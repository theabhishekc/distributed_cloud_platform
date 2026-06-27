# master/storage/upload_orchestrator.py
#
# Splits an uploaded file into 1MB chunks, replicates each chunk to 2 workers,
# verifies MD5 on every write, and persists FileMetadata + FileChunk records.
#
# Algorithm:
#   1. Generate file_id (UUID).
#   2. Split bytes into ceil(size/1MB) chunks.
#   3. For each chunk:
#      a. Compute MD5 checksum.
#      b. Pick 2 distinct healthy workers using get_healthy_nodes() + scoring.
#      c. POST chunk to both workers as multipart form data.
#      d. Verify response checksum matches computed checksum.
#   4. Persist FileMetadata + all FileChunk records.
#   5. Return Pydantic FileMetadata.

import asyncio
import hashlib
import uuid
from datetime import datetime
from typing import List, Tuple

import httpx

from master.db.database import get_db
from master.db import storage_repository as storage_repo
from master.registry.node_registry import get_healthy_nodes
from master.scheduler.scheduler import NoHealthyNodeError
from shared.logger import get_logger
from shared.models import FileChunk, FileMetadata, NodeInfo

logger = get_logger("upload_orchestrator", node_id="master")

CHUNK_SIZE = 1024 * 1024           # 1 MB
REPLICATION_FACTOR = 2
WORKER_TIMEOUT = 30.0


# ── Custom exception ──────────────────────────────────────────────────────────

class StorageError(Exception):
    """Raised when a chunk cannot be stored on any worker."""


# ── Worker selection ──────────────────────────────────────────────────────────

def _pick_two_workers() -> Tuple[NodeInfo, NodeInfo]:
    """
    Return two distinct healthy workers, best-scored first.
    Raises NoHealthyNodeError if < 2 healthy nodes are available.
    """
    from master.scheduler.scheduler import _score  # noqa: F401 (lazy import to avoid cycle)

    healthy = get_healthy_nodes()
    if len(healthy) < 2:
        raise NoHealthyNodeError(
            f"Need at least 2 healthy workers for replication_factor=2, "
            f"but only {len(healthy)} are available."
        )
    scored = sorted(healthy, key=lambda n: _score(n), reverse=True)
    return scored[0], scored[1]


def _pick_one_worker_excluding(exclude_id: str) -> NodeInfo:
    """Pick a single healthy worker that is not exclude_id."""
    from master.scheduler.scheduler import _score

    healthy = [n for n in get_healthy_nodes() if n.node_id != exclude_id]
    if not healthy:
        raise NoHealthyNodeError(
            f"No healthy workers available excluding {exclude_id!r}."
        )
    return max(healthy, key=lambda n: _score(n))


# ── Chunk upload ──────────────────────────────────────────────────────────────

async def _post_chunk_to_worker(
    client: httpx.AsyncClient,
    worker: NodeInfo,
    chunk_id: str,
    file_id: str,
    chunk_index: int,
    checksum: str,
    data: bytes,
) -> str:
    """
    POST a single chunk to one worker. Returns the checksum the worker echoes back.
    Raises httpx.HTTPError or StorageError on failure.
    """
    url = f"http://{worker.ip}:{worker.port}/storage/chunks"
    response = await client.post(
        url,
        data={
            "chunk_id":    chunk_id,
            "file_id":     file_id,
            "chunk_index": str(chunk_index),
            "checksum":    checksum,
        },
        files={"file": (chunk_id, data, "application/octet-stream")},
    )
    response.raise_for_status()
    body = response.json()
    returned_checksum = body.get("checksum", "")
    if returned_checksum != checksum:
        raise StorageError(
            f"Worker {worker.node_id!r} returned wrong checksum for chunk "
            f"[{chunk_id}]: expected={checksum!r} got={returned_checksum!r}"
        )
    return returned_checksum


# ── Public API ────────────────────────────────────────────────────────────────

