# worker/health/heartbeat.py

import asyncio
from datetime import datetime
import httpx
import psutil

from worker.config import MASTER_BASE_URL
from shared.models import NodeInfo, HeartbeatPayload

from shared.logger import get_logger

# Initialize CPU measurement comparison times
psutil.cpu_percent(interval=None)


def collect_metrics() -> tuple[float, float]:
    """
    Collect current system resource usage.
    Returns (cpu_percent, ram_percent).
    
    Using interval=None ensures this call is non-blocking (doesn't block the async loop).
    It calculates utilization relative to the last time cpu_percent was called.
    """
    cpu = psutil.cpu_percent(interval=None)
    ram = psutil.virtual_memory().percent
    return cpu, ram


async def start_heartbeat(node_info: NodeInfo) -> None:
    """
    Background loop that runs forever. Every 5 seconds, it:
      1. Collects system resource metrics (CPU and RAM).
      2. Prints the metrics locally to verify they look real.
      3. Builds a HeartbeatPayload.
      4. POSTs the payload to master:8000/heartbeat.
      5. Catches and logs errors without crashing if the request fails.
    """
    url = f"{MASTER_BASE_URL}/heartbeat"
    logger = get_logger("heartbeat", node_id=node_info.node_id)
    logger.info(
        f"Starting heartbeat sender to master at {url} (interval: 5s)...",
        extra={"event": "heartbeat_sender_started"}
    )

    consecutive_failures = 0

    while True:
        try:
            # 1. Collect metrics
            cpu, ram = collect_metrics()
            
            # 2. Build HeartbeatPayload
            payload = HeartbeatPayload(
                node_id=node_info.node_id,
                ip=node_info.ip,
                cpu_percent=cpu,
                ram_percent=ram,
                active_tasks=node_info.active_tasks,
                timestamp=datetime.utcnow()
            )

            # 3. POST to master
            # timeout=10s — Windows LAN can spike above 3s (Wi-Fi, Defender, etc.)
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    url,
                    json=payload.model_dump(mode="json")
                )
                if response.status_code == 200:
                    consecutive_failures = 0
                    logger.info(
                        f"Heartbeat sent successfully. Metrics -> CPU: {cpu:.1f}%, RAM: {ram:.1f}%",
                        extra={"event": "beat_sent", "cpu": cpu, "ram": ram}
                    )
                else:
                    consecutive_failures += 1
                    logger.warning(
                        f"Master returned status code {response.status_code} for heartbeat (consecutive failures: {consecutive_failures})",
                        extra={"event": "beat_warning", "status_code": response.status_code, "consecutive_failures": consecutive_failures}
                    )

        except httpx.ConnectError:
            logger.error(
                f"Master unreachable at {MASTER_BASE_URL}",
                extra={"event": "beat_connect_error"}
            )
        except httpx.TimeoutException:
            consecutive_failures += 1
            logger.error(
                f"Heartbeat timed out (timeout=10s, consecutive failures: {consecutive_failures})",
                extra={"event": "beat_timeout_error", "consecutive_failures": consecutive_failures}
            )
        except Exception as e:
            logger.error(
                f"Unexpected error in heartbeat loop: {e}",
                extra={"event": "beat_unexpected_error", "error": str(e)}
            )

        # Wait 5 seconds before next heartbeat
        await asyncio.sleep(5)
