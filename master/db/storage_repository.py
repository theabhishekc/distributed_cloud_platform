# master/db/storage_repository.py
#
# Async CRUD for FileMetadata, FileChunk tables.
# Every function receives an AsyncSession — never creates its own.

import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from master.db.models import FileChunkDB, FileMetadataDB
from shared.logger import get_logger
from shared.models import FileChunk, FileMetadata

logger = get_logger("storage_repo", node_id="master")


# ═══════════════════════════════════════════════════════════════════════════════
# FileMetadata
# ═══════════════════════════════════════════════════════════════════════════════

async def create_file_metadata(
    session: AsyncSession,
    file_id: str,
    filename: str,
    total_size: int,
    chunk_count: int,
    replication_factor: int = 2,
) -> FileMetadataDB:
    """Persist a new file record in 'available' state."""
    db_file = FileMetadataDB(
        file_id            = file_id,
        filename           = filename,
        total_size         = total_size,
        chunk_count        = chunk_count,
        replication_factor = replication_factor,
        created_at         = datetime.utcnow(),
        status             = "available",
    )
    session.add(db_file)
    await session.commit()
    await session.refresh(db_file)
    logger.info(
        f"File [{file_id}] metadata created — '{filename}' ({total_size}B, {chunk_count} chunks)",
        extra={"event": "file_created", "file_id": file_id, "orig_filename": filename},
    )
    return db_file


async def get_file_metadata(
    session: AsyncSession, file_id: str
) -> Optional[FileMetadataDB]:
    """Return FileMetadataDB or None if not found."""
    result = await session.execute(
        select(FileMetadataDB).where(FileMetadataDB.file_id == file_id)
    )
    return result.scalar_one_or_none()


async def list_files(session: AsyncSession) -> List[FileMetadataDB]:
    """List all files that are not deleted, newest first."""
    result = await session.execute(
        select(FileMetadataDB)
        .where(FileMetadataDB.status != "deleted")
        .order_by(FileMetadataDB.created_at.desc())
    )
    return list(result.scalars().all())


async def update_file_status(
    session: AsyncSession, file_id: str, status: str
) -> Optional[FileMetadataDB]:
    """Update the status field of a file record."""
    await session.execute(
        update(FileMetadataDB)
        .where(FileMetadataDB.file_id == file_id)
        .values(status=status)
    )
    await session.commit()
    result = await get_file_metadata(session, file_id)
    logger.info(
        f"File [{file_id}] status → {status}",
        extra={"event": "file_status_updated", "file_id": file_id, "status": status},
    )
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# FileChunk
# ═══════════════════════════════════════════════════════════════════════════════

async def create_chunk(
    session: AsyncSession,
    chunk_id: str,
    file_id: str,
    chunk_index: int,
    size_bytes: int,
    checksum: str,
    worker_id: str,
    replica_worker_id: Optional[str] = None,
) -> FileChunkDB:
    """Persist a chunk record."""
    db_chunk = FileChunkDB(
        chunk_id          = chunk_id,
        file_id           = file_id,
        chunk_index       = chunk_index,
        size_bytes        = size_bytes,
        checksum          = checksum,
        worker_id         = worker_id,
        replica_worker_id = replica_worker_id,
    )
    session.add(db_chunk)
    await session.commit()
    await session.refresh(db_chunk)
    return db_chunk


async def get_chunks_for_file(
    session: AsyncSession, file_id: str
) -> List[FileChunkDB]:
    """Return all chunks for a file ordered by chunk_index ascending."""
    result = await session.execute(
        select(FileChunkDB)
        .where(FileChunkDB.file_id == file_id)
        .order_by(FileChunkDB.chunk_index)
    )
    return list(result.scalars().all())


async def update_chunk_worker(
    session: AsyncSession,
    chunk_id: str,
    worker_id: Optional[str] = None,
    replica_worker_id: Optional[str] = None,
) -> Optional[FileChunkDB]:
    """
    Update primary or replica worker assignment for a chunk.
    Only updates fields that are explicitly passed.
    """
    values = {}
    if worker_id is not None:
        values["worker_id"] = worker_id
    if replica_worker_id is not None:
        values["replica_worker_id"] = replica_worker_id

    if not values:
        result = await session.execute(
            select(FileChunkDB).where(FileChunkDB.chunk_id == chunk_id)
        )
        return result.scalar_one_or_none()

    await session.execute(
        update(FileChunkDB)
        .where(FileChunkDB.chunk_id == chunk_id)
        .values(**values)
    )
    await session.commit()
    result = await session.execute(
        select(FileChunkDB).where(FileChunkDB.chunk_id == chunk_id)
    )
    return result.scalar_one_or_none()


async def list_under_replicated_chunks(
    session: AsyncSession,
    dead_worker_ids: List[str],
) -> List[FileChunkDB]:
    """
    Return all chunks whose primary worker_id is in dead_worker_ids.
    These are the chunks that need re-replication to a healthy worker.
    Also includes chunks whose replica_worker_id is dead but primary is fine —
    those are under-replicated (only 1 copy when 2 are required).
    """
    if not dead_worker_ids:
        return []

    # Primary dead: chunk needs a whole new primary
    result_primary = await session.execute(
        select(FileChunkDB).where(FileChunkDB.worker_id.in_(dead_worker_ids))
    )
    primary_dead = list(result_primary.scalars().all())

    # Replica dead: chunk still reachable but down to 1 replica
    result_replica = await session.execute(
        select(FileChunkDB).where(
            FileChunkDB.replica_worker_id.in_(dead_worker_ids),
            FileChunkDB.worker_id.notin_(dead_worker_ids),  # primary is alive
        )
    )
    replica_dead = list(result_replica.scalars().all())

    return primary_dead + replica_dead
