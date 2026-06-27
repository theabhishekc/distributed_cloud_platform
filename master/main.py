# master/main.py
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from master.api.registry_routes import router as registry_router
from master.api.heartbeat_routes import router as heartbeat_router
from master.api.task_routes import router as task_router
from master.api.storage_routes import router as storage_router
from master.api.function_routes import router as function_router
from master.api.log_routes import router as log_router
from master.registry.health_monitor import monitor_nodes
from master.registry.node_registry import load_nodes_from_redis
from master.db.database import create_tables
from master.scheduler.task_reaper import reap_tasks
from master.storage.replication_monitor import replication_monitor
from shared.logger import get_logger

logger = get_logger("master", node_id="master")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Master node starting up...", extra={"event": "startup"})

    # ── Week 2+3: create DB tables (idempotent — safe to run every startup) ──
    try:
        await create_tables()
    except Exception as exc:
        logger.warning(
            f"DB table creation failed (PostgreSQL may be unavailable): {exc}",
            extra={"event": "db_init_failed", "error": str(exc)},
        )

    # ── Week 1: Load healthy nodes from Redis on startup ─────────────────────
    load_nodes_from_redis()

    # ── Week 1: Background health monitor ────────────────────────────────────
    monitor_task = asyncio.create_task(monitor_nodes())

    # ── Week 2: Background task reaper ───────────────────────────────────────
    reaper_task = asyncio.create_task(reap_tasks())

    # ── Week 3: Background replication monitor ────────────────────────────────
    replication_task = asyncio.create_task(replication_monitor())

    logger.info(
        "Master node ready. Listening for registrations, tasks, uploads, and function invocations.",
        extra={"event": "startup"},
    )

    yield

    # Cleanup on shutdown
    monitor_task.cancel()
    reaper_task.cancel()
    replication_task.cancel()
    logger.info("Master node shutting down.", extra={"event": "shutdown"})


app = FastAPI(
    title="Mini Distributed Cloud Platform - Master Node",
    lifespan=lifespan,
)

# ── Week 1 routes ─────────────────────────────────────────────────────────────
app.include_router(registry_router)
app.include_router(heartbeat_router)

# ── Week 2 routes ─────────────────────────────────────────────────────────────
app.include_router(task_router)

# ── Week 3 routes ─────────────────────────────────────────────────────────────
app.include_router(storage_router)
app.include_router(function_router)

# ── Week 4 routes ─────────────────────────────────────────────────────────────
app.include_router(log_router)
from master.metrics import metrics_app
app.mount("/metrics", metrics_app)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "node":   "master",
    }
