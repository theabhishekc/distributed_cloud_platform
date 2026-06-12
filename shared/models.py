# shared/models.py

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    SCHEDULED = "SCHEDULED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class NodeInfo(BaseModel):
    node_id: str                         # fixed: was 'id'
    ip: str
    port: int
    cpu_percent: float
    ram_percent: float
    active_tasks: int
    status: str
    last_heartbeat: datetime = Field(
        default_factory=datetime.utcnow)  # fixed: was missing


class HeartbeatPayload(BaseModel):
    node_id: str
    ip: str
    cpu_percent: float
    ram_percent: float
    active_tasks: int
    timestamp: datetime                  # fixed: was str


class TaskRequest(BaseModel):
    task_id: str
    image: str
    command: str
    cpu_limit: float = 0.5
    ram_limit_mb: int = 256              # fixed: was ram_limit
    priority: int = 1               # fixed: was missing
    retry_count: int = 0               # fixed: was missing
    max_retries: int = 3               # fixed: was missing


class TaskResult(BaseModel):
    task_id: str
    worker_id: str
    status: TaskStatus                   # fixed: was plain str
    output: Optional[str] = None
    error: Optional[str] = None
    started_at: datetime                 # fixed: was missing
    completed_at: datetime               # fixed: was missing
    duration_seconds: float              # fixed: was missing


class SchedulerDecision(BaseModel):
    task_id: str
    chosen_worker_id: str
    reason: str
    score: float
