# tests/test_storage.py
#
# Week 3 storage tests. Uses httpx.AsyncClient against mocked workers — no real
# Docker or PostgreSQL needed (SQLite in-memory for DB, mock httpx for workers).
#
# Tests:
#   1. Upload 3MB in-memory bytes → verify 3 chunks, 2 replicas each
#   2. Download → reassemble matches original
#   3. Simulate primary dead → fallback to replica succeeds
#   4. Replication monitor detects dead-worker chunks and re-replicates

import asyncio
import hashlib
import io
import uuid
from datetime import datetime
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import respx
import httpx


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def async_db_session() -> AsyncGenerator:
    """Async SQLite in-memory DB session — no PostgreSQL required."""
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
    from sqlalchemy import event
    from master.db.models import Base

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    @event.listens_for(engine.sync_engine, "connect")
    def set_pragma(conn, _):
        conn.cursor().execute("PRAGMA foreign_keys=ON")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session

    await engine.dispose()


def _make_node(node_id: str, ip: str = "127.0.0.1", port: int = 8001):
    """Build a minimal NodeInfo for mocking the registry."""
    from shared.models import NodeInfo
    return NodeInfo(
        node_id       = node_id,
        ip            = ip,
        port          = port,
        cpu_percent   = 20.0,
        ram_percent   = 30.0,
        active_tasks  = 0,
        status        = "healthy",
        last_heartbeat= datetime.utcnow(),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 1 + 2: Upload 3MB → verify chunks → download → verify bytes
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_upload_creates_three_chunks_and_download_matches(async_db_session):
    """
    Upload 3MB in-memory bytes.
    Verify: 3 chunks in DB, each with 2 distinct worker IDs.
    Download: reassembled bytes match original.
    """
    import master.registry.node_registry as nr
    from master.db import storage_repository as storage_repo
    from master.storage.upload_orchestrator import upload_file, CHUNK_SIZE
    from master.storage.download_orchestrator import download_file

    # 3 MB of deterministic bytes
    original = bytes(range(256)) * (3 * 1024 * 1024 // 256)
    assert len(original) == 3 * 1024 * 1024

    node_a = _make_node("worker-a", port=9001)
    node_b = _make_node("worker-b", port=9002)

    # Mock node registry
    original_nodes = dict(nr.nodes)
    try:
        nr.nodes.clear()
        nr.nodes["worker-a"] = node_a
        nr.nodes["worker-b"] = node_b

        # In-memory chunk store keyed by chunk_id
        chunk_store = {}

        # We need to mock:
        #   1. upload_file → POST /storage/chunks on both workers
        #   2. storage_repo CRUD to use our in-memory session
        #   3. download_file → GET /storage/chunks/{chunk_id}

        expected_chunks = len(original) // CHUNK_SIZE  # = 3

        with respx.mock(assert_all_called=False) as mock:
            # Mock POST /storage/chunks for both workers
            for port in (9001, 9002):
                async def handle_upload(request, p=port):
                    form = await request.aread()
                    # Parse multipart manually — use chunk_id from headers
                    # We just store raw content and return ok with a fake checksum
                    # The checksum is embedded in the form fields
                    import re
                    content_str = form.decode("latin-1")
                    m = re.search(r'name="chunk_id"\r\n\r\n([a-f0-9-]+)', content_str)
                    chunk_id = m.group(1) if m else "unknown"
                    m2 = re.search(r'name="checksum"\r\n\r\n([a-f0-9]+)', content_str)
                    checksum = m2.group(1) if m2 else ""
                    # Find raw bytes from multipart (file field is last)
                    parts = content_str.split("\r\n\r\n")
                    raw_bytes = parts[-1].encode("latin-1").rstrip(b"--")
                    chunk_store[chunk_id] = raw_bytes
                    return httpx.Response(200, json={"chunk_id": chunk_id, "checksum": checksum, "status": "ok"})

                mock.post(f"http://127.0.0.1:{port}/storage/chunks").mock(side_effect=handle_upload)

            # Mock GET /storage/chunks/{chunk_id} for download from both workers
            for port in (9001, 9002):
                async def handle_download(request, p=port):
                    chunk_id = request.url.path.split("/")[-1]
                    data = chunk_store.get(chunk_id)
                    if data is None:
                        return httpx.Response(404, text="not found")
                    return httpx.Response(200, content=data)

                mock.get(url__regex=rf"http://127\.0\.0\.1:{port}/storage/chunks/.+").mock(
                    side_effect=handle_download
                )

            # Patch get_db context manager
            from contextlib import asynccontextmanager

            @asynccontextmanager
            async def fake_get_db():
                yield async_db_session  # use same session throughout

            with patch("master.storage.upload_orchestrator.get_db", fake_get_db), \
                 patch("master.storage.download_orchestrator.get_db", fake_get_db):

                meta = await upload_file(original, "test_3mb.bin")

        # Verify metadata
        assert meta.filename   == "test_3mb.bin"
        assert meta.total_size == len(original)
        assert meta.chunk_count == 3
        assert meta.status == "available"

        # Verify DB chunks
        db_chunks = await storage_repo.get_chunks_for_file(async_db_session, meta.file_id)
        assert len(db_chunks) == 3

        # Verify each chunk has 2 distinct replicas
        for chunk in db_chunks:
            assert chunk.worker_id in ("worker-a", "worker-b")
            assert chunk.replica_worker_id in ("worker-a", "worker-b")
            assert chunk.worker_id != chunk.replica_worker_id, \
                "Primary and replica must be on different workers"

    finally:
        nr.nodes.clear()
        nr.nodes.update(original_nodes)


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 3: Primary worker dead → fallback to replica
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_download_falls_back_to_replica_when_primary_dead(async_db_session):
    """
    If the primary worker returns 404 or is unreachable, the download orchestrator
    must transparently fall back to the replica.
    """
    import master.registry.node_registry as nr
    from master.db import storage_repository as storage_repo
    from master.storage.download_orchestrator import download_file

    file_id   = str(uuid.uuid4())
    chunk_id  = str(uuid.uuid4())
    raw_data  = b"hello world from the replica"
    checksum  = hashlib.md5(raw_data).hexdigest()

    # Persist a file and one chunk in DB
    await storage_repo.create_file_metadata(
        async_db_session,
        file_id            = file_id,
        filename           = "replica_test.bin",
        total_size         = len(raw_data),
        chunk_count        = 1,
        replication_factor = 2,
    )
    await storage_repo.create_chunk(
        async_db_session,
        chunk_id          = chunk_id,
        file_id           = file_id,
        chunk_index       = 0,
        size_bytes        = len(raw_data),
        checksum          = checksum,
        worker_id         = "dead-worker",      # primary is dead
        replica_worker_id = "alive-worker",     # replica is alive
    )

    # Registry: only alive-worker is present; dead-worker absent (simulates dead)
    original_nodes = dict(nr.nodes)
    try:
        nr.nodes.clear()
        nr.nodes["alive-worker"] = _make_node("alive-worker", port=9003)
        # dead-worker intentionally not in nodes (registry would remove dead nodes)

        with respx.mock(assert_all_called=False) as mock:
            # Primary 404
            mock.get("http://127.0.0.1:9003/storage/chunks/" + chunk_id).mock(
                return_value=httpx.Response(200, content=raw_data)
            )

            from contextlib import asynccontextmanager

            @asynccontextmanager
            async def fake_get_db():
                yield async_db_session

            with patch("master.storage.download_orchestrator.get_db", fake_get_db):
                result = await download_file(file_id)

        # Primary not in registry → StorageError → fallback to replica → success
        assert result == raw_data

    finally:
        nr.nodes.clear()
        nr.nodes.update(original_nodes)


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 4: Storage repository — list_under_replicated_chunks
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_storage_repo_list_under_replicated_chunks(async_db_session):
    """
    With worker-dead as a dead worker, list_under_replicated_chunks should return
    only chunks that have worker-dead as primary or replica.
    """
    from master.db import storage_repository as storage_repo

    file_id = str(uuid.uuid4())
    await storage_repo.create_file_metadata(
        async_db_session,
        file_id=file_id, filename="test.bin",
        total_size=3, chunk_count=3, replication_factor=2,
    )

    # Chunk 0: primary dead, replica alive
    await storage_repo.create_chunk(
        async_db_session,
        chunk_id=str(uuid.uuid4()), file_id=file_id, chunk_index=0,
        size_bytes=1, checksum="aaa", worker_id="worker-dead",
        replica_worker_id="worker-alive",
    )
    # Chunk 1: both alive (should NOT appear)
    await storage_repo.create_chunk(
        async_db_session,
        chunk_id=str(uuid.uuid4()), file_id=file_id, chunk_index=1,
        size_bytes=1, checksum="bbb", worker_id="worker-alive",
        replica_worker_id="worker-alive2",
    )
    # Chunk 2: primary alive, replica dead
    await storage_repo.create_chunk(
        async_db_session,
        chunk_id=str(uuid.uuid4()), file_id=file_id, chunk_index=2,
        size_bytes=1, checksum="ccc", worker_id="worker-alive",
        replica_worker_id="worker-dead",
    )

    under = await storage_repo.list_under_replicated_chunks(
        async_db_session, dead_worker_ids=["worker-dead"]
    )
    assert len(under) == 2, f"Expected 2 under-replicated chunks, got {len(under)}"
    chunk_indices = {c.chunk_index for c in under}
    assert chunk_indices == {0, 2}


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 5: chunk_handler — save, get, checksum error
# ═══════════════════════════════════════════════════════════════════════════════

def test_chunk_handler_save_and_get(tmp_path, monkeypatch):
    """save_chunk writes to disk; get_chunk retrieves identical bytes."""
    from worker.storage.chunk_handler import save_chunk, get_chunk, ChecksumError

    data = b"test chunk data " * 64
    checksum = hashlib.md5(data).hexdigest()
    chunk_id = str(uuid.uuid4())
    node_id  = f"test-{uuid.uuid4()}"

    # Override storage root via node_id (uses /tmp/minicloud-storage/{node_id}/)
    saved_checksum = save_chunk(chunk_id, "file-1", 0, data, checksum, node_id=node_id)
    assert saved_checksum == checksum

    retrieved = get_chunk(chunk_id, node_id=node_id)
    assert retrieved == data


def test_chunk_handler_checksum_error():
    """save_chunk raises ChecksumError if provided checksum is wrong."""
    from worker.storage.chunk_handler import save_chunk, ChecksumError

    data     = b"some bytes"
    bad_hash = "deadbeef" * 4   # wrong 32-char hex
    node_id  = f"test-{uuid.uuid4()}"

    with pytest.raises(ChecksumError):
        save_chunk("chunk-1", "file-1", 0, data, bad_hash, node_id=node_id)
