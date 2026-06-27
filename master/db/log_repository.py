# master/db/log_repository.py
from datetime import datetime
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from master.db.models import LogDB
from shared.models import LogEntry


async def query_logs(
    session: AsyncSession,
    node_id: Optional[str] = None,
    task_id: Optional[str] = None,
    level: Optional[str] = None,
    since: Optional[datetime] = None,
    limit: int = 100,
) -> List[LogEntry]:
    """
    Query aggregated logs across the cluster with filtering options.
    """
    stmt = select(LogDB).order_by(LogDB.timestamp.desc())

    if node_id:
        stmt = stmt.where(LogDB.node_id == node_id)
    if task_id:
        stmt = stmt.where(LogDB.task_id == task_id)
    if level:
        stmt = stmt.where(LogDB.level == level)
    if since:
        stmt = stmt.where(LogDB.timestamp >= since)

    stmt = stmt.limit(limit)
    result = await session.execute(stmt)
    db_logs = result.scalars().all()

    return [
        LogEntry(
            log_id=log.log_id,
            timestamp=log.timestamp,
            level=log.level,
            node_id=log.node_id,
            task_id=log.task_id,
            message=log.message,
            extra=log.extra,
        )
        for log in db_logs
    ]
