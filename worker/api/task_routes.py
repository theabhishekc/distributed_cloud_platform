# worker/api/task_routes.py
#
# FastAPI routes for task submission and retrieval on the worker node.
#
# The worker does NOT talk to the DB directly — it only:
#   1. Accepts a TaskRequest → enqueues it → returns 202.
#   2. Returns the current TaskResult from RESULT_STORE.
#   3. Accepts a DELETE (cancel signal) from the master — marks cancelled in store.
#
# The master is the source of truth for task state (PostgreSQL).
# The worker's RESULT_STORE is ephemeral: restart clears it.

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException

from shared.logger import get_logger
from shared.models import TaskRequest, TaskResult, TaskStatus
from worker.config import WORKER_NODE_ID
from worker.executor.task_queue import enqueue_task, get_result, RESULT_STORE

router = APIRouter(prefix="/tasks", tags=["tasks"])
logger = get_logger("task_routes", node_id=WORKER_NODE_ID)


# ── POST /tasks ───────────────────────────────────────────────────────────────

@router.post("", status_code=202)
async def submit_task(task: TaskRequest) -> dict:
    """
    Enqueue a task for Docker execution.

    The master always provides a task_id in the request body.
    Returns 202 Accepted immediately — the task runs asynchronously.
    """
    await enqueue_task(task)

    logger.info(
        f"Task [{task.task_id}] accepted for execution",
        extra={"event": "task_accepted", "task_id": task.task_id, "image": task.image},
    )

    return {
        "task_id": task.task_id,
        "status":  TaskStatus.PENDING.value,
        "message": "Task accepted and queued for execution.",
    }


# ── GET /tasks/{task_id} ──────────────────────────────────────────────────────

@router.get("/{task_id}")
async def get_task_status(task_id: str) -> TaskResult:
    """
    Return the current TaskResult for a task running on this worker.

    The master calls this while a task is RUNNING to get live status.
    Returns 404 if the task is unknown to this worker
    (it was never submitted here, or the worker restarted).
    """
    result = get_result(task_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Task {task_id!r} not found on this worker.",
        )
    return result


# ── DELETE /tasks/{task_id} ───────────────────────────────────────────────────

@router.delete("/{task_id}", status_code=200)
async def cancel_task(task_id: str) -> dict:
    """
    Best-effort cancel signal from the master.

    If the task is PENDING in the queue we mark it CANCELLED in RESULT_STORE.
    If it is already RUNNING (container active) we cannot forcibly kill it here
    without holding a container handle — we mark it CANCELLED and the
    task_queue worker will write a final FAILED result when the container exits.
    If the task is already COMPLETED or FAILED, we return 409.
    """
    result = get_result(task_id)

    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Task {task_id!r} not found on this worker.",
        )

    if result.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
        return {
            "task_id": task_id,
            "status":  result.status.value,
            "message": "Task already in terminal state; no action taken.",
        }

    # Mark as cancelled in store
    RESULT_STORE[task_id] = TaskResult(
        task_id          = task_id,
        worker_id        = result.worker_id,
        status           = TaskStatus.CANCELLED,
        output           = None,
        error            = "Cancelled by master request.",
        started_at       = result.started_at,
        completed_at     = datetime.utcnow(),
        duration_seconds = (datetime.utcnow() - result.started_at).total_seconds(),
    )

    logger.info(
        f"Task [{task_id}] marked CANCELLED by master request",
        extra={"event": "task_cancelled", "task_id": task_id},
    )

    return {
        "task_id": task_id,
        "status":  TaskStatus.CANCELLED.value,
        "message": "Cancel signal received. Task marked as cancelled.",
    }
