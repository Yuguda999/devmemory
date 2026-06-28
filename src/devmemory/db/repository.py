"""Database repository — all CRUD operations, scoped by user_id."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from devmemory.auth.hashing import hash_api_key, hash_password
from devmemory.models import (
    ApiKey,
    ContextBlock,
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


async def get_user_with_subscription(session: AsyncSession, user_id: str) -> User | None:
    """Find a user by ID with subscription eagerly loaded.

    Use this when you need to access ``user.subscription`` outside the session.
    """
    result = await session.execute(
        select(User)
        .where(User.id == user_id)
        .options(selectinload(User.subscription))
    )
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


async def get_project_by_id(
    session: AsyncSession, project_id: str, user_id: str,
) -> Project | None:
    """Get a single project by ID, scoped to user."""
    result = await session.execute(
        select(Project).where(Project.id == project_id, Project.user_id == user_id)
    )
    return result.scalar_one_or_none()


# ── Session Operations ─────────────────────────────────────────


async def create_session(
    session: AsyncSession,
    user_id: str,
    project_id: str,
    title: str,
    tool_source: str,
) -> Session | None:
    """Create a new development session within a project.

    Verifies the project belongs to the user before creating.

    Args:
        session: The async database session.
        user_id: The owning user's ID (for ownership check).
        project_id: The project to attach the session to.
        title: Human-readable session title.
        tool_source: Which AI tool created this session.

    Returns:
        The newly created Session, or None if project not owned by user.
    """
    # Verify ownership
    project = await get_project_by_id(session, project_id, user_id)
    if project is None:
        return None

    dev_session = Session(
        project_id=project_id,
        title=title.strip(),
        tool_source=tool_source.strip().lower(),
    )
    session.add(dev_session)
    await session.flush()
    return dev_session


async def get_session(
    session: AsyncSession, session_id: str, user_id: str,
) -> Session | None:
    """Get a session by ID with context blocks eagerly loaded.

    Enforces user ownership via the project relationship.
    """
    result = await session.execute(
        select(Session)
        .join(Project, Session.project_id == Project.id)
        .where(Session.id == session_id, Project.user_id == user_id)
        .options(
            selectinload(Session.context_blocks),
            selectinload(Session.project),
        )
    )
    return result.scalar_one_or_none()


async def list_sessions(
    session: AsyncSession,
    user_id: str,
    project_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[Session]:
    """List sessions for a user, optionally filtered by project and status.

    Args:
        session: The async database session.
        user_id: The owning user's ID.
        project_id: Optional project filter.
        status: Optional status filter (active, paused, completed, archived).
        limit: Maximum number of sessions to return.

    Returns:
        List of sessions, ordered by most recently updated first.
    """
    stmt = (
        select(Session)
        .join(Project, Session.project_id == Project.id)
        .where(Project.user_id == user_id)
    )
    if project_id is not None:
        stmt = stmt.where(Session.project_id == project_id)
    if status is not None:
        stmt = stmt.where(Session.status == status)

    stmt = stmt.order_by(Session.updated_at.desc()).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def update_session(
    session: AsyncSession,
    session_id: str,
    user_id: str,
    status: str | None = None,
    title: str | None = None,
) -> Session | None:
    """Update a session's status and/or title.

    Enforces user ownership via the project relationship.

    Returns:
        The updated Session, or None if not found or not owned by user.
    """
    dev_session = await get_session(session, session_id, user_id)
    if dev_session is None:
        return None

    if status is not None:
        dev_session.status = status
    if title is not None:
        dev_session.title = title.strip()

    await session.flush()
    return dev_session


# ── Context Block Operations ───────────────────────────────────


async def create_context_block(
    session: AsyncSession,
    session_id: str,
    user_id: str,
    block_type: str,
    content: str,
    meta_json: str | None = None,
    priority: int = 5,
) -> ContextBlock | None:
    """Save a single context block to a session.

    Verifies user ownership of the session's parent project.

    Args:
        session: The async database session.
        session_id: The session to attach the block to.
        user_id: The owning user's ID (for ownership check).
        block_type: One of the BlockType enum values.
        content: The context content text.
        meta_json: Optional JSON-encoded metadata string.
        priority: Priority for resume prompt ordering (1-10, default 5).

    Returns:
        The newly created ContextBlock, or None if session not accessible.
    """
    # Verify session ownership
    dev_session = await get_session(session, session_id, user_id)
    if dev_session is None:
        return None

    block = ContextBlock(
        session_id=session_id,
        block_type=block_type,
        content=content,
        meta_json=meta_json,
        priority=priority,
    )
    session.add(block)
    await session.flush()
    return block


async def create_bulk_context_blocks(
    session: AsyncSession,
    session_id: str,
    user_id: str,
    blocks: list[dict],
) -> list[ContextBlock] | None:
    """Save multiple context blocks to a session in one call.

    Each dict in *blocks* must have at minimum ``block_type`` and ``content``.
    Optional keys: ``meta_json``, ``priority``.

    Returns:
        List of created ContextBlock objects, or None if session not accessible.
    """
    dev_session = await get_session(session, session_id, user_id)
    if dev_session is None:
        return None

    created: list[ContextBlock] = []
    for block_data in blocks:
        block = ContextBlock(
            session_id=session_id,
            block_type=block_data["block_type"],
            content=block_data["content"],
            meta_json=block_data.get("meta_json"),
            priority=block_data.get("priority", 5),
        )
        session.add(block)
        created.append(block)

    await session.flush()
    return created


async def get_context_blocks(
    session: AsyncSession,
    session_id: str,
    user_id: str,
    block_type: str | None = None,
    limit: int = 100,
) -> list[ContextBlock] | None:
    """Retrieve context blocks for a session, optionally filtered by type.

    Returns:
        List of context blocks ordered by priority (desc) then created_at,
        or None if the session is not accessible to the user.
    """
    # Verify session ownership
    dev_session = await get_session(session, session_id, user_id)
    if dev_session is None:
        return None

    stmt = select(ContextBlock).where(ContextBlock.session_id == session_id)
    if block_type is not None:
        stmt = stmt.where(ContextBlock.block_type == block_type)

    stmt = (
        stmt.order_by(ContextBlock.priority.desc(), ContextBlock.created_at.asc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def update_context_block(
    session: AsyncSession,
    block_id: str,
    user_id: str,
    content: str | None = None,
    priority: int | None = None,
) -> ContextBlock | None:
    """Update a context block's content and/or priority.

    Enforces user ownership by joining through session → project → user.

    Returns:
        The updated ContextBlock, or None if not found or not owned by user.
    """
    result = await session.execute(
        select(ContextBlock)
        .join(Session, ContextBlock.session_id == Session.id)
        .join(Project, Session.project_id == Project.id)
        .where(ContextBlock.id == block_id, Project.user_id == user_id)
    )
    block = result.scalar_one_or_none()
    if block is None:
        return None

    if content is not None:
        block.content = content
    if priority is not None:
        block.priority = priority

    await session.flush()
    return block


async def delete_context_block(
    session: AsyncSession, block_id: str, user_id: str,
) -> bool:
    """Delete a context block by ID.

    Enforces user ownership by joining through session → project → user.

    Returns:
        True if the block was found and deleted, False otherwise.
    """
    result = await session.execute(
        select(ContextBlock)
        .join(Session, ContextBlock.session_id == Session.id)
        .join(Project, Session.project_id == Project.id)
        .where(ContextBlock.id == block_id, Project.user_id == user_id)
    )
    block = result.scalar_one_or_none()
    if block is None:
        return False

    await session.delete(block)
    await session.flush()
    return True


async def get_context_block_by_id(
    session: AsyncSession, block_id: str, user_id: str,
) -> ContextBlock | None:
    """Get a context block by ID.

    Enforces user ownership by joining through session → project → user.
    """
    result = await session.execute(
        select(ContextBlock)
        .join(Session, ContextBlock.session_id == Session.id)
        .join(Project, Session.project_id == Project.id)
        .where(ContextBlock.id == block_id, Project.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def update_context_block_status(
    session: AsyncSession,
    block_id: str,
    user_id: str,
    status: str,
) -> ContextBlock | None:
    """Update only the status field in a task block's meta_json.

    Enforces user ownership by joining through session → project → user.

    Returns:
        The updated ContextBlock, or None if not found or not owned by user.
    """
    block = await get_context_block_by_id(session, block_id, user_id)
    if block is None:
        return None

    # Load existing metadata or create new
    meta = block.extra_metadata
    meta["status"] = status
    block.extra_metadata = meta

    await session.flush()
    return block
