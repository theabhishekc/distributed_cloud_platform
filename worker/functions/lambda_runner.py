# worker/functions/lambda_runner.py
#
# Serverless function executor — runs user-supplied Python code in a sandboxed
# Docker container (--network=none, --memory=128m, --cpus=0.25).
#
# Execution model:
#   1. Write user code to /tmp/fn_{function_id}.py
#   2. Prepend PAYLOAD = <json payload dict> as first line
#   3. docker run with resource caps and network isolation
#   4. Capture stdout (output) and stderr (error), measure duration_ms
#   5. Delete /tmp/fn_{id}.py after run — always, even on failure/timeout
#
# All docker-py SDK calls are blocking; wrapped in run_in_executor to avoid
# blocking the async event loop (same pattern as docker_runner.py).

import asyncio
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Optional

import docker
import docker.errors

from shared.logger import get_logger
from shared.models import FunctionDef, InvokeResult
from worker.config import WORKER_NODE_ID

logger = get_logger("lambda_runner", node_id=WORKER_NODE_ID)

# Docker image → runtime tag mapping
RUNTIME_IMAGE_MAP = {
    "python3.11": "python:3.11-slim",
    "python3.10": "python:3.10-slim",
    "python3.9":  "python:3.9-slim",
}

_docker_client = None


def _get_docker_client():
    global _docker_client
    if _docker_client is None:
        _docker_client = docker.from_env()
    return _docker_client


# ── Blocking implementation (runs in executor) ────────────────────────────────

def _run_function_sync(
    function_id: str,
    code: str,
    payload: dict,
    runtime: str,
    timeout_seconds: int,
) -> tuple[Optional[str], Optional[str], int]:
    """
    Blocking: write code file, run container, return (stdout, stderr, duration_ms).

    Returns (output, error, duration_ms).
    """
    # Map runtime string to Docker image tag
    image = RUNTIME_IMAGE_MAP.get(runtime, f"python:{runtime}-slim")

    # Build the script: PAYLOAD injected as first line, then user code
    payload_line = f"PAYLOAD = {json.dumps(payload)}\n"
    full_code = payload_line + code

    # Write to temp file
    script_path = Path(f"/tmp/fn_{function_id}.py")
    try:
        script_path.write_text(full_code, encoding="utf-8")

        client = _get_docker_client()
        start_ms = int(time.monotonic() * 1000)

        try:
            container_output = client.containers.run(
                image     = image,
                command   = "python /app/handler.py",
                volumes   = {str(script_path): {"bind": "/app/handler.py", "mode": "ro"}},
                mem_limit = "128m",
                nano_cpus = int(0.25 * 1e9),
                network_disabled = True,    # --network=none equivalent
                remove    = True,
                detach    = False,
                stdout    = True,
                stderr    = True,
                timeout   = timeout_seconds,
            )
            duration_ms = int(time.monotonic() * 1000) - start_ms
            stdout_str = (
                container_output.decode("utf-8", errors="replace")
                if isinstance(container_output, bytes)
                else str(container_output)
            )
            return stdout_str.strip() or None, None, duration_ms

        except docker.errors.ContainerError as exc:
            duration_ms = int(time.monotonic() * 1000) - start_ms
            stderr_str = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else str(exc)
            return None, f"exit={exc.exit_status}: {stderr_str.strip()}", duration_ms

        except Exception as exc:
            # Covers: APIError, ImageNotFound, ConnectionError, timeout
            duration_ms = int(time.monotonic() * 1000) - start_ms
            # Check if it looks like a timeout
            error_str = str(exc)
            is_timeout = (
                "timed out" in error_str.lower()
                or "timeout" in error_str.lower()
                or "read timeout" in error_str.lower()
            )
            error_label = "timeout" if is_timeout else error_str
            return None, error_label, duration_ms

    finally:
        # Always clean up the temp script
        if script_path.exists():
            script_path.unlink()
            logger.info(
                f"Cleaned up /tmp/fn_{function_id}.py",
                extra={"event": "lambda_cleanup", "function_id": function_id},
            )


# ── Public async API ──────────────────────────────────────────────────────────

async def invoke(
    function_def: FunctionDef,
    payload: dict,
    timeout_seconds: int = 30,
    worker_id: str = WORKER_NODE_ID,
) -> InvokeResult:
    """
    Invoke a serverless function in a sandboxed Docker container.

    Args:
        function_def:    FunctionDef from shared/models.py.
        payload:         Dict injected as PAYLOAD variable into the script.
        timeout_seconds: Max seconds for the container to run. Returns
                         InvokeResult(error="timeout") if exceeded.
        worker_id:       This worker's node_id (included in InvokeResult).

    Returns:
        InvokeResult with output/error and duration_ms.
    """
    logger.info(
        f"Invoking function [{function_def.function_id}] name={function_def.name!r} "
        f"runtime={function_def.runtime!r} timeout={timeout_seconds}s",
        extra={
            "event":       "lambda_invoke_start",
            "function_id": function_def.function_id,
            "fn_name":     function_def.name,
            "runtime":     function_def.runtime,
        },
    )

    loop = asyncio.get_event_loop()
    output, error, duration_ms = await loop.run_in_executor(
        None,
        _run_function_sync,
        function_def.function_id,
        function_def.code,
        payload,
        function_def.runtime,
        timeout_seconds,
    )

    if error and "timeout" in error.lower():
        logger.warning(
            f"Function [{function_def.function_id}] TIMED OUT after {timeout_seconds}s",
            extra={"event": "lambda_timeout", "function_id": function_def.function_id},
        )
    elif error:
        logger.warning(
            f"Function [{function_def.function_id}] returned error: {error[:200]}",
            extra={"event": "lambda_error", "function_id": function_def.function_id},
        )
    else:
        logger.info(
            f"Function [{function_def.function_id}] completed in {duration_ms}ms",
            extra={"event": "lambda_invoke_done", "function_id": function_def.function_id,
                   "duration_ms": duration_ms},
        )

    return InvokeResult(
        function_id = function_def.function_id,
        output      = output,
        error       = error,
        duration_ms = duration_ms,
        worker_id   = worker_id,
    )
