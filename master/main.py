# master/main.py
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from master.api.registry_routes import router as registry_router
from master.api.heartbeat_routes import router as heartbeat_router
from master.registry.health_monitor import monitor_nodes
from master.registry.node_registry import load_nodes_from_redis


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load nodes from Redis on startup
    load_nodes_from_redis()
    
    # Start health monitor background task
    monitor_task = asyncio.create_task(monitor_nodes())
    
    yield
    
    # Cleanup task on shutdown
    monitor_task.cancel()


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
