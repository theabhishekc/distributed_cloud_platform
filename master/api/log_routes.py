# master/api/log_routes.py
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from master.db.database import get_db
from master.db import log_repository
from shared.models import LogEntry
from shared.logger import get_logger

logger = get_logger("log_routes", node_id="master")
router = APIRouter(prefix="/logs", tags=["Logs"])


@router.get("", response_model=List[LogEntry])
async def get_logs(
    node_id: Optional[str] = Query(None, description="Filter by node ID"),
    task_id: Optional[str] = Query(None, description="Filter by task ID"),
    level: Optional[str] = Query(None, description="Filter by log level (e.g. INFO, ERROR)"),
    since: Optional[datetime] = Query(None, description="Filter logs since this timestamp"),
    limit: int = Query(100, ge=1, le=1000, description="Max number of logs to return"),
    session: AsyncSession = Depends(get_db),
):
    """
    Query aggregated logs from across the cluster.
    """
    logger.info(
        f"Querying logs — node_id={node_id} task_id={task_id} level={level} limit={limit}",
        extra={"event": "query_logs_request", "filter_node_id": node_id, "filter_task_id": task_id},
    )
    try:
        logs = await log_repository.query_logs(
            session=session,
            node_id=node_id,
            task_id=task_id,
            level=level,
            since=since,
            limit=limit,
        )
        return logs
    except Exception as exc:
        logger.error(f"Failed to query logs: {exc}", extra={"event": "query_logs_error", "error": str(exc)})
        raise HTTPException(status_code=500, detail=f"Failed to query logs: {exc}")
