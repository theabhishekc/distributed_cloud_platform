from fastapi import APIRouter, HTTPException
from shared.models import HeartbeatPayload
from master.registry.node_registry import update_node
from shared.logger import get_logger

router = APIRouter()
logger = get_logger("heartbeat", node_id="master")

@router.post("/heartbeat")
def receive_heartbeat(payload: HeartbeatPayload):
    """
    Periodic heartbeat from worker nodes.
    Updates CPU, RAM, active tasks, and resets last_heartbeat.
    """
    success = update_node(payload.node_id, payload)

    if not success:
        # Node not in registry — it likely restarted. Tell it to re-register.
        raise HTTPException(status_code=404, detail="Node not registered. Please register first.")

    logger.info(
        f"CPU: {payload.cpu_percent:.1f}%  RAM: {payload.ram_percent:.1f}%",
        extra={
            "event":      "beat_received",
            "cpu":        payload.cpu_percent,
            "ram":        payload.ram_percent,
            "node_id":    payload.node_id,
            "active_tasks": payload.active_tasks,
        }
    )

    return {"message": "Heartbeat received successfully."}
