# shared/models.py

from pydantic import BaseModel
from typing import Optional


class NodeInfo(BaseModel):
    id: str
    ip: str
    port: int
    cpu_percent: float
    ram_percent: float
    active_tasks: int
    status: str


class TaskRequest(BaseModel):
    task_id: str
    image: str
    command: str
    cpu_limit: float
    ram_limit: int


class TaskResult(BaseModel):
    task_id: str
    status: str
    output: Optional[str] = None
    error: Optional[str] = None
    worker_id: str


class HeartbeatPayload(BaseModel):
    node_id: str
    ip: str
    cpu_percent: float
    ram_percent: float
    active_tasks: int
    timestamp: str