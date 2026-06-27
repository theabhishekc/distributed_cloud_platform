# master/api/storage_routes.py
#
# Master-side file storage REST routes.
#
# POST   /files              — upload file → orchestrate chunking + replication
# GET    /files              — list all files
# GET    /files/{file_id}    — download file as StreamingResponse
# DELETE /files/{file_id}    — mark deleted, clean up chunk workers

import io
from typing import Any, Dict, List

import httpx
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from master.db.database import get_db
from master.db import storage_repository as storage_repo
from master.registry.node_registry import nodes
from master.storage.download_orchestrator import download_file, StorageError
from master.storage.upload_orchestrator import upload_file
from master.scheduler.scheduler import NoHealthyNodeError
from shared.logger import get_logger
from shared.models import FileMetadata

router = APIRouter(prefix="/files", tags=["files"])
logger = get_logger("master_storage_routes", node_id="master")

WORKER_TIMEOUT = 30.0


async def _update_storage_metrics():
    try:
        async with get_db() as session:
            files = await storage_repo.list_files(session)
            total_files = len(files)
            total_bytes = sum(f.total_size for f in files)
            from master.metrics import minicloud_files_total, minicloud_storage_bytes_total
            minicloud_files_total.set(total_files)
            minicloud_storage_bytes_total.set(total_bytes)
    except Exception:
        pass


# ── POST /files ───────────────────────────────────────────────────────────────

@router.post("", status_code=201)
async def upload_file_endpoint(
    file: UploadFile = File(...),
) -> Dict[str, Any]:
    """
    Upload a file. The master splits it into 1MB chunks and replicates each
    chunk to 2 workers. Returns FileMetadata on success.
    """
    data = await file.read()
    filename = file.filename or "unnamed"

    logger.info(
        f"Upload request — filename={filename!r} size={len(data)}B",
        extra={"event": "upload_request", "orig_filename": filename, "size": len(data)},
    )

    try:
        meta: FileMetadata = await upload_file(data, filename)
    except NoHealthyNodeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        logger.error(
            f"Upload failed — filename={filename!r}: {exc}",
            extra={"event": "upload_failed", "orig_filename": filename, "error": str(exc)},
        )
        raise HTTPException(status_code=500, detail=f"Upload failed: {exc}")

    await _update_storage_metrics()
    return meta.model_dump(mode="json")


# ── GET /files ────────────────────────────────────────────────────────────────

@router.get("")
async def list_files_endpoint() -> List[Dict[str, Any]]:
    """Return a list of all non-deleted files (file_id, filename, size, status, created_at)."""
    async with get_db() as session:
        files = await storage_repo.list_files(session)

    return [
        {
            "file_id":    f.file_id,
            "filename":   f.filename,
            "total_size": f.total_size,
            "chunk_count": f.chunk_count,
            "status":     f.status,
            "created_at": f.created_at.isoformat() if f.created_at else None,
        }
        for f in files
    ]


# ── GET /files/{file_id} ──────────────────────────────────────────────────────

@router.get("/{file_id}")
async def download_file_endpoint(file_id: str) -> StreamingResponse:
    """
    Download a file. Fetches all chunks from workers (with replica fallback)
    and streams the reassembled bytes to the client.
    """
    try:
        file_bytes = await download_file(file_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except StorageError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    # Get filename from DB for Content-Disposition header
    filename = file_id
    try:
        async with get_db() as session:
            meta = await storage_repo.get_file_metadata(session, file_id)
            if meta:
                filename = meta.filename
    except Exception:
        pass  # Non-fatal — use file_id as fallback

    return StreamingResponse(
        io.BytesIO(file_bytes),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── DELETE /files/{file_id} ───────────────────────────────────────────────────

@router.delete("/{file_id}", status_code=200)
async def delete_file_endpoint(file_id: str) -> Dict[str, Any]:
    """
    Soft-delete a file:
    1. Mark status='deleted' in DB.
    2. Best-effort: send DELETE /storage/chunks/{chunk_id} to each worker.
    """
    async with get_db() as session:
        meta = await storage_repo.get_file_metadata(session, file_id)
        if meta is None:
            raise HTTPException(status_code=404, detail=f"File {file_id!r} not found.")
        if meta.status == "deleted":
            return {"file_id": file_id, "status": "deleted", "message": "Already deleted."}

        chunks = await storage_repo.get_chunks_for_file(session, file_id)

    # Mark as deleted first — even if worker cleanup fails the user gets 200
    async with get_db() as session:
        await storage_repo.update_file_status(session, file_id, "deleted")

    # Best-effort: delete chunks from workers
    async with httpx.AsyncClient(timeout=WORKER_TIMEOUT) as client:
        for chunk in chunks:
            for worker_id in {chunk.worker_id, chunk.replica_worker_id}:
                if not worker_id:
                    continue
                node = nodes.get(worker_id)
                if node is None:
                    continue
                try:
                    await client.delete(
                        f"http://{node.ip}:{node.port}/storage/chunks/{chunk.chunk_id}"
                    )
                except Exception as exc:
                    logger.warning(
                        f"Failed to delete chunk [{chunk.chunk_id}] from worker "
                        f"{worker_id!r}: {exc}",
                        extra={"event": "chunk_delete_warn", "chunk_id": chunk.chunk_id,
                               "worker_id": worker_id, "error": str(exc)},
                    )

    logger.info(
        f"File [{file_id}] deleted — {len(chunks)} chunks removed from workers",
        extra={"event": "file_deleted", "file_id": file_id, "chunks": len(chunks)},
    )

    await _update_storage_metrics()
    return {
        "file_id": file_id,
        "status":  "deleted",
        "message": f"File deleted. {len(chunks)} chunks cleaned up.",
    }
