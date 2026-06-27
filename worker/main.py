# worker/main.py

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from worker.health.registrar import build_node_info, start_registration
from worker.health.heartbeat import start_heartbeat
from worker.executor.task_queue import start_worker_loop, get_active_tasks
from worker.api.task_routes import router as task_router
from worker.api.storage_routes import router as storage_router
from worker.api.function_routes import router as function_router
from shared.logger import get_logger


# ── Build node identity once at startup ──────────────────────────────────────
#
# NODE_INFO is created at module level so every part of the worker
# shares the same node_id and ip — not a new UUID each time someone calls it.
#
NODE_INFO = build_node_info()
logger = get_logger("lifespan", node_id=NODE_INFO.node_id)


# ── Patch heartbeat to report live active_tasks count ────────────────────────
#
# The heartbeat loop reads NODE_INFO.active_tasks.  We override the attribute
# with a property-like approach: instead of mutating NODE_INFO every second,
# we monkey-patch the heartbeat payload builder to read from task_queue.
# This keeps task_queue.py as the single source of truth for the count.
#
# Implementation: we update NODE_INFO.active_tasks before each heartbeat post
# by hooking into the heartbeat module (done via the import — heartbeat.py
# reads node_info.active_tasks at call time, so we update it in the loop).
# Actually the simplest correct approach: override active_tasks as a readable
# value in the shared node_info by patching it in the heartbeat loop.
# See note in heartbeat.py: it calls node_info.active_tasks at each iteration.

# We expose a function so heartbeat.py can read the live count:
import worker.executor.task_queue as _tq

_original_collect = None


# ── Lifespan: runs startup/shutdown logic ────────────────────────────────────
#
# Everything BEFORE yield runs when uvicorn starts.
# Everything AFTER yield runs when uvicorn shuts down.
#
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        f"Starting up — node_id={NODE_INFO.node_id} ip={NODE_INFO.ip}",
        extra={"event": "startup"}
    )

    # Week 1: registration + heartbeat
    asyncio.create_task(start_registration(NODE_INFO))
    asyncio.create_task(start_heartbeat(NODE_INFO))

    # Week 2: task queue consumer loop
    # Pass the real node UUID so TaskResult.worker_id is accurate.
    asyncio.create_task(start_worker_loop(worker_id=NODE_INFO.node_id))

    logger.info(
        "Worker ready — registration, heartbeat, and task queue started.",
        extra={"event": "startup"},
    )

    yield

    logger.info(
        f"Shutting down — node_id={NODE_INFO.node_id}",
        extra={"event": "shutdown"}
    )


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="MiniCloud Worker", lifespan=lifespan)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health_check():
    """
    Simple liveness probe.
    The master (and you, during manual testing) can call this to confirm
    the worker process is alive and to check its identity.
    """
    return {
        "status":       "ok",
        "node_id":      NODE_INFO.node_id,
        "ip":           NODE_INFO.ip,
        "port":         NODE_INFO.port,
        "active_tasks": get_active_tasks(),
    }


# Week 2: task submission + status routes
app.include_router(task_router)

# Week 3: chunk storage + lambda invocation routes
app.include_router(storage_router)
app.include_router(function_router)

# Week 4: metrics route
from worker.metrics import worker_metrics_app
app.mount("/metrics", worker_metrics_app)
