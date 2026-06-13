from fastapi import APIRouter, HTTPException
from shared.models import HeartbeatPayload
from master.registry.node_registry import update_node

router = APIRouter()

@router.post("/heartbeat")
def receive_heartbeat(payload: HeartbeatPayload):
    """
    Periodic heartbeat from worker nodes.
    Updates CPU, RAM, active tasks, and resets last_heartbeat.
    """
    success = update_node(payload.node_id, payload)
    
    if not success:
        # If node is not found, maybe it restarted and lost state? 
        # For now, just return an error so the worker knows to re-register.
        raise HTTPException(status_code=404, detail="Node not registered. Please register first.")
        
    return {"message": "Heartbeat received successfully."}
