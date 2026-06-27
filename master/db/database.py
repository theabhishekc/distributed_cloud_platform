# master/db/database.py
#
# Async SQLAlchemy engine + session factory.
# Uses asyncpg as the driver (postgresql+asyncpg).
#
# DATABASE_URL env var format:
#   postgresql+asyncpg://<user>:<pass>@<host>:<port>/<db>
# Default points at the local master machine PostgreSQL instance.

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from master.db.models import Base
from shared.logger import get_logger

logger = get_logger("database", node_id="master")

# ── Connection string ─────────────────────────────────────────────────────────

DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://minicloud:minicloud@localhost:5432/minicloud",
)

# ── Engine ────────────────────────────────────────────────────────────────────
#
# echo=False  — don't flood logs with raw SQL in production.
# pool_pre_ping=True  — verify connection alive before lending from pool.
# pool_size / max_overflow are asyncpg defaults (5 / 10); fine for 4 laptops.

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
)

# ── Session factory ───────────────────────────────────────────────────────────
#
# expire_on_commit=False — prevents "DetachedInstanceError" after commit when
# we access model attributes in route handlers after the session is gone.

AsyncSessionFactory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ── Table creation ────────────────────────────────────────────────────────────

async def create_tables() -> None:
    """
    Create all tables defined in models.py if they do not already exist.

    Called once at master startup (see master/main.py lifespan).
    In production you would use Alembic migrations instead; this is the
    lightweight "just make it work" path for Week 2.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info(
        "Database tables created (or already exist).",
        extra={"event": "db_tables_ready"},
    )


# ── FastAPI dependency ────────────────────────────────────────────────────────

@asynccontextmanager
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Async context manager that yields a database session and guarantees
    close even if an exception is raised.

    Usage in a route:
        async with get_db() as session:
            result = await task_repo.get_task(session, task_id)
    """
    async with AsyncSessionFactory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
