# master/registry/node_registry.py

from typing import Dict, List

from shared.models import (
    NodeInfo,
    HeartbeatPayload
)

nodes: Dict[str, NodeInfo] = {}


def add_node(node_info: NodeInfo) -> None:
    """
    Add a new node to the registry or update it if it exists.
    """
    nodes[node_info.id] = node_info


def remove_node(node_id: str) -> None:
    """
    Remove a node from the registry by its node_id.
    """
    nodes.pop(node_id, None)


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

    return True