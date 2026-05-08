"""Database repository — all CRUD operations, scoped by user_id."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from devmemory.auth.hashing import hash_api_key, hash_password
from devmemory.models import (
    ApiKey,
    Project,
    Session,
    Subscription,
    SubscriptionTier,
    User,
)


# ── User Operations ────────────────────────────────────────────

async def create_user(
    session: AsyncSession,
    email: str,
    password: str,
    display_name: str,
) -> User:
    """Register a new user with a free-tier subscription.

    Args:
        session: The async database session.
        email: The user's email address.
        password: The user's plaintext password (will be hashed).
        display_name: The user's display name.

    Returns:
        The newly created User.
    """
    user = User(
        email=email.lower().strip(),
        password_hash=hash_password(password),
        display_name=display_name.strip(),
    )
    session.add(user)
    await session.flush()

    # Auto-provision a free-tier subscription
    subscription = Subscription(
        user_id=user.id,
        tier=SubscriptionTier.FREE.value,
    )
    session.add(subscription)
    await session.flush()

    return user


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    """Find a user by email address."""
    result = await session.execute(
        select(User).where(User.email == email.lower().strip())
    )
    return result.scalar_one_or_none()


async def get_user_by_id(session: AsyncSession, user_id: str) -> User | None:
    """Find a user by ID."""
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


# ── API Key Operations ─────────────────────────────────────────

async def create_api_key_record(
    session: AsyncSession,
    user_id: str,
    raw_key: str,
    prefix: str,
    name: str,
) -> ApiKey:
    """Store a hashed API key in the database.

    Args:
        session: The async database session.
        user_id: The owning user's ID.
        raw_key: The raw API key (will be hashed with SHA-256).
        prefix: The first 12 chars of the key.
        name: A user-friendly name for the key.

    Returns:
        The newly created ApiKey record.
    """
    key = ApiKey(
        user_id=user_id,
        key_hash=hash_api_key(raw_key),
        name=name.strip(),
        prefix=prefix,
    )
    session.add(key)
    await session.flush()
    return key


async def get_api_key_by_hash(session: AsyncSession, raw_key: str) -> ApiKey | None:
    """Find an API key by its raw value (hashed for lookup)."""
    key_hash = hash_api_key(raw_key)
    result = await session.execute(
        select(ApiKey).where(
            ApiKey.key_hash == key_hash,
            ApiKey.revoked == False,  # noqa: E712
        )
    )
    return result.scalar_one_or_none()


async def list_api_keys(session: AsyncSession, user_id: str) -> list[ApiKey]:
    """List all API keys for a user (non-revoked)."""
    result = await session.execute(
        select(ApiKey).where(
            ApiKey.user_id == user_id,
            ApiKey.revoked == False,  # noqa: E712
        ).order_by(ApiKey.created_at.desc())
    )
    return list(result.scalars().all())


async def revoke_api_key(session: AsyncSession, key_id: str, user_id: str) -> bool:
    """Revoke an API key. Returns True if found and revoked."""
    result = await session.execute(
        update(ApiKey)
        .where(ApiKey.id == key_id, ApiKey.user_id == user_id)
        .values(revoked=True)
    )
    return result.rowcount > 0


async def touch_api_key(session: AsyncSession, key_id: str) -> None:
    """Update the last_used_at timestamp for an API key."""
    await session.execute(
        update(ApiKey)
        .where(ApiKey.id == key_id)
        .values(last_used_at=datetime.now(timezone.utc))
    )


# ── Project Operations ─────────────────────────────────────────

async def get_or_create_project(
    session: AsyncSession,
    user_id: str,
    slug: str,
    name: str | None = None,
    remote_url: str | None = None,
) -> tuple[Project, bool]:
    """Get an existing project or create a new one.

    Args:
        session: The async database session.
        user_id: The owning user's ID.
        slug: The URL-safe project identifier.
        name: Optional display name (defaults to slug).
        remote_url: Optional git remote URL.

    Returns:
        A tuple of (project, created) where created is True if new.
    """
    result = await session.execute(
        select(Project).where(
            Project.user_id == user_id,
            Project.slug == slug,
        )
    )
    project = result.scalar_one_or_none()
    if project is not None:
        return project, False

    project = Project(
        user_id=user_id,
        slug=slug,
        name=name or slug,
        remote_url=remote_url,
    )
    session.add(project)
    await session.flush()
    return project, True


async def list_projects(session: AsyncSession, user_id: str) -> list[Project]:
    """List all projects for a user."""
    result = await session.execute(
        select(Project)
        .where(Project.user_id == user_id)
        .order_by(Project.updated_at.desc())
    )
    return list(result.scalars().all())
