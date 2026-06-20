# master/main.py
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from master.api.registry_routes import router as registry_router
from master.api.heartbeat_routes import router as heartbeat_router
from master.registry.health_monitor import monitor_nodes
from master.registry.node_registry import load_nodes_from_redis
from shared.logger import get_logger

logger = get_logger("master", node_id="master")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Master node starting up...", extra={"event": "startup"})

    # Load healthy nodes from Redis on startup
    load_nodes_from_redis()

    # Start health monitor background task
    monitor_task = asyncio.create_task(monitor_nodes())

    logger.info("Master node ready. Listening for worker registrations.", extra={"event": "startup"})

    yield

    # Cleanup task on shutdown
    monitor_task.cancel()
    logger.info("Master node shutting down.", extra={"event": "shutdown"})


app = FastAPI(
    title="Mini Distributed Cloud Platform - Master Node",
    lifespan=lifespan
)

app.include_router(registry_router)
app.include_router(heartbeat_router)

@app.get("/health")
def health():
    return {
        "status": "ok",
        "node": "master"
    }
