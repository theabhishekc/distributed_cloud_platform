# shared/log_aggregator.py
import asyncio
import uuid
from datetime import datetime
from typing import Dict, Any, Optional

from master.db.models import LogDB
from master.db.database import get_db


async def write_log_to_db(log_entry: dict, db_session) -> None:
    """
    Inserts a log entry into the Logs table.
    
    Log schema: log_id (UUID), timestamp, level, node_id, task_id (nullable), message, extra (JSONB)
    """
    log_id = log_entry.get("log_id") or str(uuid.uuid4())
    
    timestamp_raw = log_entry.get("timestamp")
    if isinstance(timestamp_raw, datetime):
        timestamp = timestamp_raw
    elif isinstance(timestamp_raw, str):
        try:
            timestamp = datetime.fromisoformat(timestamp_raw.replace("Z", "+00:00"))
            timestamp = timestamp.replace(tzinfo=None)
        except Exception:
            timestamp = datetime.utcnow()
    else:
        timestamp = datetime.utcnow()

    level   = log_entry.get("level", "INFO")
    node_id = log_entry.get("node_id", "unknown")
    task_id = log_entry.get("task_id")
    message = log_entry.get("message", "")
    extra   = log_entry.get("extra", {})

    db_log = LogDB(
        log_id=log_id,
        timestamp=timestamp,
        level=level,
        node_id=node_id,
        task_id=task_id,
        message=message,
        extra=extra,
    )
    db_session.add(db_log)
    await db_session.commit()


async def write_log_to_db_fire_and_forget(log_entry: dict) -> None:
    """
    Helper coroutine to open a DB session and call write_log_to_db.
    Used by shared/logger.py for fire-and-forget background execution.
    """
    try:
        async with get_db() as session:
            await write_log_to_db(log_entry, session)
    except Exception:
        # Suppress errors in fire-and-forget log aggregation so they never crash the app
        pass
