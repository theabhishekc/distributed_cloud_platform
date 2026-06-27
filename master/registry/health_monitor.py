import asyncio
from datetime import datetime, timezone

from master.registry.node_registry import nodes, redis_client
from shared.logger import get_logger

logger = get_logger("health_monitor", node_id="master")

async def monitor_nodes():
    """
    Background task to monitor node health.
    Checks every 5 seconds.

    Dead threshold: 30s (= 6 missed heartbeat intervals).
    We use 30s instead of 15s because:
      - Heartbeat timeout is 10s (Windows LAN can spike).
      - A single slow request used to eat the entire 15s budget and
        cause false-positive dead detection.
    """
    DEAD_THRESHOLD_SECONDS = 30

    while True:
        try:
            now = datetime.utcnow()
            healthy_count = 0

            for node_id, node in list(nodes.items()):
                if node.last_heartbeat:
                    delta = now - node.last_heartbeat

                    if delta.total_seconds() > DEAD_THRESHOLD_SECONDS:
                        if node.status != "dead":
                            logger.warning(
                                f"Node {node_id} is dead. Last heartbeat was {delta.total_seconds():.1f}s ago.",
                                extra={
                                    "event": "node_dead",
                                    "dead_node_id": node_id,
                                    "last_beat_seconds_ago": delta.total_seconds()
                                }
                            )
                            node.status = "dead"

                            if redis_client:
                                try:
                                    redis_client.hset("nodes", node.node_id, node.model_dump_json())
                                except Exception as e:
                                    logger.error(
                                        f"Error updating node status to dead in Redis: {e}",
                                        extra={"event": "redis_status_update_error", "dead_node_id": node.node_id, "error": str(e)}
                                    )
                    else:
                        if node.status == "healthy":
                            healthy_count += 1

            logger.debug(
                f"Health check complete. Healthy nodes: {healthy_count}/{len(nodes)}",
                extra={"event": "health_check_done", "healthy": healthy_count, "total": len(nodes)}
            )

            from master.metrics import update_node_metrics
            update_node_metrics(nodes)

        except Exception as e:
            logger.error(f"Error in health monitor: {e}", extra={"event": "health_monitor_error", "error": str(e)})

        await asyncio.sleep(5)
