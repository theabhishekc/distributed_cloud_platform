# worker/storage/chunk_handler.py
#
# Local disk storage for file chunks on a worker node.
#
# Storage layout:
#   /tmp/minicloud-storage/{node_id}/{chunk_id}.bin
#
# IMPORTANT: node_id is read from worker/config.py (set via WORKER_NODE_ID env var
# or the UUID generated at startup). It is never hardcoded.
#
# All operations are synchronous disk I/O — callers should run them in a
# thread pool executor if called from async context (same pattern as docker_runner).

import hashlib
import os
from pathlib import Path

from shared.logger import get_logger

# node_id from config — set at import time
# The runtime node_id (UUID) comes from NODE_INFO in worker/main.py,
# but chunk_handler is also used before main starts so we fall back to
# WORKER_NODE_ID from config (the env var or 'worker-unknown').
from worker.config import WORKER_NODE_ID

logger = get_logger("chunk_handler", node_id=WORKER_NODE_ID)


# ── Custom exception ──────────────────────────────────────────────────────────

class ChecksumError(Exception):
    """Raised when the MD5 checksum of received chunk data does not match."""
    pass


# ── Storage root ──────────────────────────────────────────────────────────────

def _storage_root(node_id: str) -> Path:
    """
    Return the storage directory for this worker node, creating it if needed.
    node_id is passed explicitly so that the actual runtime UUID from NODE_INFO
    can be injected — overriding the config default which is just for logging.
    """
    root = Path(f"/tmp/minicloud-storage/{node_id}")
    root.mkdir(parents=True, exist_ok=True)
    return root


def _chunk_path(node_id: str, chunk_id: str) -> Path:
    return _storage_root(node_id) / f"{chunk_id}.bin"


# ── Public API ────────────────────────────────────────────────────────────────

def save_chunk(
    chunk_id: str,
    file_id: str,
    chunk_index: int,
    data: bytes,
    checksum: str,
    node_id: str = WORKER_NODE_ID,
) -> str:
    """
    Write chunk bytes to disk and verify the MD5 checksum.

    Args:
        chunk_id:   UUID string for this chunk.
        file_id:    UUID of the parent file (for logging).
        chunk_index: Position of this chunk in the file.
        data:       Raw bytes of the chunk.
        checksum:   Expected MD5 hex digest (32 hex chars) from the master.
        node_id:    This worker's node_id. Defaults to WORKER_NODE_ID from config.

    Returns:
        The MD5 hex digest of the saved data (same as checksum if valid).

    Raises:
        ChecksumError: If computed MD5 ≠ expected checksum.
    """
    computed = hashlib.md5(data).hexdigest()
    if computed != checksum:
        raise ChecksumError(
            f"Checksum mismatch for chunk [{chunk_id}]: "
            f"expected={checksum!r} got={computed!r}"
        )

    path = _chunk_path(node_id, chunk_id)
    path.write_bytes(data)

    logger.info(
        f"Chunk [{chunk_id}] saved — file={file_id} idx={chunk_index} "
        f"size={len(data)}B checksum={computed}",
        extra={
            "event":       "chunk_saved",
            "chunk_id":    chunk_id,
            "file_id":     file_id,
            "chunk_index": chunk_index,
            "size_bytes":  len(data),
            "checksum":    computed,
        },
    )
    return computed


def get_chunk(chunk_id: str, node_id: str = WORKER_NODE_ID) -> bytes:
    """
    Read and return raw chunk bytes from disk.

    Raises:
        FileNotFoundError: If the chunk file does not exist.
    """
    path = _chunk_path(node_id, chunk_id)
    if not path.exists():
        raise FileNotFoundError(
            f"Chunk [{chunk_id}] not found at {path}"
        )
    data = path.read_bytes()
    logger.info(
        f"Chunk [{chunk_id}] read — size={len(data)}B",
        extra={"event": "chunk_read", "chunk_id": chunk_id, "size_bytes": len(data)},
    )
    return data


def delete_chunk(chunk_id: str, node_id: str = WORKER_NODE_ID) -> bool:
    """
    Delete a chunk from disk.

    Returns:
        True if deleted, False if the file was not found (idempotent).
    """
    path = _chunk_path(node_id, chunk_id)
    if path.exists():
        path.unlink()
        logger.info(
            f"Chunk [{chunk_id}] deleted",
            extra={"event": "chunk_deleted", "chunk_id": chunk_id},
        )
        return True
    return False
