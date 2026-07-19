"""Shared test fixtures."""

from __future__ import annotations

import os

# Isolate the test suite from a developer's real configuration. The settings
# singleton is built from environment + .env / ~/.devmemory/.env on first import
# of ``devmemory.config`` (triggered by the imports below), so a real SendGrid
# key, saas mode, admin allowlist, or Postgres URL would otherwise leak in and
# make results depend on the machine. Real env vars take precedence over the
# env_file in pydantic-settings, so pinning them here forces a clean, hermetic
# config. MUST run before any ``devmemory`` import.
os.environ.update(
    {
        "DEVMEMORY_DATABASE_URL": "sqlite+aiosqlite:///:memory:",
        "DEVMEMORY_DEPLOYMENT_MODE": "self-hosted",
        "DEVMEMORY_SECRET_KEY": "test-secret-key-for-tests-only-min-32-bytes",
        "DEVMEMORY_SENDGRID_API_KEY": "",
        "DEVMEMORY_SMTP_HOST": "",
        "DEVMEMORY_ADMIN_EMAILS": "",
        "DEVMEMORY_BLOCKFROST_PROJECT_ID": "",
        "DEVMEMORY_CARDANO_ACCOUNT_XPUB": "",
        "DEVMEMORY_CARDANO_ALLOW_TEST_PAYMENTS": "false",
    }
)

import asyncio  # noqa: E402
from collections.abc import AsyncGenerator  # noqa: E402

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from sqlalchemy import event  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from devmemory.models import Base  # noqa: E402

# Use an in-memory SQLite database for tests
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop():
    """Create a single event loop for the entire test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def engine():
    """Create a test engine with all tables.

    Enables ``PRAGMA foreign_keys = ON`` for SQLite so that
    ``ON DELETE CASCADE`` works correctly in tests.
    """
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)

    # SQLite ignores ON DELETE CASCADE unless foreign_keys is enabled.
    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(engine) -> AsyncGenerator[AsyncSession, None]:
    """Provide a transactional test session that rolls back after each test."""
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    session = session_factory()
    try:
        yield session
    finally:
        await session.rollback()
        await session.close()
