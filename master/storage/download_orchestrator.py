# master/storage/download_orchestrator.py
#
# Retrieves and reassembles a file from its distributed chunks.
#
# Algorithm:
#   1. Fetch FileMetadata + all FileChunk records from DB (ordered by chunk_index).
#   2. For each chunk:
#      a. GET /storage/chunks/{chunk_id} from primary worker.
#      b. Verify MD5 of returned bytes.
#      c. On failure (timeout, 404, checksum mismatch): fall back to replica.
#      d. Verify replica checksum.
#      e. If both fail: raise StorageError (chunk unrecoverable).
#   3. Concatenate all chunks in order → return full bytes.

import hashlib
from typing import List

import httpx

from master.db.database import get_db
from master.db import storage_repository as storage_repo
from master.db.models import FileChunkDB
from master.registry.node_registry import nodes
from master.storage.upload_orchestrator import StorageError
from shared.logger import get_logger

logger = get_logger("download_orchestrator", node_id="master")

WORKER_TIMEOUT = 30.0


# ── Helpers ───────────────────────────────────────────────────────────────────

def _worker_url(worker_id: str) -> str | None:
    """Return http://ip:port for a node_id, or None if not in the registry."""
    node = nodes.get(worker_id)
    if node is None:
        return None
    return f"http://{node.ip}:{node.port}"


async def _fetch_chunk(
    client: httpx.AsyncClient,
    worker_id: str,
    chunk_id: str,
    expected_checksum: str,
) -> bytes:
    """
    GET chunk bytes from a worker and verify MD5.

    Raises:
        StorageError: worker unreachable, returned 404, or checksum mismatch.
    """
    url = _worker_url(worker_id)
    if url is None:
        raise StorageError(
            f"Worker {worker_id!r} not found in registry — cannot fetch chunk [{chunk_id}]"
        )

    try:
        response = await client.get(f"{url}/storage/chunks/{chunk_id}")
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise StorageError(
            f"HTTP error fetching chunk [{chunk_id}] from {worker_id!r}: {exc}"
        ) from exc

    data = response.content
    computed = hashlib.md5(data).hexdigest()
    if computed != expected_checksum:
        raise StorageError(
            f"Checksum mismatch for chunk [{chunk_id}] from {worker_id!r}: "
            f"expected={expected_checksum!r} got={computed!r}"
        )
    return data


# ── Public API ────────────────────────────────────────────────────────────────

async def download_file(file_id: str) -> bytes:
    """
    Download and reassemble a file from its distributed chunks.

    Args:
        file_id: UUID string of the file to download.

    Returns:
        Full file bytes in correct order.

    Raises:
        FileNotFoundError: file_id not found or file is deleted.
        StorageError:      A chunk is unrecoverable from all its replicas.
    """
    async with get_db() as session:
        meta = await storage_repo.get_file_metadata(session, file_id)
        if meta is None or meta.status == "deleted":
            raise FileNotFoundError(f"File {file_id!r} not found.")

        chunks: List[FileChunkDB] = await storage_repo.get_chunks_for_file(session, file_id)

    if not chunks:
        raise StorageError(f"File {file_id!r} has no chunk records in DB.")

    logger.info(
        f"Starting download — file_id={file_id} filename={meta.filename!r} "
        f"chunks={len(chunks)}",
        extra={"event": "download_start", "file_id": file_id},
    )

    assembled: List[bytes] = []

    async with httpx.AsyncClient(timeout=WORKER_TIMEOUT) as client:
        for chunk in chunks:
            chunk_data: bytes | None = None

            # Try primary first
            try:
                chunk_data = await _fetch_chunk(
                    client, chunk.worker_id, chunk.chunk_id, chunk.checksum
                )
                logger.info(
                    f"Chunk {chunk.chunk_index} [{chunk.chunk_id[-8:]}] fetched from primary",
                    extra={"event": "chunk_fetched", "source": "primary",
                           "chunk_id": chunk.chunk_id},
                )
            except StorageError as primary_err:
                logger.warning(
                    f"Primary fetch failed for chunk {chunk.chunk_index} "
                    f"[{chunk.chunk_id[-8:]}]: {primary_err} — trying replica",
                    extra={"event": "chunk_primary_fail", "chunk_id": chunk.chunk_id,
                           "error": str(primary_err)},
                )

                # Fall back to replica
                if chunk.replica_worker_id:
                    try:
                        chunk_data = await _fetch_chunk(
                            client,
                            chunk.replica_worker_id,
                            chunk.chunk_id,
                            chunk.checksum,
                        )
                        logger.info(
                            f"Chunk {chunk.chunk_index} [{chunk.chunk_id[-8:]}] "
                            f"fetched from replica",
                            extra={"event": "chunk_fetched", "source": "replica",
                                   "chunk_id": chunk.chunk_id},
                        )
                    except StorageError as replica_err:
                        raise StorageError(
                            f"Chunk {chunk.chunk_index} [{chunk.chunk_id}] is unrecoverable: "
                            f"primary error: {primary_err}; replica error: {replica_err}"
                        )
                else:
                    raise StorageError(
                        f"Chunk {chunk.chunk_index} [{chunk.chunk_id}] primary failed "
                        f"and no replica is registered."
                    )

            assembled.append(chunk_data)

    result = b"".join(assembled)
    logger.info(
        f"Download complete — file_id={file_id} size={len(result)}B",
        extra={"event": "download_complete", "file_id": file_id, "size": len(result)},
    )
    return result
