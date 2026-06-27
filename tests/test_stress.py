# tests/test_stress.py
#
# Week 4 stress tests. Uses httpx.AsyncClient against mocked workers — no real
# Docker or PostgreSQL needed (SQLite in-memory for DB, mock httpx for workers).
#
# Tests:
#   1. Concurrent Task Scheduling Stress (50 tasks in parallel)
#   2. Concurrent File Upload & Chunking Stress (10 concurrent uploads)
#   3. Concurrent Lambda Invocation Stress (20 concurrent invocations)
#   4. Metrics & Log Query API validation under load

import asyncio
import hashlib
import uuid
from datetime import datetime
from typing import AsyncGenerator
from unittest.mock import patch

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from master.main import app as master_app
from worker.main import app as worker_app


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def async_db_engine() -> AsyncGenerator:
    """Async SQLite shared in-memory DB engine and sessionmaker factory."""
    from sqlalchemy import event
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from master.db.models import Base

    # Use a shared in-memory database so multiple concurrent sessions see the same tables/data
    engine = create_async_engine("sqlite+aiosqlite:///file:stressmem?mode=memory&cache=shared", echo=False)

    @event.listens_for(engine.sync_engine, "connect")
    def set_pragma(conn, _):
        conn.cursor().execute("PRAGMA foreign_keys=ON")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory

    await engine.dispose()


@pytest.fixture
async def async_db_session(async_db_engine) -> AsyncGenerator:
    """Single async session for non-concurrent setup/teardown."""
    async with async_db_engine() as session:
        yield session


def _make_node(node_id: str, ip: str = "127.0.0.1", port: int = 8001):
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
# TEST 1: Concurrent Task Scheduling Stress (50 Tasks)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_concurrent_task_scheduling_stress(async_db_engine):
    import master.registry.node_registry as nr
    from master.api.task_routes import submit_task
    from contextlib import asynccontextmanager

    node_a = _make_node("stress-worker-1", port=9001)
    node_b = _make_node("stress-worker-2", port=9002)

    original_nodes = dict(nr.nodes)
    try:
        nr.nodes.clear()
        nr.nodes["stress-worker-1"] = node_a
        nr.nodes["stress-worker-2"] = node_b

        @asynccontextmanager
        async def fake_get_db():
            async with async_db_engine() as session:
                yield session

        with respx.mock(assert_all_called=False) as mock:
            for port in (9001, 9002):
                mock.post(f"http://127.0.0.1:{port}/tasks").mock(
                    return_value=httpx.Response(202, json={"status": "ACCEPTED", "message": "Enqueued"})
                )

            with patch("master.api.task_routes.get_db", fake_get_db):
                # Launch 50 submit_task requests concurrently
                tasks = [
                    submit_task({"image": "alpine", "command": "echo stress", "ram_limit_mb": 64})
                    for _ in range(50)
                ]
                results = await asyncio.gather(*tasks)

        assert len(results) == 50
        for res in results:
            assert res["status"] == "SCHEDULED"
            assert res["worker_id"] in ("stress-worker-1", "stress-worker-2")

    finally:
        nr.nodes.clear()
        nr.nodes.update(original_nodes)


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 2: Concurrent File Upload Stress (10 Concurrent Uploads)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_concurrent_file_upload_stress(async_db_engine):
    import master.registry.node_registry as nr
    from master.storage.upload_orchestrator import upload_file
    from contextlib import asynccontextmanager

    node_a = _make_node("stress-worker-1", port=9001)
    node_b = _make_node("stress-worker-2", port=9002)

    original_nodes = dict(nr.nodes)
    try:
        nr.nodes.clear()
        nr.nodes["stress-worker-1"] = node_a
        nr.nodes["stress-worker-2"] = node_b

        @asynccontextmanager
        async def fake_get_db():
            async with async_db_engine() as session:
                yield session

        with respx.mock(assert_all_called=False) as mock:
            for port in (9001, 9002):
                async def handle_upload(request, p=port):
                    form = await request.aread()
                    import re
                    content_str = form.decode("latin-1")
                    m = re.search(r'name="chunk_id"\r\n\r\n([a-f0-9-]+)', content_str)
                    chunk_id = m.group(1) if m else "unknown"
                    m2 = re.search(r'name="checksum"\r\n\r\n([a-f0-9]+)', content_str)
                    checksum = m2.group(1) if m2 else ""
                    return httpx.Response(200, json={"chunk_id": chunk_id, "checksum": checksum, "status": "ok"})

                mock.post(f"http://127.0.0.1:{port}/storage/chunks").mock(side_effect=handle_upload)

            with patch("master.storage.upload_orchestrator.get_db", fake_get_db):
                # 10 concurrent uploads of 1MB files
                file_bytes = b"stress upload bytes " * 51200
                upload_tasks = [
                    upload_file(file_bytes, f"stress_{i}.bin")
                    for i in range(10)
                ]
                results = await asyncio.gather(*upload_tasks)

        assert len(results) == 10
        for meta in results:
            assert meta.filename.startswith("stress_")
            assert meta.status == "available"

    finally:
        nr.nodes.clear()
        nr.nodes.update(original_nodes)


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 3: Concurrent Lambda Invocation Stress (20 Concurrent Invocations)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_concurrent_lambda_invocation_stress(async_db_engine, async_db_session):
    import master.registry.node_registry as nr
    from master.api.function_routes import invoke_function, InvokeBody
    from shared.models import FunctionDef, InvokeRequest, InvokeResult
    from contextlib import asynccontextmanager

    node_a = _make_node("stress-worker-1", port=9001)

    original_nodes = dict(nr.nodes)
    try:
        nr.nodes.clear()
        nr.nodes["stress-worker-1"] = node_a

        # Create a mock function in DB
        from master.db import function_repository as func_repo
        fn_id = str(uuid.uuid4())
        fn_def = FunctionDef(
            function_id = fn_id,
            name        = "stress_func",
            code        = "def handler(event): return {'stress': 'ok'}",
            runtime     = "python3.10",
            created_at  = datetime.utcnow(),
        )
        await func_repo.create_function(async_db_session, fn_def)

        @asynccontextmanager
        async def fake_get_db():
            async with async_db_engine() as session:
                yield session

        with respx.mock(assert_all_called=False) as mock:
            mock.post("http://127.0.0.1:9001/functions/invoke").mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "function_id": fn_id,
                        "output": '{"stress": "ok"}',
                        "error": None,
                        "duration_ms": 15,
                        "worker_id": "stress-worker-1",
                    },
                )
            )

            with patch("master.functions.function_store.get_db", fake_get_db):
                invocations = [
                    invoke_function(fn_id, InvokeBody(payload={"req": i}))
                    for i in range(20)
                ]
                results = await asyncio.gather(*invocations)

        assert len(results) == 20
        for res in results:
            assert res.error is None
            assert res.output == '{"stress": "ok"}'

    finally:
        nr.nodes.clear()
        nr.nodes.update(original_nodes)


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 4: Metrics & Log Query API Validation
# ═══════════════════════════════════════════════════════════════════════════════

