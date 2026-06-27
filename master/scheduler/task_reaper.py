# master/scheduler/task_reaper.py
#
# Background task that runs every REAPER_INTERVAL_SECONDS (30s) and marks
# long-running tasks as FAILED.
#
# Rationale: A worker can crash mid-execution without sending a final status
# update.  Without the reaper, tasks stay in RUNNING forever.  The reaper
# provides a backstop: if a task has been RUNNING longer than
# REAPER_TIMEOUT_MINUTES (default: 10) it is almost certainly stuck.

import asyncio
import os
from datetime import datetime, timedelta

from master.db.database import get_db
from master.db.models import TaskStatusDB
from master.db.task_repository import list_tasks, update_task_status
from shared.logger import get_logger
from shared.models import TaskStatus

logger = get_logger("task_reaper", node_id="master")

# ── Configuration (env-overridable) ───────────────────────────────────────────

REAPER_INTERVAL_SECONDS: int = int(os.getenv("REAPER_INTERVAL_SECONDS", "30"))
REAPER_TIMEOUT_MINUTES:  int = int(os.getenv("REAPER_TIMEOUT_MINUTES",  "10"))


# ── Reaper loop ───────────────────────────────────────────────────────────────

async def reap_tasks() -> None:
    """
    Background coroutine.  Runs forever, sleeping REAPER_INTERVAL_SECONDS
    between each sweep.

    On each sweep:
      1. Open a DB session.
      2. Fetch all RUNNING tasks.
      3. For each task whose started_at is older than REAPER_TIMEOUT_MINUTES:
           - Compute elapsed duration.
           - Mark as FAILED with an explanatory error message.
           - Log task_id + elapsed duration.
    """
    logger.info(
        f"Task reaper started — interval={REAPER_INTERVAL_SECONDS}s "
        f"timeout={REAPER_TIMEOUT_MINUTES}min",
        extra={"event": "reaper_started"},
    )

    timeout_delta = timedelta(minutes=REAPER_TIMEOUT_MINUTES)

    while True:
        try:
            await _sweep(timeout_delta)
        except Exception as exc:
            # Never let an exception crash the reaper loop
            logger.error(
                f"Unexpected error in reaper sweep: {exc}",
                extra={"event": "reaper_error", "error": str(exc)},
            )

        await asyncio.sleep(REAPER_INTERVAL_SECONDS)


async def _sweep(timeout_delta: timedelta) -> None:
    """One reaper sweep: find and kill timed-out RUNNING tasks."""
    now = datetime.utcnow()
    cutoff = now - timeout_delta

    async with get_db() as session:
        running_tasks = await list_tasks(session, status=TaskStatus.RUNNING)

        reaped = 0
        for task in running_tasks:
            if task.started_at is None:
                # Defensive: shouldn't happen but skip to avoid crash
                continue

            if task.started_at <= cutoff:
                elapsed = (now - task.started_at).total_seconds()

                await update_task_status(
                    session,
                    task.task_id,
                    status       = TaskStatus.FAILED,
                    error        = (
                        f"Task reaped after {elapsed:.0f}s — exceeded "
                        f"timeout of {REAPER_TIMEOUT_MINUTES} minutes."
                    ),
                    completed_at     = now,
                    duration_seconds = elapsed,
                )

                logger.warning(
                    f"Task [{task.task_id}] reaped — "
                    f"ran for {elapsed:.0f}s (limit={REAPER_TIMEOUT_MINUTES * 60}s)",
                    extra={
                        "event":           "task_reaped",
                        "task_id":         task.task_id,
                        "elapsed_seconds": elapsed,
                        "worker_id":       task.assigned_worker_id,
                    },
                )
                reaped += 1

    if reaped > 0:
        logger.info(
            f"Reaper sweep complete — reaped {reaped} task(s).",
            extra={"event": "reaper_sweep_done", "reaped": reaped},
        )
    else:
        logger.debug(
            "Reaper sweep complete — no tasks to reap.",
            extra={"event": "reaper_sweep_done", "reaped": 0},
        )
