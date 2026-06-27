# master/api/task_routes.py
#
# Master-side REST routes for task lifecycle management.
#
# Flow for POST /tasks:
#   1. Generate task_id UUID.
#   2. Create TaskRequest (validated by Pydantic).
#   3. Persist as PENDING in PostgreSQL.
#   4. Call scheduler.select_worker() → SchedulerDecision.
#   5. Forward to chosen worker via httpx POST /tasks.
#   6. Update DB to SCHEDULED (or FAILED if worker unreachable).
#   7. Return 202 with task_id.
#
# Flow for GET /tasks/{task_id}:
#   1. Fetch from DB.
#   2. If RUNNING, also poll worker GET /tasks/{task_id} for live status.
#   3. Return combined view.
#
# Flow for DELETE /tasks/{task_id}:
#   1. Mark CANCELLED in DB.
#   2. Forward DELETE to assigned worker (best-effort).
#
# Flow for GET /tasks:
#   1. list_tasks() with optional ?status= filter.
#   2. Return list.

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, HTTPException, Query

from master.db.database import get_db
from master.db import task_repository as task_repo
from master.scheduler.scheduler import NoHealthyNodeError, select_worker
from master.registry.node_registry import nodes
from shared.logger import get_logger
from shared.models import (
    SchedulerDecision,
    TaskRequest,
    TaskResult,
    TaskStatus,
)

router = APIRouter(prefix="/tasks", tags=["tasks"])
logger = get_logger("task_routes", node_id="master")

# Timeout for all inter-node HTTP calls (PROJECT_CONTEXT.md: httpx timeout=30)
WORKER_TIMEOUT = 30.0


# ── Helpers ───────────────────────────────────────────────────────────────────

def _worker_base_url(worker_id: str) -> str:
    """Resolve worker_id → http://ip:port base URL from the live registry."""
    node = nodes.get(worker_id)
    if node is None:
        raise HTTPException(
            status_code=503,
            detail=f"Worker {worker_id!r} not found in registry.",
        )
    return f"http://{node.ip}:{node.port}"


def _task_to_dict(task) -> Dict[str, Any]:
    """Convert SQLAlchemy Task ORM object → JSON-serializable dict."""
    return {
        "task_id":            task.task_id,
        "image":              task.image,
        "command":            task.command,
        "cpu_limit":          task.cpu_limit,
        "ram_limit_mb":       task.ram_limit_mb,
        "priority":           task.priority,
        "retry_count":        task.retry_count,
        "max_retries":        task.max_retries,
        "status":             task.status.value if task.status else None,
        "assigned_worker_id": task.assigned_worker_id,
        "output":             task.output,
        "error":              task.error,
        "created_at":         task.created_at.isoformat() if task.created_at else None,
        "started_at":         task.started_at.isoformat() if task.started_at else None,
        "completed_at":       task.completed_at.isoformat() if task.completed_at else None,
        "duration_seconds":   task.duration_seconds,
    }


# ── POST /tasks ───────────────────────────────────────────────────────────────

