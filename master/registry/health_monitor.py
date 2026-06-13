import asyncio
from datetime import datetime, timezone
import logging

from master.registry.node_registry import nodes, redis_client

logger = logging.getLogger(__name__)

async def monitor_nodes():
    """
    Background task to monitor node health.
    Checks every 5 seconds. Marks node as dead if heartbeat is older than 15 seconds.
    """
    while True:
        try:
            now = datetime.now(timezone.utc)
            # Remove tzinfo for comparison if models are using naive datetimes
            # Actually, `datetime.utcnow()` was used as default. So we use `datetime.utcnow()`
            now = datetime.utcnow()
            
            for node_id, node in list(nodes.items()):
                # Calculate time since last heartbeat
                if node.last_heartbeat:
                    # Depending on if they are naive or aware, we'll try to just subtract them.
                    # Since default_factory=datetime.utcnow, they are naive.
                    delta = now - node.last_heartbeat
                    if delta.total_seconds() > 15:
                        if node.status != "dead":
                            logger.warning(f"Node {node_id} is dead. Last heartbeat was {delta.total_seconds():.1f}s ago.")
                            node.status = "dead"
                            
                            # Update Redis
                            if redis_client:
                                try:
                                    redis_client.hset("nodes", node.node_id, node.model_dump_json())
                                except Exception as e:
                                    logger.error(f"Error updating node status to dead in Redis: {e}")
        except Exception as e:
            logger.error(f"Error in health monitor: {e}")
            
        await asyncio.sleep(5)