async def upload_file(file_bytes: bytes, filename: str) -> FileMetadata:
    """
    Split, replicate, and persist an uploaded file.

    Args:
        file_bytes: Full file content as bytes.
        filename:   Original filename (stored in metadata).

    Returns:
        Pydantic FileMetadata with status='available'.

    Raises:
        NoHealthyNodeError: Fewer than 2 healthy workers are available.
        StorageError:       A chunk could not be replicated to both workers.
    """
    file_id     = str(uuid.uuid4())
    total_size  = len(file_bytes)
    created_at  = datetime.utcnow()

    # Split into 1MB chunks
    chunks_raw: List[bytes] = [
        file_bytes[i : i + CHUNK_SIZE]
        for i in range(0, max(total_size, 1), CHUNK_SIZE)
    ]
    chunk_count = len(chunks_raw)

    logger.info(
        f"Starting upload — file_id={file_id} filename={filename!r} "
        f"size={total_size}B chunks={chunk_count}",
        extra={"event": "upload_start", "file_id": file_id, "orig_filename": filename},
    )

    stored_chunks: List[FileChunk] = []

    async with httpx.AsyncClient(timeout=WORKER_TIMEOUT) as client:
        for idx, raw in enumerate(chunks_raw):
            chunk_id = str(uuid.uuid4())
            checksum = hashlib.md5(raw).hexdigest()

            # Pick 2 distinct healthy workers
            primary, replica = _pick_two_workers()

            # Upload to primary
            try:
                await _post_chunk_to_worker(
                    client, primary, chunk_id, file_id, idx, checksum, raw
                )
            except Exception as exc:
                raise StorageError(
                    f"Failed to upload chunk {idx} to primary worker "
                    f"{primary.node_id!r}: {exc}"
                ) from exc

            # Upload to replica
            try:
                await _post_chunk_to_worker(
                    client, replica, chunk_id, file_id, idx, checksum, raw
                )
            except Exception as exc:
                raise StorageError(
                    f"Failed to upload chunk {idx} to replica worker "
                    f"{replica.node_id!r}: {exc}"
                ) from exc

            stored_chunks.append(FileChunk(
                chunk_id          = chunk_id,
                file_id           = file_id,
                chunk_index       = idx,
                size_bytes        = len(raw),
                checksum          = checksum,
                worker_id         = primary.node_id,
                replica_worker_id = replica.node_id,
            ))

            logger.info(
                f"Chunk {idx}/{chunk_count-1} [{chunk_id[-8:]}] stored — "
                f"primary={primary.node_id[-8:]} replica={replica.node_id[-8:]}",
                extra={
                    "event":      "chunk_stored",
                    "file_id":    file_id,
                    "chunk_id":   chunk_id,
                    "chunk_index": idx,
                    "primary":    primary.node_id,
                    "replica":    replica.node_id,
                },
            )

    # Persist to PostgreSQL
    async with get_db() as session:
        await storage_repo.create_file_metadata(
            session,
            file_id            = file_id,
            filename           = filename,
            total_size         = total_size,
            chunk_count        = chunk_count,
            replication_factor = REPLICATION_FACTOR,
        )
        for chunk in stored_chunks:
            await storage_repo.create_chunk(
                session,
                chunk_id          = chunk.chunk_id,
                file_id           = file_id,
                chunk_index       = chunk.chunk_index,
                size_bytes        = chunk.size_bytes,
                checksum          = chunk.checksum,
                worker_id         = chunk.worker_id,
                replica_worker_id = chunk.replica_worker_id,
            )

    logger.info(
        f"Upload complete — file_id={file_id} filename={filename!r} "
        f"chunks={chunk_count} size={total_size}B",
        extra={"event": "upload_complete", "file_id": file_id, "chunk_count": chunk_count},
    )

    return FileMetadata(
        file_id            = file_id,
        filename           = filename,
        total_size         = total_size,
        chunk_count        = chunk_count,
        replication_factor = REPLICATION_FACTOR,
        created_at         = created_at,
        status             = "available",
    )
