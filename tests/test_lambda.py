# tests/test_lambda.py
#
# Week 3 Lambda tests. No real Docker needed for core tests — we mock docker-py.
# Docker tests are decorated with skipif guard (same pattern as test_week2_integration.py).
#
# Tests:
#   1. Simple function: PAYLOAD injected, code does print(PAYLOAD["x"] + 1) → output="2"
#   2. Timeout=1s on sleep(10) → InvokeResult.error contains "timeout"
#   3. /tmp/fn_{id}.py cleaned up after every run (success, failure, timeout)
#   4. FunctionDef store/retrieve cycle via in-memory SQLite

import asyncio
import os
import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _docker_available() -> bool:
    try:
        import docker
        docker.from_env().ping()
        return True
    except Exception:
        return False


def _make_fn(code: str, runtime: str = "python3.11") -> "FunctionDef":
    from shared.models import FunctionDef
    return FunctionDef(
        function_id = str(uuid.uuid4()),
        name        = "test_fn",
        code        = code,
        runtime     = runtime,
        created_at  = datetime.utcnow(),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 1: Simple function execution — mocked Docker
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_lambda_invoke_simple_output():
    """
    PAYLOAD = {"x": 1} is injected; code does print(PAYLOAD["x"] + 1).
    Mocked docker returns b"2\\n" as stdout.
    InvokeResult.output should be "2".
    """
    from worker.functions.lambda_runner import _run_function_sync
    from shared.models import InvokeResult

    fn = _make_fn('print(PAYLOAD["x"] + 1)')
    payload = {"x": 1}

    mock_client = MagicMock()
    mock_client.containers.run.return_value = b"2\n"

    with patch("worker.functions.lambda_runner._get_docker_client", return_value=mock_client):
        output, error, duration_ms = _run_function_sync(
            fn.function_id, fn.code, payload, fn.runtime, timeout_seconds=30
        )

    assert output == "2", f"Expected output='2', got {output!r}"
    assert error is None
    assert duration_ms >= 0


@pytest.mark.anyio
async def test_lambda_invoke_simple_output_async():
    """Same test but through the full async invoke() path."""
    from worker.functions.lambda_runner import invoke
    from shared.models import TaskStatus

    fn = _make_fn('print(PAYLOAD["x"] + 1)')
    mock_client = MagicMock()
    mock_client.containers.run.return_value = b"2\n"

    with patch("worker.functions.lambda_runner._get_docker_client", return_value=mock_client):
        result = await invoke(fn, payload={"x": 1}, timeout_seconds=30, worker_id="test-worker")

    assert result.output == "2"
    assert result.error is None
    assert result.function_id == fn.function_id
    assert result.worker_id == "test-worker"


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 2: Timeout — mocked Docker raises a timeout-like exception
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_lambda_invoke_timeout():
    """
    Docker raises a timeout exception; InvokeResult.error should contain 'timeout'.
    """
    from worker.functions.lambda_runner import invoke

    fn = _make_fn("import time; time.sleep(10)")
    mock_client = MagicMock()
    mock_client.containers.run.side_effect = Exception(
        "Read timeout: timed out waiting for container"
    )

    with patch("worker.functions.lambda_runner._get_docker_client", return_value=mock_client):
        result = await invoke(fn, payload={}, timeout_seconds=1, worker_id="test-worker")

    assert result.error is not None
    assert "timeout" in result.error.lower(), (
        f"Expected 'timeout' in error, got {result.error!r}"
    )
    assert result.output is None


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 3: /tmp/fn_{id}.py cleanup — always cleaned up
# ═══════════════════════════════════════════════════════════════════════════════

def test_lambda_cleanup_on_success():
    """After a successful run, /tmp/fn_{function_id}.py must not exist."""
    from worker.functions.lambda_runner import _run_function_sync
    from pathlib import Path

    fn = _make_fn("pass")
    mock_client = MagicMock()
    mock_client.containers.run.return_value = b""

    with patch("worker.functions.lambda_runner._get_docker_client", return_value=mock_client):
        _run_function_sync(fn.function_id, fn.code, {}, fn.runtime, 30)

    script_path = Path(f"/tmp/fn_{fn.function_id}.py")
    assert not script_path.exists(), f"Script not cleaned up: {script_path}"


def test_lambda_cleanup_on_error():
    """After a failed run (exception), /tmp/fn_{id}.py must still be cleaned up."""
    from worker.functions.lambda_runner import _run_function_sync
    from pathlib import Path

    fn = _make_fn("raise RuntimeError('boom')")
    mock_client = MagicMock()
    import docker.errors
    mock_client.containers.run.side_effect = docker.errors.ContainerError(
        "c", 1, "raise RuntimeError", "alpine", b"RuntimeError: boom"
    )

    with patch("worker.functions.lambda_runner._get_docker_client", return_value=mock_client):
        output, error, duration_ms = _run_function_sync(
            fn.function_id, fn.code, {}, fn.runtime, 30
        )

    script_path = Path(f"/tmp/fn_{fn.function_id}.py")
    assert not script_path.exists(), f"Script not cleaned up on error: {script_path}"
    assert error is not None


def test_lambda_cleanup_on_timeout():
    """After a timeout exception, /tmp/fn_{id}.py must still be cleaned up."""
    from worker.functions.lambda_runner import _run_function_sync
    from pathlib import Path

    fn = _make_fn("import time; time.sleep(999)")
    mock_client = MagicMock()
    mock_client.containers.run.side_effect = Exception("Read timed out")

    with patch("worker.functions.lambda_runner._get_docker_client", return_value=mock_client):
        output, error, duration_ms = _run_function_sync(
            fn.function_id, fn.code, {}, fn.runtime, 1
        )

    script_path = Path(f"/tmp/fn_{fn.function_id}.py")
    assert not script_path.exists(), f"Script not cleaned up on timeout: {script_path}"
    assert error is not None


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 4: PAYLOAD injection — code file contents are correct
# ═══════════════════════════════════════════════════════════════════════════════

def test_lambda_payload_injection_written_to_file():
    """
    Verify that the generated script file starts with
    PAYLOAD = <json payload> followed by user code.
    We intercept the file write before it gets deleted.
    """
    from pathlib import Path
    import json

    fn = _make_fn("print('hello')")
    payload = {"key": "value", "num": 42}
    expected_first_line = f'PAYLOAD = {json.dumps(payload)}'

    captured_content = []

    mock_client = MagicMock()
    original_run = mock_client.containers.run

    def capture_and_run(*args, **kwargs):
        # At the time containers.run() is called, the file should still exist
        script_path = Path(f"/tmp/fn_{fn.function_id}.py")
        if script_path.exists():
            captured_content.append(script_path.read_text())
        return b"hello"

    mock_client.containers.run.side_effect = capture_and_run

    from worker.functions.lambda_runner import _run_function_sync
    with patch("worker.functions.lambda_runner._get_docker_client", return_value=mock_client):
        _run_function_sync(fn.function_id, fn.code, payload, fn.runtime, 30)

    assert captured_content, "Script file was never written"
    first_line = captured_content[0].splitlines()[0]
    assert first_line == expected_first_line, (
        f"Expected first line to be {expected_first_line!r}, got {first_line!r}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 5: Real Docker — alpine echo (skipped if Docker unavailable)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
@pytest.mark.skipif(not _docker_available(), reason="Docker daemon not available")
async def test_lambda_real_docker_python():
    """
    Actually runs python:3.11-slim in Docker with a PAYLOAD-injecting script.
    Verifies output="2" from print(PAYLOAD["x"] + 1) where x=1.
    """
    from worker.functions.lambda_runner import invoke

    fn = _make_fn('print(PAYLOAD["x"] + 1)')
    result = await invoke(fn, payload={"x": 1}, timeout_seconds=60, worker_id="test")

    assert result.output == "2", f"Expected '2', got {result.output!r}"
    assert result.error is None


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 6: Function store CRUD (in-memory SQLite)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
async def async_db_session():
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
    from master.db.models import Base

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.anyio
async def test_function_store_create_list_delete(async_db_session):
    """store → list → get → delete lifecycle via function_repository."""
    from master.db import function_repository as fn_repo
    from shared.models import FunctionDef

    fn = FunctionDef(
        function_id = str(uuid.uuid4()),
        name        = "my_fn",
        code        = "print('hello')",
        runtime     = "python3.11",
        created_at  = datetime.utcnow(),
    )

    # Create
    db_fn = await fn_repo.create_function(async_db_session, fn)
    assert db_fn.function_id == fn.function_id

    # List
    all_fns = await fn_repo.list_functions(async_db_session)
    assert any(f.function_id == fn.function_id for f in all_fns)

    # Get
    fetched = await fn_repo.get_function(async_db_session, fn.function_id)
    assert fetched is not None
    assert fetched.name == "my_fn"

    # Delete
    deleted = await fn_repo.delete_function(async_db_session, fn.function_id)
    assert deleted is True

    # Confirm gone
    gone = await fn_repo.get_function(async_db_session, fn.function_id)
    assert gone is None
