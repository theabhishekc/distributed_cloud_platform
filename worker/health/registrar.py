# worker/health/registrar.py

import asyncio
import socket
import uuid
from datetime import datetime

import httpx

from worker.config import (
    MASTER_BASE_URL,
    WORKER_PORT,
    REGISTRATION_RETRY_INTERVAL_SECONDS,
)
from shared.models import NodeInfo


def get_lan_ip() -> str:
    """
    Detect the machine's real LAN IP — not 127.0.0.1.

    The trick: open a UDP socket and 'connect' to an external address.
    No data is actually sent. The OS picks the right network interface
    to route there, and getsockname() reads back that interface's IP.
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def build_node_info() -> NodeInfo:
    """
    Build this worker's NodeInfo once at startup.
    The node_id is a fresh UUID — unique per process run.
    cpu/ram start at 0.0 — the heartbeat sender updates these later.
    """
    return NodeInfo(
        node_id=str(uuid.uuid4()),
        ip=get_lan_ip(),
        port=WORKER_PORT,
        cpu_percent=0.0,
        ram_percent=0.0,
        active_tasks=0,
        status="healthy",
        last_heartbeat=datetime.utcnow(),
    )


from shared.logger import get_logger


async def _try_register(node_info: NodeInfo) -> bool:
    """
    Make a single POST attempt to the master's /nodes/register endpoint.
    Returns True on success, False on any failure.
    """
    url = f"{MASTER_BASE_URL}/nodes/register"
    logger = get_logger("registrar", node_id=node_info.node_id)

    try:
        # timeout=10s — matches heartbeat timeout; guards against Windows LAN latency spikes
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                url,
                json=node_info.model_dump(mode="json"),
            )
            return response.status_code == 200

    except httpx.ConnectError:
        logger.warning(
            f"Master unreachable at {MASTER_BASE_URL}",
            extra={"event": "connect_error", "url": url}
        )
        return False

    except httpx.TimeoutException:
        logger.warning(
            "Request to master timed out",
            extra={"event": "timeout_error", "url": url}
        )
        return False

    except Exception as e:
        logger.error(
            f"Unexpected error: {e}",
            extra={"event": "unexpected_error", "error": str(e)}
        )
        return False


async def start_registration(node_info: NodeInfo) -> None:
    """
    Keep trying to register with the master until it succeeds.
    Retries every REGISTRATION_RETRY_INTERVAL_SECONDS seconds.

    This runs as a background asyncio task — it never blocks
    the worker's API from accepting requests.
    """
    logger = get_logger("registrar", node_id=node_info.node_id)
    logger.info(
        f"Starting registration for node {node_info.node_id} at {node_info.ip}",
        extra={"event": "registration_started"}
    )

    while True:
        success = await _try_register(node_info)

        if success:
            logger.info(
                f"Registered with master as node-{node_info.node_id}",
                extra={"event": "registration_success"}
            )
            return  # done — exit the loop

        logger.warning(
            f"Registration failed. Retrying in {REGISTRATION_RETRY_INTERVAL_SECONDS}s...",
            extra={"event": "registration_failed_retry", "retry_interval": REGISTRATION_RETRY_INTERVAL_SECONDS}
        )
        await asyncio.sleep(REGISTRATION_RETRY_INTERVAL_SECONDS)
