# master/api/function_routes.py
#
# Master-side serverless function REST routes.
#
# POST   /functions                        — store function definition
# GET    /functions                        — list all functions
# GET    /functions/{function_id}          — get one function
# DELETE /functions/{function_id}          — delete function definition
# POST   /functions/{function_id}/invoke   — schedule invocation on a worker

from typing import Any, Dict, List

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from master.functions.function_store import (
    delete_function,
    get_function,
    list_functions,
    store_function,
)
from master.registry.node_registry import get_healthy_nodes, nodes
from master.scheduler.scheduler import NoHealthyNodeError, _score
from shared.logger import get_logger
from shared.models import FunctionDef, InvokeResult

router = APIRouter(prefix="/functions", tags=["functions"])
logger = get_logger("function_routes", node_id="master")

WORKER_TIMEOUT = 30.0


# ── Request schemas ───────────────────────────────────────────────────────────

class CreateFunctionBody(BaseModel):
    name:    str
    code:    str
    runtime: str = "python3.11"


class InvokeBody(BaseModel):
    payload:         Dict[str, Any] = {}
    timeout_seconds: int = 30


# ── Worker selection ──────────────────────────────────────────────────────────

def _pick_worker_for_invoke():
    """Pick the highest-scoring healthy worker for Lambda invocation."""
    healthy = get_healthy_nodes()
    if not healthy:
        raise NoHealthyNodeError(
            "No healthy worker nodes available for function invocation."
        )
    return max(healthy, key=lambda n: _score(n))


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("", status_code=201)
async def create_function(body: CreateFunctionBody) -> Dict[str, Any]:
    """
    Store a new function definition.
    Returns the created FunctionDef (with generated function_id and created_at).
    """
    fn: FunctionDef = await store_function(
        name    = body.name,
        code    = body.code,
        runtime = body.runtime,
    )
    return fn.model_dump(mode="json")


@router.get("")
async def list_all_functions() -> List[Dict[str, Any]]:
    """Return all stored function definitions."""
    fns = await list_functions()
    return [f.model_dump(mode="json") for f in fns]


@router.get("/{function_id}")
async def get_one_function(function_id: str) -> Dict[str, Any]:
    """Return one function definition by ID."""
    try:
        fn = await get_function(function_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Function {function_id!r} not found.")
    return fn.model_dump(mode="json")


@router.delete("/{function_id}", status_code=200)
async def delete_one_function(function_id: str) -> Dict[str, Any]:
    """Delete a function definition permanently."""
    deleted = await delete_function(function_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Function {function_id!r} not found.")
    return {"function_id": function_id, "deleted": True}


@router.post("/{function_id}/invoke")
async def invoke_function(function_id: str, body: InvokeBody) -> InvokeResult:
    """
    Invoke a stored function on a healthy worker node.

    Steps:
      1. Fetch FunctionDef from DB.
      2. Select best healthy worker using scheduler score.
      3. POST to worker /functions/invoke with full FunctionDef + payload.
      4. Return InvokeResult to client.
    """
    try:
        fn = await get_function(function_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Function {function_id!r} not found.")

    try:
        worker = _pick_worker_for_invoke()
    except NoHealthyNodeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    worker_url = f"http://{worker.ip}:{worker.port}/functions/invoke"

    logger.info(
        f"Invoking function [{function_id}] on worker [{worker.node_id[-8:]}]",
        extra={
            "event":       "invoke_dispatch",
            "function_id": function_id,
            "worker_id":   worker.node_id,
        },
    )

    try:
        async with httpx.AsyncClient(timeout=body.timeout_seconds + 5) as client:
            resp = await client.post(
                worker_url,
                json={
                    "function_def":    fn.model_dump(mode="json"),
                    "payload":         body.payload,
                    "timeout_seconds": body.timeout_seconds,
                },
            )
            resp.raise_for_status()
            result = InvokeResult(**resp.json())
            from master.metrics import minicloud_lambda_invocations_total, minicloud_lambda_duration_ms
            minicloud_lambda_invocations_total.labels(function_id=function_id).inc()
            minicloud_lambda_duration_ms.labels(function_id=function_id).observe(result.duration_ms)
            return result

    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Worker returned HTTP {exc.response.status_code}: {exc.response.text}",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Worker unreachable during invocation: {exc}",
        )
