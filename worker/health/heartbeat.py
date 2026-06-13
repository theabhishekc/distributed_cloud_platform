# worker/health/heartbeat.py

import asyncio
from datetime import datetime
import httpx
import psutil

from worker.config import MASTER_BASE_URL
from shared.models import NodeInfo, HeartbeatPayload

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
    print(f"[heartbeat] Starting heartbeat sender to master at {url} (interval: 5s)...")

    while True:
        try:
            # 1. Collect metrics
            cpu, ram = collect_metrics()
            
            # 2. Print metrics locally for verification
            print(f"[heartbeat] Collected metrics -> CPU: {cpu:.1f}%, RAM: {ram:.1f}%")

            # 3. Build HeartbeatPayload
            payload = HeartbeatPayload(
                node_id=node_info.node_id,
                ip=node_info.ip,
                cpu_percent=cpu,
                ram_percent=ram,
                active_tasks=node_info.active_tasks,
                timestamp=datetime.utcnow()
            )

            # 4. POST to master
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.post(
                    url,
                    json=payload.model_dump(mode="json")
                )
                if response.status_code == 200:
                    # Successful beat sent
                    pass
                else:
                    print(
                        f"[heartbeat] Warning: Master returned status code {response.status_code} for heartbeat"
                    )

        except httpx.ConnectError:
            print(f"[heartbeat] Error: Master unreachable at {MASTER_BASE_URL}")
        except httpx.TimeoutException:
            print(f"[heartbeat] Error: Request to master timed out")
        except Exception as e:
            print(f"[heartbeat] Unexpected error in heartbeat loop: {e}")

        # Wait 5 seconds before next heartbeat
        await asyncio.sleep(5)
