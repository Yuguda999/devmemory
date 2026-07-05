"""Async database engine and session factory."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from devmemory.config import settings

# ── Engine ──────────────────────────────────────────────────────
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Return the shared async engine, creating it on first call.

    TLS for managed Postgres (Neon/Supabase) is carried in the URL as
    ``?ssl=require`` (normalised from ``sslmode`` in config), so no per-host
    handling is needed here.
    """
    global _engine
    if _engine is None:
        connect_args = {}
        engine_kwargs = {"echo": settings.log_level == "DEBUG"}

        if settings.database_is_sqlite:
            # SQLite requires this for async + concurrent writes
            connect_args["check_same_thread"] = False
        else:
            # Managed/serverless Postgres (Neon) closes idle connections when the
            # compute suspends or the pooler recycles them. Without this the pool
            # hands out a dead connection → "asyncpg InterfaceError: connection
            # is closed". pre_ping validates (and transparently replaces) a
            # connection before use; recycle drops aged ones proactively.
            engine_kwargs["pool_pre_ping"] = True
            engine_kwargs["pool_recycle"] = 300
            if settings.database_url.startswith("postgresql+asyncpg://"):
                # Keep asyncpg compatible with pgbouncer transaction pooling
                # (Neon's pooled endpoint) by not caching prepared statements.
                connect_args["statement_cache_size"] = 0

        _engine = create_async_engine(
            settings.database_url,
            connect_args=connect_args,
            **engine_kwargs,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the shared async session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide an async database session with automatic cleanup.

    Usage::

        async with get_db_session() as session:
            result = await session.execute(...)
    """
    factory = get_session_factory()
    session = factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def init_db() -> None:
    """Create all tables (for development / testing only).

    In production, use Alembic migrations instead.
    """
    from devmemory.models import Base  # noqa: F811

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Dispose of the engine connection pool."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
