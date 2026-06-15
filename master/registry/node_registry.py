# master/registry/node_registry.py

import json
import redis
from typing import Dict, List

from shared.models import (
    NodeInfo,
    HeartbeatPayload
)

from shared.logger import get_logger

nodes: Dict[str, NodeInfo] = {}
logger = get_logger("node_registry", node_id="master")

# Initialize Redis client. For a production app, these values would come from env vars.
try:
    redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
except Exception as e:
    logger.warning(f"Failed to initialize Redis client: {e}", extra={"event": "redis_init_failed", "error": str(e)})
    redis_client = None

def load_nodes_from_redis():
    """
    Load existing nodes from Redis on startup.
    """
    if not redis_client:
        return
    
    try:
        redis_nodes = redis_client.hgetall("nodes")
        for node_id, node_json in redis_nodes.items():
            node_data = json.loads(node_json)
            nodes[node_id] = NodeInfo(**node_data)
        logger.info(f"Loaded {len(nodes)} nodes from Redis.", extra={"event": "redis_load_success", "node_count": len(nodes)})
    except Exception as e:
        logger.error(f"Error loading nodes from Redis: {e}", extra={"event": "redis_load_error", "error": str(e)})

def add_node(node_info: NodeInfo) -> None:
    """
    Add a new node to the registry or update it if it exists.
    """
    nodes[node_info.node_id] = node_info
    
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
    """
    node = nodes.get(node_id)

    if not node:
        return False

    node.cpu_percent = heartbeat.cpu_percent
    node.ram_percent = heartbeat.ram_percent
    node.active_tasks = heartbeat.active_tasks
    node.status = "healthy"
    # last_heartbeat will be updated in the caller or here? The request says:
    # "Updates node's cpu_percent, ram_percent, active_tasks, last_heartbeat = datetime.now()"
    # But wait, heartbeat payload has a timestamp. Let's use the payload timestamp or datetime.utcnow().
    # The requirement says: last_heartbeat = datetime.now()
    # Actually `node.last_heartbeat` should be updated.
    
    node.last_heartbeat = heartbeat.timestamp
    
    if redis_client:
        try:
            redis_client.hset("nodes", node.node_id, node.model_dump_json())
        except Exception as e:
            logger.error(f"Error updating node in Redis: {e}", extra={"event": "redis_update_error", "node_id": node.node_id, "error": str(e)})

    return True