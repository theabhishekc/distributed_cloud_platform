# worker/executor/docker_runner.py
#
# Runs a Docker container for a TaskRequest and returns a TaskResult.
#
# Key design choices:
# - All docker-py SDK calls are BLOCKING (they talk to the Docker socket).
#   We wrap them with asyncio.get_event_loop().run_in_executor(None, fn)
#   so they never block the async event loop.
# - auto_remove=True: container is deleted as soon as it exits, no cleanup needed.
# - stdout=True, stderr=True: we capture both streams in the result.
# - Resource limits: mem_limit in MB string form, nano_cpus in integer (1 CPU = 1e9).

import asyncio
from datetime import datetime
from typing import Optional

import docker
import docker.errors
from docker import DockerClient

from shared.logger import get_logger
from shared.models import TaskRequest, TaskResult, TaskStatus
from worker.config import WORKER_NODE_ID   # injected at import time from config

logger = get_logger("docker_runner", node_id=WORKER_NODE_ID)

# ── Docker client (lazy singleton) ────────────────────────────────────────────
#
# Instantiated once per process — connecting to the local Docker socket.
# If Docker is not available, the error surfaces at task-run time, not import time.

_docker_client: Optional[DockerClient] = None


def _get_docker_client() -> DockerClient:
    global _docker_client
    if _docker_client is None:
        _docker_client = docker.from_env()
    return _docker_client


# ── Blocking helpers (run in executor) ────────────────────────────────────────

def _run_container_sync(
    image: str,
    command: str,
    mem_limit: str,
    nano_cpus: int,
) -> tuple[str, str, int]:
    """
    Blocking function: pull image if needed, run container, capture output.

    Returns (stdout, stderr, exit_code).
    Raises docker.errors.ContainerError, docker.errors.ImageNotFound,
    or docker.errors.APIError on failure.
    """
    client = _get_docker_client()

    # docker-py containers.run() with detach=False blocks until completion.
    # auto_remove=True deletes container immediately on exit.
    container_output = client.containers.run(
        image         = image,
        command       = command,
        mem_limit     = mem_limit,
        nano_cpus     = nano_cpus,
        stdout        = True,
        stderr        = True,
        remove        = True,      # auto_remove equivalent for run()
        detach        = False,
    )

    # When detach=False and stdout=True, run() returns bytes of combined output.
    stdout_str = container_output.decode("utf-8", errors="replace") if isinstance(container_output, bytes) else str(container_output)
    return stdout_str, "", 0


# ── Public async API ──────────────────────────────────────────────────────────

async def run_task(task: TaskRequest, worker_id: str) -> TaskResult:
    """
    Asynchronously execute a Docker container for the given task.

    1. Converts TaskRequest resource limits to Docker format.
    2. Runs the container in a thread pool executor (non-blocking).
    3. Returns a TaskResult with COMPLETED or FAILED status.

    Args:
        task:      The task specification from shared/models.py.
        worker_id: This worker's node_id (included in the TaskResult).
    """
    mem_limit  = f"{task.ram_limit_mb}m"
    nano_cpus  = int(task.cpu_limit * 1e9)

    started_at = datetime.utcnow()

    logger.info(
        f"Starting container — image={task.image!r} command={task.command!r} "
        f"mem={mem_limit} cpus={task.cpu_limit}",
        extra={
            "event":   "container_start",
            "task_id": task.task_id,
            "image":   task.image,
        },
    )

    loop = asyncio.get_event_loop()

    try:
        stdout, stderr, _ = await loop.run_in_executor(
            None,
            _run_container_sync,
            task.image,
            task.command,
            mem_limit,
            nano_cpus,
        )

        completed_at     = datetime.utcnow()
        duration_seconds = (completed_at - started_at).total_seconds()

        logger.info(
            f"Container finished — task={task.task_id} "
            f"duration={duration_seconds:.2f}s",
            extra={
                "event":            "container_done",
                "task_id":          task.task_id,
                "duration_seconds": duration_seconds,
            },
        )

        return TaskResult(
            task_id          = task.task_id,
            worker_id        = worker_id,
            status           = TaskStatus.COMPLETED,
            output           = stdout.strip() or None,
            error            = None,
            started_at       = started_at,
            completed_at     = completed_at,
            duration_seconds = duration_seconds,
        )

    except docker.errors.ContainerError as exc:
        # Container ran but exited non-zero
        completed_at     = datetime.utcnow()
        duration_seconds = (completed_at - started_at).total_seconds()
        error_msg        = f"ContainerError: exit={exc.exit_status} — {exc.stderr}"

        logger.error(
            f"Container exited with error — task={task.task_id} exit={exc.exit_status}",
            extra={
                "event":       "container_error",
                "task_id":     task.task_id,
                "exit_status": exc.exit_status,
                "error":       error_msg,
            },
        )

        return TaskResult(
            task_id          = task.task_id,
            worker_id        = worker_id,
            status           = TaskStatus.FAILED,
            output           = None,
            error            = error_msg,
            started_at       = started_at,
            completed_at     = completed_at,
            duration_seconds = duration_seconds,
        )

    except docker.errors.ImageNotFound as exc:
        completed_at     = datetime.utcnow()
        duration_seconds = (completed_at - started_at).total_seconds()
        error_msg        = f"ImageNotFound: {exc}"

        logger.error(
            f"Docker image not found — task={task.task_id} image={task.image!r}",
            extra={"event": "container_image_not_found", "task_id": task.task_id, "error": error_msg},
        )

        return TaskResult(
            task_id          = task.task_id,
            worker_id        = worker_id,
            status           = TaskStatus.FAILED,
            output           = None,
            error            = error_msg,
            started_at       = started_at,
            completed_at     = completed_at,
            duration_seconds = duration_seconds,
        )

    except docker.errors.APIError as exc:
        completed_at     = datetime.utcnow()
        duration_seconds = (completed_at - started_at).total_seconds()
        error_msg        = f"DockerAPIError: {exc}"

        logger.error(
            f"Docker API error — task={task.task_id}: {exc}",
            extra={"event": "container_api_error", "task_id": task.task_id, "error": error_msg},
        )

        return TaskResult(
            task_id          = task.task_id,
            worker_id        = worker_id,
            status           = TaskStatus.FAILED,
            output           = None,
            error            = error_msg,
            started_at       = started_at,
            completed_at     = completed_at,
            duration_seconds = duration_seconds,
        )

    except Exception as exc:
        completed_at     = datetime.utcnow()
        duration_seconds = (completed_at - started_at).total_seconds()
        error_msg        = f"UnexpectedError: {exc}"

        logger.error(
            f"Unexpected error running task={task.task_id}: {exc}",
            extra={"event": "container_unexpected_error", "task_id": task.task_id, "error": error_msg},
        )

        return TaskResult(
            task_id          = task.task_id,
            worker_id        = worker_id,
            status           = TaskStatus.FAILED,
            output           = None,
            error            = error_msg,
            started_at       = started_at,
            completed_at     = completed_at,
            duration_seconds = duration_seconds,
        )
