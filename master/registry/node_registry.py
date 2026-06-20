# master/registry/node_registry.py

import json
import redis
from datetime import datetime
from typing import Dict, List

from shared.models import (
    NodeInfo,
    HeartbeatPayload
)

from shared.logger import get_logger

nodes: Dict[str, NodeInfo] = {}
logger = get_logger("node_registry", node_id="master")

# Initialize Redis client.
# protocol=2 → forces RESP2 (works with Redis 5.x and 6.x+).
# redis-py v4+ defaults to RESP3 (HELLO 3) which breaks on older Redis versions.
try:
    redis_client = redis.Redis(
        host='localhost',
        port=6379,
        db=0,
        decode_responses=True,
        protocol=2,          # ← RESP2: compatible with Redis 5.x and above
    )
    redis_client.ping()      # validate connection is actually alive at startup
    logger.info("Redis connected successfully.", extra={"event": "redis_connected"})
except Exception as e:
    logger.warning(
        f"Redis unavailable — running without persistence: {e}",
        extra={"event": "redis_init_failed", "error": str(e)}
    )
    redis_client = None

def load_nodes_from_redis():
    """
    Load existing HEALTHY nodes from Redis on startup.
    Dead nodes from previous sessions are skipped — they will re-register
    if still alive, or stay gone if not. This prevents ghost dead-node
    warnings flooding the log on every master restart.
    """
    if not redis_client:
        return

    try:
        redis_nodes = redis_client.hgetall("nodes")
        loaded = 0
        skipped_dead = 0
        for node_id, node_json in redis_nodes.items():
            node_data = json.loads(node_json)
            if node_data.get("status") == "dead":
                skipped_dead += 1
                continue  # don't load dead nodes from previous sessions
            nodes[node_id] = NodeInfo(**node_data)
            loaded += 1
        logger.info(
            f"Loaded {loaded} healthy node(s) from Redis. Skipped {skipped_dead} dead node(s).",
            extra={"event": "redis_load_success", "node_count": loaded, "skipped_dead": skipped_dead}
        )
    except Exception as e:
        logger.error(f"Error loading nodes from Redis: {e}", extra={"event": "redis_load_error", "error": str(e)})

def add_node(node_info: NodeInfo) -> None:
    """
    Add a new node to the registry or update it if it exists.
    """
    is_new = node_info.node_id not in nodes
    nodes[node_info.node_id] = node_info

    action = "registered" if is_new else "re-registered"
    logger.info(
        f"Node [{node_info.node_id[-8:]}] {action} from {node_info.ip}:{node_info.port}",
        extra={"event": "node_registered", "node_id": node_info.node_id, "ip": node_info.ip, "action": action}
    )

    if redis_client:
        try:
            redis_client.hset("nodes", node_info.node_id, node_info.model_dump_json())
        except Exception as e:
            logger.error(f"Error saving node to Redis: {e}", extra={"event": "redis_save_error", "node_id": node_info.node_id, "error": str(e)})


def remove_node(node_id: str) -> None:
    """
    Remove a node from the registry by its node_id.
    """
    nodes.pop(node_id, None)
    
    if redis_client:
        try:
            redis_client.hdel("nodes", node_id)
        except Exception as e:
            logger.error(f"Error removing node from Redis: {e}", extra={"event": "redis_remove_error", "node_id": node_id, "error": str(e)})


def get_all_nodes() -> List[NodeInfo]:
    """
    Retrieve all registered nodes.
    """
    return list(nodes.values())


def get_healthy_nodes() -> List[NodeInfo]:
    """
    Retrieve all healthy registered nodes.
    """
    return [
        node
        for node in nodes.values()
        if node.status == "healthy"
    ]


def update_node(
    node_id: str,
    heartbeat: HeartbeatPayload
) -> bool:
    """
    Update a node's heartbeat information.
    Uses the MASTER's clock (datetime.utcnow()) for last_heartbeat — not the
    worker's clock — to avoid false dead-detection from clock skew between machines.
    """
    node = nodes.get(node_id)

    if not node:
        return False

    node.cpu_percent    = heartbeat.cpu_percent
    node.ram_percent    = heartbeat.ram_percent
    node.active_tasks   = heartbeat.active_tasks
    node.status         = "healthy"
    node.last_heartbeat = datetime.utcnow()  # use MASTER clock, not worker's

    if redis_client:
        try:
            redis_client.hset("nodes", node.node_id, node.model_dump_json())
        except Exception as e:
            logger.error(f"Error updating node in Redis: {e}", extra={"event": "redis_update_error", "node_id": node.node_id, "error": str(e)})

    return True