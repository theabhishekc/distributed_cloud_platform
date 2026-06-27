# worker/api/storage_routes.py
#
# Worker-side chunk storage REST routes.
#
# POST /storage/chunks  — receive chunk bytes as multipart, save to disk
# GET  /storage/chunks/{chunk_id} — return raw bytes as StreamingResponse
# DELETE /storage/chunks/{chunk_id} — delete from disk
#
# All disk I/O is synchronous; wrapped in run_in_executor to keep the
# async event loop non-blocking.

import asyncio
from functools import partial

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from shared.logger import get_logger
from worker.config import WORKER_NODE_ID
from worker.storage.chunk_handler import ChecksumError, delete_chunk, get_chunk, save_chunk

router = APIRouter(prefix="/storage", tags=["storage"])
logger = get_logger("worker_storage_routes", node_id=WORKER_NODE_ID)


def _update_worker_storage_metrics_sync():
    try:
        from worker.storage.chunk_handler import _storage_root
        from worker.config import WORKER_NODE_ID
        root = _storage_root(WORKER_NODE_ID)
        chunk_files = list(root.glob("*.bin"))
        total_chunks = len(chunk_files)
        total_bytes = sum(f.stat().st_size for f in chunk_files)
        from worker.metrics import minicloud_worker_local_chunks_total, minicloud_worker_local_storage_bytes
        minicloud_worker_local_chunks_total.set(total_chunks)
        minicloud_worker_local_storage_bytes.set(total_bytes)
    except Exception:
        pass


# ── POST /storage/chunks ──────────────────────────────────────────────────────

@router.post("/chunks", status_code=200)
async def receive_chunk(
    chunk_id:    str       = Form(...),
    file_id:     str       = Form(...),
    chunk_index: int       = Form(...),
    checksum:    str       = Form(...),
    file:        UploadFile = File(...),
) -> dict:
    """
    Receive a file chunk as multipart form data, verify its MD5, save to disk.

    Returns:
        JSON: {chunk_id, checksum, status: "ok"}
    """
    data = await file.read()

    loop = asyncio.get_event_loop()
    try:
        computed = await loop.run_in_executor(
            None,
            partial(
                save_chunk,
                chunk_id,
                file_id,
                chunk_index,
                data,
                checksum,
                WORKER_NODE_ID,
            ),
        )
    except ChecksumError as exc:
        logger.error(
            f"Checksum mismatch for chunk [{chunk_id}]: {exc}",
            extra={"event": "chunk_checksum_fail", "chunk_id": chunk_id},
        )
        raise HTTPException(status_code=400, detail=str(exc))

    await loop.run_in_executor(None, _update_worker_storage_metrics_sync)

    return {
        "chunk_id": chunk_id,
        "checksum": computed,
        "status":   "ok",
    }


# ── GET /storage/chunks/{chunk_id} ────────────────────────────────────────────

@router.get("/chunks/{chunk_id}")
async def serve_chunk(chunk_id: str) -> StreamingResponse:
    """
    Return raw chunk bytes as a streaming response.
    The caller verifies the MD5 after receiving all bytes.
    """
    loop = asyncio.get_event_loop()
    try:
        data = await loop.run_in_executor(
            None,
            partial(get_chunk, chunk_id, WORKER_NODE_ID),
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Chunk {chunk_id!r} not found on this worker.",
        )

    async def _chunk_generator():
        yield data

    return StreamingResponse(
        _chunk_generator(),
        media_type="application/octet-stream",
        headers={"X-Chunk-Id": chunk_id},
    )


# ── DELETE /storage/chunks/{chunk_id} ─────────────────────────────────────────

@router.delete("/chunks/{chunk_id}", status_code=200)
async def remove_chunk(chunk_id: str) -> dict:
    """
    Delete a chunk from local disk (idempotent — 200 even if not found).
    """
    loop = asyncio.get_event_loop()
    deleted = await loop.run_in_executor(
        None,
        partial(delete_chunk, chunk_id, WORKER_NODE_ID),
    )

    await loop.run_in_executor(None, _update_worker_storage_metrics_sync)

    return {
        "chunk_id": chunk_id,
        "deleted":  deleted,
        "status":   "ok",
    }
