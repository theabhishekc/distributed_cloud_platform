# worker/executor/task_queue.py
#
# Async task queue with a concurrency semaphore.
#
# Design:
#   - asyncio.Queue holds TaskRequest objects waiting to be executed.
#   - asyncio.Semaphore(MAX_CONCURRENT_TASKS) limits simultaneous containers.
#   - RESULT_STORE is a module-level dict {task_id: TaskResult} that is
#     populated as tasks finish.  It is read by worker/api/task_routes.py.
#   - active_tasks counter is updated atomically around semaphore acquire/release
#     so that heartbeat metrics stay accurate.
#
# Note on thread safety: asyncio is single-threaded per event loop.
# The counter and dict updates are atomic within the event loop.

import asyncio
from datetime import datetime
from typing import Dict, Optional

from shared.logger import get_logger
from shared.models import TaskRequest, TaskResult, TaskStatus
from worker.config import MAX_CONCURRENT_TASKS, WORKER_NODE_ID
from worker.executor.docker_runner import run_task

logger = get_logger("task_queue", node_id=WORKER_NODE_ID)

# ── Shared state ──────────────────────────────────────────────────────────────

# Task queue: unbounded — backpressure is handled by the semaphore.
_queue: asyncio.Queue = asyncio.Queue()

# Semaphore: cap concurrent container executions.
_semaphore: asyncio.Semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)

# Result store: populated when a task finishes (success or failure).
RESULT_STORE: Dict[str, TaskResult] = {}

# Tracks how many containers are actively running right now.
# Used by heartbeat for accurate active_tasks reporting.
_active_tasks: int = 0


# ── Public helpers ────────────────────────────────────────────────────────────

def get_active_tasks() -> int:
    """Return the current count of actively running Docker containers."""
    return _active_tasks


def get_result(task_id: str) -> Optional[TaskResult]:
    """Look up a completed/failed task result.  Returns None if not done yet."""
    return RESULT_STORE.get(task_id)


# ── Enqueue ───────────────────────────────────────────────────────────────────

async def enqueue_task(task: TaskRequest) -> None:
    """
    Put a task on the queue.

    Records a PENDING placeholder in RESULT_STORE immediately so that
    GET /tasks/{task_id} returns a meaningful status while the task waits.
    """
    now = datetime.utcnow()
    placeholder = TaskResult(
        task_id          = task.task_id,
        worker_id        = WORKER_NODE_ID,
        status           = TaskStatus.PENDING,
        output           = None,
        error            = None,
        started_at       = now,
        completed_at     = now,
        duration_seconds = 0.0,
    )
    RESULT_STORE[task.task_id] = placeholder
    await _queue.put(task)

    from worker.metrics import minicloud_worker_local_tasks_total
    minicloud_worker_local_tasks_total.labels(status="PENDING").inc()

    logger.info(
        f"Task [{task.task_id}] enqueued — queue_size={_queue.qsize()}",
        extra={
            "event":      "task_enqueued",
            "task_id":    task.task_id,
            "queue_size": _queue.qsize(),
        },
    )


# ── Worker loop ───────────────────────────────────────────────────────────────

async def start_worker_loop(worker_id: str) -> None:
    """
    Background coroutine started at worker startup.

    Continuously pulls tasks from _queue, acquires the semaphore (blocking
    when MAX_CONCURRENT_TASKS containers are already running), runs the
    container in docker_runner.run_task(), then stores the result and
    releases the semaphore.

    Args:
        worker_id: The full node_id UUID (from NODE_INFO).
                   Passed to docker_runner so the TaskResult carries the real id.
    """
    global _active_tasks

    logger.info(
        f"Task queue worker loop started (max_concurrent={MAX_CONCURRENT_TASKS})",
        extra={"event": "task_queue_started", "max_concurrent": MAX_CONCURRENT_TASKS},
    )

    while True:
        task: TaskRequest = await _queue.get()

        logger.info(
            f"Picked up task [{task.task_id}] from queue",
            extra={"event": "task_dequeued", "task_id": task.task_id},
        )

        # Fire off a coroutine to execute the task while keeping the
        # main loop free to pick up the next item.
        asyncio.create_task(_execute_task(task, worker_id))
        _queue.task_done()


async def _execute_task(task: TaskRequest, worker_id: str) -> None:
    """
    Acquire the semaphore → run container → store result → release semaphore.
    The semaphore ensures at most MAX_CONCURRENT_TASKS containers run at once.
    """
    global _active_tasks

    await _semaphore.acquire()
    _active_tasks += 1

    logger.info(
        f"Semaphore acquired for task [{task.task_id}] "
        f"(active={_active_tasks}/{MAX_CONCURRENT_TASKS})",
        extra={
            "event":        "task_execution_start",
            "task_id":      task.task_id,
            "active_tasks": _active_tasks,
        },
    )

    try:
        result: TaskResult = await run_task(task, worker_id)
    except Exception as exc:
        # docker_runner already returns FAILED on all expected errors.
        # This guard catches truly unexpected exceptions (import errors, etc.)
        now = datetime.utcnow()
        result = TaskResult(
            task_id          = task.task_id,
            worker_id        = worker_id,
            status           = TaskStatus.FAILED,
            output           = None,
            error            = f"Fatal executor error: {exc}",
            started_at       = now,
            completed_at     = now,
            duration_seconds = 0.0,
        )
    finally:
        _active_tasks -= 1
        _semaphore.release()

    RESULT_STORE[task.task_id] = result

    from worker.metrics import minicloud_worker_local_tasks_total, minicloud_worker_local_tasks_duration_seconds
    minicloud_worker_local_tasks_total.labels(status=result.status.value).inc()
    if result.status.value in ("COMPLETED", "FAILED") and result.duration_seconds:
        minicloud_worker_local_tasks_duration_seconds.observe(result.duration_seconds)

    logger.info(
        f"Task [{task.task_id}] finished — status={result.status.value} "
        f"duration={result.duration_seconds:.2f}s "
        f"(active={_active_tasks}/{MAX_CONCURRENT_TASKS})",
        extra={
            "event":            "task_execution_done",
            "task_id":          task.task_id,
            "status":           result.status.value,
            "duration_seconds": result.duration_seconds,
            "active_tasks":     _active_tasks,
        },
    )
