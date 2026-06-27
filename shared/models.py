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


# ── Week 3: Storage models ────────────────────────────────────────────────────

class FileChunk(BaseModel):
    chunk_id:        str
    file_id:         str
    chunk_index:     int
    size_bytes:      int
    checksum:        str          # MD5 hex digest
    worker_id:       str          # primary replica worker
    replica_worker_id: Optional[str] = None  # second replica worker


class FileMetadata(BaseModel):
    file_id:            str
    filename:           str
    total_size:         int
    chunk_count:        int
    replication_factor: int = 2
    created_at:         datetime
    status:             str       # 'available' | 'degraded' | 'lost' | 'deleted'


# ── Week 3: Function (Lambda) models ─────────────────────────────────────────

class FunctionDef(BaseModel):
    function_id: str
    name:        str
    code:        str              # Python source as string
    runtime:     str = "python3.11"
    created_at:  datetime


class InvokeRequest(BaseModel):
    function_id:      str
    payload:          dict
    timeout_seconds:  int = 30


class InvokeResult(BaseModel):
    function_id:  str
    output:       Optional[str] = None
    error:        Optional[str] = None
    duration_ms:  int
    worker_id:    str


# ── Week 4: Log models ────────────────────────────────────────────────────────

class LogEntry(BaseModel):
    log_id:    str
    timestamp: datetime
    level:     str
    node_id:   str
    task_id:   Optional[str] = None
    message:   str
    extra:     Optional[dict] = None