def test_prometheus_metrics_endpoints():
    """Verify that both master and worker expose valid Prometheus metrics at /metrics."""
    master_client = TestClient(master_app)
    resp = master_client.get("/metrics")
    assert resp.status_code == 200
    assert "minicloud_healthy_nodes" in resp.text
    assert "minicloud_tasks_total" in resp.text

    worker_client = TestClient(worker_app)
    resp_w = worker_client.get("/metrics")
    assert resp_w.status_code == 200
    assert "minicloud_worker_local_cpu_percent" in resp_w.text
    assert "minicloud_worker_local_tasks_total" in resp_w.text


@pytest.mark.anyio
async def test_log_query_api(async_db_session):
    """Verify log ingestion and log query API endpoints under stress simulation."""
    from shared.log_aggregator import write_log_to_db
    from master.api.log_routes import get_logs

    # Insert 15 logs simulating stress events
    for i in range(15):
        await write_log_to_db(
            {
                "log_id":    str(uuid.uuid4()),
                "timestamp": datetime.utcnow(),
                "level":     "INFO" if i % 2 == 0 else "ERROR",
                "service":   "stress_test",
                "node_id":   f"stress-worker-{i%2 + 1}",
                "message":   f"Stress log message {i}",
                "extra":     {"stress_id": i},
            },
            async_db_session,
        )

    # Query all logs
    logs = await get_logs(session=async_db_session, node_id=None, task_id=None, level=None, since=None, limit=10)
    assert len(logs) == 10

    # Query by level
    error_logs = await get_logs(session=async_db_session, node_id=None, task_id=None, level="ERROR", since=None, limit=10)
    assert all(log.level == "ERROR" for log in error_logs)

    # Query by node_id
    node_logs = await get_logs(session=async_db_session, node_id="stress-worker-1", task_id=None, level=None, since=None, limit=10)
    assert all(log.node_id == "stress-worker-1" for log in node_logs)
