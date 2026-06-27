# master/db/function_repository.py
#
# Async CRUD for the FunctionDef table.
# Every function receives an AsyncSession — never creates its own.

from datetime import datetime
from typing import List, Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from master.db.models import FunctionDefDB
from shared.logger import get_logger
from shared.models import FunctionDef

logger = get_logger("function_repo", node_id="master")


async def create_function(
    session: AsyncSession, fn: FunctionDef
) -> FunctionDefDB:
    """Persist a new function definition."""
    db_fn = FunctionDefDB(
        function_id = fn.function_id,
        name        = fn.name,
        code        = fn.code,
        runtime     = fn.runtime,
        created_at  = datetime.utcnow(),
    )
    session.add(db_fn)
    await session.commit()
    await session.refresh(db_fn)
    logger.info(
        f"Function [{fn.function_id}] stored — name={fn.name!r} runtime={fn.runtime!r}",
        extra={"event": "function_created", "function_id": fn.function_id, "fn_name": fn.name},
    )
    return db_fn


async def get_function(
    session: AsyncSession, function_id: str
) -> Optional[FunctionDefDB]:
    """Return FunctionDefDB or None if not found."""
    result = await session.execute(
        select(FunctionDefDB).where(FunctionDefDB.function_id == function_id)
    )
    return result.scalar_one_or_none()


async def list_functions(session: AsyncSession) -> List[FunctionDefDB]:
    """List all functions, newest first."""
    result = await session.execute(
        select(FunctionDefDB).order_by(FunctionDefDB.created_at.desc())
    )
    return list(result.scalars().all())


async def delete_function(
    session: AsyncSession, function_id: str
) -> bool:
    """
    Delete a function definition permanently.
    Returns True if a row was deleted, False if not found.
    """
    result = await session.execute(
        delete(FunctionDefDB).where(FunctionDefDB.function_id == function_id)
    )
    await session.commit()
    deleted = result.rowcount > 0
    if deleted:
        logger.info(
            f"Function [{function_id}] deleted",
            extra={"event": "function_deleted", "function_id": function_id},
        )
    return deleted


def orm_to_pydantic(db_fn: FunctionDefDB) -> FunctionDef:
    """Convert a FunctionDefDB ORM object to the Pydantic FunctionDef model."""
    return FunctionDef(
        function_id = db_fn.function_id,
        name        = db_fn.name,
        code        = db_fn.code,
        runtime     = db_fn.runtime,
        created_at  = db_fn.created_at,
    )
