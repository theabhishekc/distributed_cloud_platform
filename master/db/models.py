# master/db/models.py
#
# SQLAlchemy 2.x async declarative ORM models.
# Week 2: Task table
# Week 3: FileMetadata, FileChunk, FunctionDef tables
#
# Design: Pydantic models (shared/models.py) = validation / API surface.
#         SQLAlchemy models (here)            = DB persistence layer.
# These are intentionally kept separate — see PROJECT_CONTEXT.md.

import enum
from datetime import datetime

from sqlalchemy import (
    Column, String, Float, Integer, DateTime, Text,
    ForeignKey, Enum as SAEnum, BigInteger, JSON,
)
from sqlalchemy.orm import DeclarativeBase, relationship


# ── Declarative base ──────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


# ── TaskStatusDB ──────────────────────────────────────────────────────────────

class TaskStatusDB(str, enum.Enum):
    PENDING    = "PENDING"
    SCHEDULED  = "SCHEDULED"
    RUNNING    = "RUNNING"
    COMPLETED  = "COMPLETED"
    FAILED     = "FAILED"
    CANCELLED  = "CANCELLED"


# ── Task ──────────────────────────────────────────────────────────────────────

class Task(Base):
    """
    Persists every task submitted to the platform.

    Lifecycle:
      PENDING → (scheduler picks worker) → SCHEDULED
             → (worker starts container) → RUNNING
             → (container exits 0)       → COMPLETED
             → (container exits non-0)   → FAILED
             → (client cancels)          → CANCELLED
    """
    __tablename__ = "tasks"

    task_id            = Column(String(36),  primary_key=True, nullable=False)
    image              = Column(String(255), nullable=False)
    command            = Column(Text,        nullable=False)
    cpu_limit          = Column(Float,       nullable=False, default=0.5)
    ram_limit_mb       = Column(Integer,     nullable=False, default=256)
    priority           = Column(Integer,     nullable=False, default=1)
    retry_count        = Column(Integer,     nullable=False, default=0)
    max_retries        = Column(Integer,     nullable=False, default=3)
    status             = Column(
        SAEnum(TaskStatusDB, name="taskstatus", create_type=True),
        nullable=False,
        default=TaskStatusDB.PENDING,
    )
    assigned_worker_id = Column(String(36),  nullable=True)
    output             = Column(Text,        nullable=True)
    error              = Column(Text,        nullable=True)
    created_at         = Column(DateTime,    nullable=False, default=datetime.utcnow)
    started_at         = Column(DateTime,    nullable=True)
    completed_at       = Column(DateTime,    nullable=True)
    duration_seconds   = Column(Float,       nullable=True)

    def __repr__(self) -> str:
        return f"<Task id={self.task_id!r} image={self.image!r} status={self.status!r}>"


# ── Week 3: FileMetadata ──────────────────────────────────────────────────────

class FileMetadataDB(Base):
    """
    Tracks uploaded files.  A file is made of 1+ FileChunk records.

    status:
      'available' — all chunks present on the required number of replicas
      'degraded'  — some chunks are under-replicated (replication monitor will fix)
      'lost'      — all replicas of at least one chunk are gone (unrecoverable)
      'deleted'   — client deleted the file; chunks cleaned up
    """
    __tablename__ = "file_metadata"

    file_id            = Column(String(36),  primary_key=True, nullable=False)
    filename           = Column(String(512), nullable=False)
    total_size         = Column(BigInteger,  nullable=False)   # bytes
    chunk_count        = Column(Integer,     nullable=False)
    replication_factor = Column(Integer,     nullable=False, default=2)
    created_at         = Column(DateTime,    nullable=False, default=datetime.utcnow)
    status             = Column(String(20),  nullable=False, default="available")

    # ORM relationship — convenient for cascade deletes in tests
    chunks             = relationship("FileChunkDB", back_populates="file",
                                      cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<FileMetadata id={self.file_id!r} name={self.filename!r} status={self.status!r}>"


# ── Week 3: FileChunk ─────────────────────────────────────────────────────────

class FileChunkDB(Base):
    """
    Represents one 1MB slice of an uploaded file.

    worker_id:         node_id of the primary replica
    replica_worker_id: node_id of the second replica (replication_factor=2)
    checksum:          MD5 hex digest — verified on both upload and download
    """
    __tablename__ = "file_chunks"

    chunk_id          = Column(String(36),  primary_key=True, nullable=False)
    file_id           = Column(String(36),  ForeignKey("file_metadata.file_id", ondelete="CASCADE"),
                               nullable=False)
    chunk_index       = Column(Integer,     nullable=False)
    size_bytes        = Column(Integer,     nullable=False)
    checksum          = Column(String(32),  nullable=False)   # MD5 hex = 32 chars
    worker_id         = Column(String(36),  nullable=False)   # primary replica
    replica_worker_id = Column(String(36),  nullable=True)    # second replica

    file              = relationship("FileMetadataDB", back_populates="chunks")

    def __repr__(self) -> str:
        return (
            f"<FileChunk id={self.chunk_id!r} file={self.file_id!r} "
            f"idx={self.chunk_index} worker={self.worker_id!r}>"
        )


# ── Week 3: FunctionDef ───────────────────────────────────────────────────────

class FunctionDefDB(Base):
    """
    Stores a serverless function definition (Lambda-equivalent).

    code:    Full Python source as a text string.
    runtime: Docker image tag to use for execution (default: python3.11).
    """
    __tablename__ = "functions"

    function_id = Column(String(36),  primary_key=True, nullable=False)
    name        = Column(String(255), nullable=False)
    code        = Column(Text,        nullable=False)
    runtime     = Column(String(50),  nullable=False, default="python3.11")
    created_at  = Column(DateTime,    nullable=False, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<FunctionDef id={self.function_id!r} name={self.name!r}>"


# ── Week 4: Log ───────────────────────────────────────────────────────────────

class LogDB(Base):
    """
    Stores structured log entries aggregated from all nodes across the cluster.
    """
    __tablename__ = "logs"

    log_id     = Column(String(36),  primary_key=True, nullable=False)
    timestamp  = Column(DateTime,    nullable=False, default=datetime.utcnow)
    level      = Column(String(20),  nullable=False)
    node_id    = Column(String(36),  nullable=False)
    task_id    = Column(String(36),  nullable=True)
    message    = Column(Text,        nullable=False)
    extra      = Column(JSON,        nullable=True)

    def __repr__(self) -> str:
        return f"<Log id={self.log_id!r} level={self.level!r} node={self.node_id!r}>"
