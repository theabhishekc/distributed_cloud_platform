# master/storage/replication_monitor.py
#
# Background async loop that detects under-replicated chunks and re-replicates them.
#
# An under-replicated chunk is one whose primary or replica worker_id belongs to
# a node the health monitor has marked 'dead'.
#
# Loop runs every REPLICATION_INTERVAL_SECONDS (default 60).
# A single chunk failure MUST NOT crash the loop — every chunk is wrapped in
# its own try/except so others still get re-replicated.

import asyncio
import hashlib
import os
import uuid
from typing import List

import httpx

from master.db.database import get_db
from master.db import storage_repository as storage_repo
from master.db.models import FileChunkDB
from master.registry.node_registry import get_healthy_nodes, nodes
from master.scheduler.scheduler import _score, NoHealthyNodeError
from master.storage.upload_orchestrator import StorageError, WORKER_TIMEOUT
from shared.logger import get_logger

logger = get_logger("replication_monitor", node_id="master")

REPLICATION_INTERVAL_SECONDS: int = int(
    os.getenv("REPLICATION_INTERVAL_SECONDS", "60")
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _dead_worker_ids() -> List[str]:
    """Return node_ids of all nodes currently marked 'dead' in the registry."""
    return [nid for nid, node in nodes.items() if node.status == "dead"]


def _pick_new_worker(exclude_ids: List[str]):
    """Return the best healthy worker not in exclude_ids, or raise NoHealthyNodeError."""
    candidates = [
        n for n in get_healthy_nodes()
        if n.node_id not in exclude_ids
    ]
    if not candidates:
        raise NoHealthyNodeError(
            f"No healthy worker available excluding {exclude_ids}"
        )
    return max(candidates, key=lambda n: _score(n))


async def _fetch_chunk_bytes(worker_id: str, chunk_id: str) -> bytes:
    """Fetch raw chunk bytes from a living worker."""
    node = nodes.get(worker_id)
    if node is None:
        raise StorageError(f"Worker {worker_id!r} not in registry")
    url = f"http://{node.ip}:{node.port}/storage/chunks/{chunk_id}"
    async with httpx.AsyncClient(timeout=WORKER_TIMEOUT) as client:
        resp = await client.get(url)
        resp.raise_for_status()
    return resp.content


async def _post_chunk_to_worker(
    worker_id: str,
    chunk_id: str,
    file_id: str,
    chunk_index: int,
    checksum: str,
    data: bytes,
) -> None:
    """POST a chunk to a new worker and verify returned checksum."""
    node = nodes.get(worker_id)
    if node is None:
        raise StorageError(f"Worker {worker_id!r} not in registry")
    url = f"http://{node.ip}:{node.port}/storage/chunks"
    async with httpx.AsyncClient(timeout=WORKER_TIMEOUT) as client:
        resp = await client.post(
            url,
            data={
                "chunk_id":    chunk_id,
                "file_id":     file_id,
                "chunk_index": str(chunk_index),
                "checksum":    checksum,
            },
            files={"file": (chunk_id, data, "application/octet-stream")},
        )
        resp.raise_for_status()
        body = resp.json()
        returned = body.get("checksum", "")
        if returned != checksum:
            raise StorageError(
                f"Re-replication checksum mismatch on {worker_id!r}: "
                f"expected={checksum!r} got={returned!r}"
            )


async def _rereplicate_chunk(chunk: FileChunkDB, dead_ids: List[str]) -> None:
    """
    Re-replicate a single under-replicated chunk to a new healthy worker.

    Cases:
    A) Primary is dead, replica is alive →
       fetch from replica, re-POST to new worker, update primary in DB.
    B) Replica is dead, primary is alive →
       fetch from primary, re-POST to new worker, update replica in DB.
    C) Both dead → log and skip (unrecoverable without more replicas).
    """
    primary_dead = chunk.worker_id in dead_ids
    replica_dead = chunk.replica_worker_id in dead_ids if chunk.replica_worker_id else False

    if primary_dead and replica_dead:
        logger.error(
            f"Chunk [{chunk.chunk_id}] is UNRECOVERABLE — "
            f"both primary ({chunk.worker_id!r}) and replica ({chunk.replica_worker_id!r}) dead",
            extra={"event": "chunk_unrecoverable", "chunk_id": chunk.chunk_id,
                   "file_id": chunk.file_id},
        )
        return

    if primary_dead:
        # Fetch from replica, re-POST to a new worker as new primary
        surviving_worker = chunk.replica_worker_id
        data = await _fetch_chunk_bytes(surviving_worker, chunk.chunk_id)

        # Verify integrity
        computed = hashlib.md5(data).hexdigest()
        if computed != chunk.checksum:
            raise StorageError(
                f"Integrity check failed fetching chunk [{chunk.chunk_id}] "
                f"from replica {surviving_worker!r}: "
                f"expected={chunk.checksum!r} got={computed!r}"
            )

        new_worker = _pick_new_worker(exclude_ids=[chunk.worker_id, surviving_worker])
        await _post_chunk_to_worker(
            new_worker.node_id, chunk.chunk_id, chunk.file_id,
            chunk.chunk_index, chunk.checksum, data
        )

        async with get_db() as session:
            await storage_repo.update_chunk_worker(
                session, chunk.chunk_id, worker_id=new_worker.node_id
            )

        logger.info(
            f"Re-replicated chunk [{chunk.chunk_id}] — "
            f"from_worker={chunk.worker_id!r} (dead) → to_worker={new_worker.node_id!r} "
            f"file_id={chunk.file_id}",
            extra={
                "event":       "chunk_rereplicated",
                "chunk_id":    chunk.chunk_id,
                "file_id":     chunk.file_id,
                "from_worker": chunk.worker_id,
                "to_worker":   new_worker.node_id,
                "role":        "primary",
            },
        )

    else:
        # Replica is dead. Fetch from primary, re-POST to a new replica.
        surviving_worker = chunk.worker_id
        data = await _fetch_chunk_bytes(surviving_worker, chunk.chunk_id)

        computed = hashlib.md5(data).hexdigest()
        if computed != chunk.checksum:
            raise StorageError(
                f"Integrity check failed fetching chunk [{chunk.chunk_id}] "
                f"from primary {surviving_worker!r}: "
                f"expected={chunk.checksum!r} got={computed!r}"
            )

        new_replica = _pick_new_worker(exclude_ids=[surviving_worker, chunk.replica_worker_id])
        await _post_chunk_to_worker(
            new_replica.node_id, chunk.chunk_id, chunk.file_id,
            chunk.chunk_index, chunk.checksum, data
        )

        async with get_db() as session:
            await storage_repo.update_chunk_worker(
                session, chunk.chunk_id, replica_worker_id=new_replica.node_id
            )

        logger.info(
            f"Re-replicated chunk [{chunk.chunk_id}] replica — "
            f"from_worker={chunk.replica_worker_id!r} (dead) → to_worker={new_replica.node_id!r} "
            f"file_id={chunk.file_id}",
            extra={
                "event":       "chunk_rereplicated",
                "chunk_id":    chunk.chunk_id,
                "file_id":     chunk.file_id,
                "from_worker": chunk.replica_worker_id,
                "to_worker":   new_replica.node_id,
                "role":        "replica",
            },
        )


# ── Background loop ───────────────────────────────────────────────────────────

async def replication_monitor() -> None:
    """
    Continuously scan for under-replicated chunks and heal them.

    Runs every REPLICATION_INTERVAL_SECONDS.
    A per-chunk exception NEVER propagates to kill the loop.
    """
    logger.info(
        f"Replication monitor started — interval={REPLICATION_INTERVAL_SECONDS}s",
        extra={"event": "monitor_start"},
    )

    while True:
        await asyncio.sleep(REPLICATION_INTERVAL_SECONDS)

        dead_ids = _dead_worker_ids()
        if not dead_ids:
            continue  # nothing to do

        logger.info(
            f"Replication scan — dead workers: {dead_ids}",
            extra={"event": "replication_scan", "dead_workers": dead_ids},
        )

        try:
            async with get_db() as session:
                chunks = await storage_repo.list_under_replicated_chunks(session, dead_ids)
        except Exception as exc:
            logger.error(
                f"Failed to query under-replicated chunks: {exc}",
                extra={"event": "replication_db_error", "error": str(exc)},
            )
            continue

        if not chunks:
            continue

        logger.info(
            f"Found {len(chunks)} under-replicated chunk(s) — starting re-replication",
            extra={"event": "replication_chunks_found", "count": len(chunks)},
        )

        for chunk in chunks:
            try:
                await _rereplicate_chunk(chunk, dead_ids)
            except Exception as exc:
                # Log and continue — a single chunk failure MUST NOT crash the loop
                logger.error(
                    f"Failed to re-replicate chunk [{chunk.chunk_id}]: {exc}",
                    extra={
                        "event":    "replication_chunk_error",
                        "chunk_id": chunk.chunk_id,
                        "file_id":  chunk.file_id,
                        "error":    str(exc),
                    },
                )
