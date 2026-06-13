# master/api/registry_routes.py

from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any

from shared.models import NodeInfo
from master.registry.node_registry import (
    add_node,
    get_all_nodes,
    nodes
)

router = APIRouter()


@router.post("/nodes/register")
def register_node(node: NodeInfo) -> Dict[str, str]:
    """
    Register a new worker node in the master registry.
    """
    add_node(node)

    return {
        "message": "Node registered successfully",
        "node_id": node.node_id
    }


@router.get("/nodes")
def list_nodes() -> List[NodeInfo]:
    """
    Retrieve a list of all registered worker nodes.
    """
    return get_all_nodes()


@router.get("/nodes/{node_id}")
def get_node(node_id: str) -> NodeInfo:
    """
    Retrieve information about a specific node by its node_id.
    """
    node = nodes.get(node_id)

    if not node:
        raise HTTPException(
            status_code=404,
            detail="Node not found"
        )

    return node