@router.post("", status_code=202)
async def submit_task(body: Dict[str, Any]) -> Dict[str, Any]:
    """
    Accept a task submission, schedule it to a worker, and return the task_id.

    Request body fields (all optional except image and command):
      image         str   — Docker image name (e.g. "alpine")
      command       str   — Command to run inside the container
      cpu_limit     float — CPU cores (default 0.5)
      ram_limit_mb  int   — RAM in MB (default 256)
      priority      int   — Scheduling priority (default 1)
      max_retries   int   — Max retry attempts on failure (default 3)
    """
    # Auto-generate task_id
    task_id = str(uuid.uuid4())

    # Build and validate the TaskRequest
    try:
        task = TaskRequest(
            task_id      = task_id,
            image        = body["image"],
            command      = body["command"],
            cpu_limit    = float(body.get("cpu_limit",   0.5)),
            ram_limit_mb = int(body.get("ram_limit_mb",  256)),
            priority     = int(body.get("priority",      1)),
            retry_count  = 0,
            max_retries  = int(body.get("max_retries",   3)),
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid task payload: {exc}")

    # 1. Persist as PENDING
    async with get_db() as session:
        db_task = await task_repo.create_task(session, task)

    # 2. Schedule
    try:
        decision: SchedulerDecision = select_worker(task)
    except NoHealthyNodeError as exc:
        # Mark as FAILED immediately — no workers available
        async with get_db() as session:
            await task_repo.update_task_status(
                session,
                task_id,
                status       = TaskStatus.FAILED,
                error        = str(exc),
                completed_at = datetime.utcnow(),
            )
        raise HTTPException(status_code=503, detail=str(exc))

    # 3. Forward to chosen worker
    worker_url = None
    try:
        worker_node = nodes.get(decision.chosen_worker_id)
        if worker_node is None:
            raise HTTPException(status_code=503, detail="Chosen worker disappeared from registry.")

        worker_url = f"http://{worker_node.ip}:{worker_node.port}"

        async with httpx.AsyncClient(timeout=WORKER_TIMEOUT) as client:
            resp = await client.post(
                f"{worker_url}/tasks",
                json=task.model_dump(mode="json"),
            )
            if resp.status_code not in (200, 201, 202):
                raise RuntimeError(
                    f"Worker returned HTTP {resp.status_code}: {resp.text}"
                )

        logger.info(
            f"Task [{task_id}] forwarded to worker [{decision.chosen_worker_id[-8:]}] "
            f"at {worker_url}",
            extra={
                "event":     "task_forwarded",
                "task_id":   task_id,
                "worker_id": decision.chosen_worker_id,
            },
        )

    except Exception as exc:
        # Worker unreachable — mark as FAILED, surface error
        async with get_db() as session:
            await task_repo.update_task_status(
                session,
                task_id,
                status       = TaskStatus.FAILED,
                error        = f"Failed to forward to worker: {exc}",
                completed_at = datetime.utcnow(),
            )
        raise HTTPException(
            status_code=503,
            detail=f"Worker unreachable: {exc}",
        )

    # 4. Update DB to SCHEDULED
    async with get_db() as session:
        await task_repo.update_task_status(
            session,
            task_id,
            status             = TaskStatus.SCHEDULED,
            assigned_worker_id = decision.chosen_worker_id,
        )

    logger.info(
        f"Task [{task_id}] scheduled → worker [{decision.chosen_worker_id[-8:]}] "
        f"score={decision.score:.4f}",
        extra={
            "event":     "task_scheduled",
            "task_id":   task_id,
            "worker_id": decision.chosen_worker_id,
            "score":     decision.score,
            "reason":    decision.reason,
        },
    )

    return {
        "task_id":   task_id,
        "status":    TaskStatus.SCHEDULED.value,
        "worker_id": decision.chosen_worker_id,
        "score":     decision.score,
        "reason":    decision.reason,
        "message":   "Task accepted and scheduled.",
    }


# ── GET /tasks ────────────────────────────────────────────────────────────────

@router.get("")
async def list_all_tasks(
    status: Optional[str] = Query(default=None, description="Filter by status (e.g. PENDING, RUNNING)")
) -> List[Dict[str, Any]]:
    """
    List all tasks, optionally filtered by ?status=<STATUS>.
    """
    filter_status = None
    if status:
        try:
            filter_status = TaskStatus(status.upper())
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown status {status!r}. Valid values: {[s.value for s in TaskStatus]}",
            )

    async with get_db() as session:
        tasks = await task_repo.list_tasks(session, status=filter_status)

    return [_task_to_dict(t) for t in tasks]


# ── GET /tasks/{task_id} ──────────────────────────────────────────────────────

@router.get("/{task_id}")
async def get_task(task_id: str) -> Dict[str, Any]:
    """
    Return the full task record.

    If the task is RUNNING, we also poll the assigned worker for a live
    TaskResult — this lets the client see real-time output/error before
    the container finishes.
    """
    async with get_db() as session:
        task = await task_repo.get_task(session, task_id)

    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id!r} not found.")

    result = _task_to_dict(task)

    # If RUNNING, poll worker for live status
    if task.status and task.status.value == TaskStatus.RUNNING.value and task.assigned_worker_id:
        try:
            worker_node = nodes.get(task.assigned_worker_id)
            if worker_node:
                worker_url = f"http://{worker_node.ip}:{worker_node.port}"
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.get(f"{worker_url}/tasks/{task_id}")
                    if resp.status_code == 200:
                        live = resp.json()
                        result["live_status"]   = live.get("status")
                        result["live_output"]   = live.get("output")
                        result["live_error"]    = live.get("error")
        except Exception:
            # Live poll failure is non-fatal — return DB state
            pass

    return result


# ── DELETE /tasks/{task_id} ───────────────────────────────────────────────────

@router.delete("/{task_id}", status_code=200)
async def cancel_task(task_id: str) -> Dict[str, Any]:
    """
    Cancel a task.
    - Updates DB to CANCELLED.
    - Forwards DELETE to assigned worker (best-effort, non-fatal if worker unreachable).
    """
    async with get_db() as session:
        task = await task_repo.get_task(session, task_id)

    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id!r} not found.")

    if task.status and task.status.value in (
        TaskStatus.COMPLETED.value,
        TaskStatus.FAILED.value,
        TaskStatus.CANCELLED.value,
    ):
        return {
            "task_id": task_id,
            "status":  task.status.value,
            "message": "Task already in terminal state; no action taken.",
        }

    # Mark cancelled in DB
    async with get_db() as session:
        await task_repo.cancel_task(session, task_id)

    # Forward cancel to worker if assigned
    if task.assigned_worker_id:
        try:
            worker_node = nodes.get(task.assigned_worker_id)
            if worker_node:
                worker_url = f"http://{worker_node.ip}:{worker_node.port}"
                async with httpx.AsyncClient(timeout=WORKER_TIMEOUT) as client:
                    await client.delete(f"{worker_url}/tasks/{task_id}")
        except Exception as exc:
            # Non-fatal — DB is already updated
            logger.warning(
                f"Could not forward cancel to worker for task [{task_id}]: {exc}",
                extra={"event": "cancel_forward_failed", "task_id": task_id, "error": str(exc)},
            )

    logger.info(
        f"Task [{task_id}] cancelled",
        extra={"event": "task_cancelled", "task_id": task_id},
    )

    return {
        "task_id": task_id,
        "status":  TaskStatus.CANCELLED.value,
        "message": "Task cancelled successfully.",
    }
