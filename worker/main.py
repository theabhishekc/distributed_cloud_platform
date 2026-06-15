# worker/main.py

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from worker.health.registrar import build_node_info, start_registration
from worker.health.heartbeat import start_heartbeat
from shared.logger import get_logger


# ── Build node identity once at startup ──────────────────────────────────────
#
# NODE_INFO is created at module level so every part of the worker
# shares the same node_id and ip — not a new UUID each time someone calls it.
#
NODE_INFO = build_node_info()
logger = get_logger("lifespan", node_id=NODE_INFO.node_id)


# ── Lifespan: runs startup/shutdown logic ────────────────────────────────────
#
# Everything BEFORE yield runs when uvicorn starts.
# Everything AFTER yield runs when uvicorn shuts down.
# asyncio.create_task() kicks off registration in the background —
# the worker immediately starts accepting requests without waiting.
#
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        f"Starting up — node_id={NODE_INFO.node_id} ip={NODE_INFO.ip}",
        extra={"event": "startup"}
    )
    asyncio.create_task(start_registration(NODE_INFO))
    asyncio.create_task(start_heartbeat(NODE_INFO))
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
        "status": "ok",
        "node_id": NODE_INFO.node_id,
        "ip": NODE_INFO.ip,
        "port": NODE_INFO.port,
    }
