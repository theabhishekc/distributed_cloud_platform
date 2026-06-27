# worker/api/function_routes.py
#
# Worker-side Lambda invocation route.
#
# POST /functions/invoke — receive FunctionDef + payload → run in Docker → return InvokeResult

from fastapi import APIRouter
from shared.logger import get_logger
from shared.models import FunctionDef, InvokeRequest, InvokeResult
from worker.config import WORKER_NODE_ID
from worker.functions.lambda_runner import invoke

router = APIRouter(prefix="/functions", tags=["functions"])
logger = get_logger("worker_function_routes", node_id=WORKER_NODE_ID)


class WorkerInvokeRequest(object):
    """Internal payload shape the master sends to the worker."""


from pydantic import BaseModel
from typing import Any, Dict


class WorkerFunctionInvokeBody(BaseModel):
    function_def:    FunctionDef
    payload:         Dict[str, Any]
    timeout_seconds: int = 30


@router.post("/invoke")
async def invoke_function(body: WorkerFunctionInvokeBody) -> InvokeResult:
    """
    Run a function in a sandboxed Docker container and return the result.

    The master sends:
      function_def:    full FunctionDef (id, name, code, runtime, created_at)
      payload:         dict injected as PAYLOAD variable into the script
      timeout_seconds: max container lifetime
    """
    logger.info(
        f"Received invoke request for function [{body.function_def.function_id}] "
        f"name={body.function_def.name!r}",
        extra={"event": "worker_invoke_received",
               "function_id": body.function_def.function_id},
    )

    result = await invoke(
        function_def    = body.function_def,
        payload         = body.payload,
        timeout_seconds = body.timeout_seconds,
        worker_id       = WORKER_NODE_ID,
    )
    from worker.metrics import minicloud_worker_local_lambda_total, minicloud_worker_local_lambda_duration_ms
    minicloud_worker_local_lambda_total.labels(function_id=body.function_def.function_id).inc()
    minicloud_worker_local_lambda_duration_ms.labels(function_id=body.function_def.function_id).observe(result.duration_ms)
    return result
