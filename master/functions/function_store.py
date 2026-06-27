# master/functions/function_store.py
#
# Business logic for managing serverless function definitions.
# Routes call this; it talks to function_repository for DB persistence.

import uuid
from datetime import datetime
from typing import List

from master.db.database import get_db
from master.db import function_repository as fn_repo
from shared.logger import get_logger
from shared.models import FunctionDef

logger = get_logger("function_store", node_id="master")


async def store_function(name: str, code: str, runtime: str = "python3.11") -> FunctionDef:
    """
    Validate and persist a new function definition.

    Args:
        name:    Human-readable function name.
        code:    Python source code as a string.
        runtime: Docker image tag for the Python interpreter.

    Returns:
        Pydantic FunctionDef with a generated function_id and created_at.
    """
    function_id = str(uuid.uuid4())
    now = datetime.utcnow()

    fn = FunctionDef(
        function_id = function_id,
        name        = name,
        code        = code,
        runtime     = runtime,
        created_at  = now,
    )

    async with get_db() as session:
        await fn_repo.create_function(session, fn)

    logger.info(
        f"Function [{function_id}] stored — name={name!r} runtime={runtime!r}",
        extra={"event": "function_stored", "function_id": function_id, "fn_name": name},
    )
    return fn


async def get_function(function_id: str) -> FunctionDef:
    """
    Retrieve a function definition by ID.

    Raises:
        KeyError: If function_id is not found.
    """
    async with get_db() as session:
        db_fn = await fn_repo.get_function(session, function_id)

    if db_fn is None:
        raise KeyError(f"Function {function_id!r} not found.")

    return fn_repo.orm_to_pydantic(db_fn)


async def list_functions() -> List[FunctionDef]:
    """Return all stored function definitions, newest first."""
    async with get_db() as session:
        all_fns = await fn_repo.list_functions(session)
    return [fn_repo.orm_to_pydantic(f) for f in all_fns]


async def delete_function(function_id: str) -> bool:
    """
    Delete a function definition.

    Returns:
        True if deleted, False if not found.
    """
    async with get_db() as session:
        deleted = await fn_repo.delete_function(session, function_id)

    if deleted:
        logger.info(
            f"Function [{function_id}] deleted",
            extra={"event": "function_deleted", "function_id": function_id},
        )
    return deleted
