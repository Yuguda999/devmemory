"""Database repository — all CRUD operations, scoped by user_id."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from devmemory.auth.hashing import (
    generate_email_token,
    hash_api_key,
    hash_password,
    hash_token,
)
from devmemory.models import (
    ApiKey,
    ContextBlock,
    EmailToken,
    Invoice,
    InvoiceStatus,
    Project,
    Session,
    Subscription,
    SubscriptionTier,
    ToolConnection,
    User,
)

# ── User Operations ────────────────────────────────────────────


async def create_user(
    session: AsyncSession,
    email: str,
    password: str,
    display_name: str,
    email_verified: bool = False,
) -> User:
    """Register a new user with a free-tier subscription.

    Args:
        session: The async database session.
        email: The user's email address.
        password: The user's plaintext password (will be hashed).
        display_name: The user's display name.
        email_verified: Whether to mark the email already verified (self-hosted
            / guest accounts, or when email delivery is not configured).

    Returns:
        The newly created User.
    """
    user = User(
        email=email.lower().strip(),
        password_hash=hash_password(password),
        display_name=display_name.strip(),
        email_verified=email_verified,
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
    result = await session.execute(select(User).where(User.email == email.lower().strip()))
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
        select(User).where(User.id == user_id).options(selectinload(User.subscription))
    )
    return result.scalar_one_or_none()


async def update_user_password(
    session: AsyncSession,
    user_id: str,
    new_password: str,
) -> User | None:
    """Set a new (hashed) password for a user. Returns the user or None."""
    user = await get_user_by_id(session, user_id)
    if user is None:
        return None
    user.password_hash = hash_password(new_password)
    await session.flush()
    return user


async def update_user_profile(
    session: AsyncSession,
    user_id: str,
    display_name: str,
) -> User | None:
    """Update a user's editable profile fields. Returns the user or None."""
    user = await get_user_by_id(session, user_id)
    if user is None:
        return None
    user.display_name = display_name.strip()
    await session.flush()
    return user


async def mark_email_verified(session: AsyncSession, user_id: str) -> User | None:
    """Flag a user's current email as verified. Returns the user or None."""
    user = await get_user_by_id(session, user_id)
    if user is None:
        return None
    user.email_verified = True
    await session.flush()
    return user


async def set_notification_prefs(
    session: AsyncSession,
    user_id: str,
    prefs: dict[str, bool],
) -> User | None:
    """Merge and persist a user's notification preferences. Returns the user."""
    user = await get_user_by_id(session, user_id)
    if user is None:
        return None
    merged = user.notification_prefs
    merged.update(prefs)
    user.notification_prefs = merged
    await session.flush()
    return user


# ── Email Token Operations (verification + password reset) ─────


async def create_email_token(
    session: AsyncSession,
    user_id: str,
    purpose: str,
    expires_at: datetime,
) -> str:
    """Create a single-use email token and return the RAW token (email it once).

    Any prior unused tokens of the same purpose for this user are invalidated so
    only the newest link works.
    """
    await invalidate_email_tokens(session, user_id, purpose)

    raw_token = generate_email_token()
    token = EmailToken(
        user_id=user_id,
        purpose=purpose,
        token_hash=hash_token(raw_token),
        expires_at=expires_at,
    )
    session.add(token)
    await session.flush()
    return raw_token


async def get_valid_email_token(
    session: AsyncSession,
    raw_token: str,
    purpose: str,
) -> EmailToken | None:
    """Look up an unused, unexpired token by its raw value and purpose."""
    result = await session.execute(
        select(EmailToken).where(
            EmailToken.token_hash == hash_token(raw_token),
            EmailToken.purpose == purpose,
        )
    )
    token = result.scalar_one_or_none()
    if token is None or not token.is_valid:
        return None
    return token


async def consume_email_token(session: AsyncSession, token: EmailToken) -> None:
    """Mark a token used so it cannot be replayed."""
    token.used_at = datetime.now(timezone.utc)
    await session.flush()


async def invalidate_email_tokens(
    session: AsyncSession,
    user_id: str,
    purpose: str,
) -> None:
    """Mark all of a user's still-unused tokens of a purpose as used."""
    await session.execute(
        update(EmailToken)
        .where(
            EmailToken.user_id == user_id,
            EmailToken.purpose == purpose,
            EmailToken.used_at.is_(None),
        )
        .values(used_at=datetime.now(timezone.utc))
    )


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
        select(ApiKey)
        .where(
            ApiKey.user_id == user_id,
            ApiKey.revoked == False,  # noqa: E712
        )
        .order_by(ApiKey.created_at.desc())
    )
    return list(result.scalars().all())


async def revoke_api_key(session: AsyncSession, key_id: str, user_id: str) -> bool:
    """Revoke an API key. Returns True if found and revoked."""
    result = await session.execute(
        update(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == user_id).values(revoked=True)
    )
    return result.rowcount > 0


async def touch_api_key(session: AsyncSession, key_id: str) -> None:
    """Update the last_used_at timestamp for an API key."""
    await session.execute(
        update(ApiKey).where(ApiKey.id == key_id).values(last_used_at=datetime.now(timezone.utc))
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
        select(Project).where(Project.user_id == user_id).order_by(Project.updated_at.desc())
    )
    return list(result.scalars().all())


async def get_project_by_id(
    session: AsyncSession,
    project_id: str,
    user_id: str,
) -> Project | None:
    """Get a single project by ID, scoped to user."""
    result = await session.execute(
        select(Project).where(Project.id == project_id, Project.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def get_project_by_slug(
    session: AsyncSession,
    user_id: str,
    slug: str,
) -> Project | None:
    """Get a single project by slug, scoped to user (read-only — never creates)."""
    result = await session.execute(
        select(Project).where(Project.user_id == user_id, Project.slug == slug)
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
    session: AsyncSession,
    session_id: str,
    user_id: str,
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

    stmt = stmt.order_by(ContextBlock.priority.desc(), ContextBlock.created_at.asc()).limit(limit)
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
    session: AsyncSession,
    block_id: str,
    user_id: str,
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
    session: AsyncSession,
    block_id: str,
    user_id: str,
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


# ── Tool Connection Operations ─────────────────────────────────


async def record_tool_connection(
    session: AsyncSession,
    user_id: str,
    client: str,
    client_version: str | None = None,
) -> ToolConnection:
    """Upsert a heartbeat for an AI tool connected via MCP.

    Creates the ``(user_id, client)`` row on first contact, otherwise refreshes
    ``last_seen_at`` (and ``client_version`` when supplied). Called on every
    authenticated MCP tool call so the dashboard can show live connection status.

    Returns:
        The created or updated ToolConnection.
    """
    client = (client or "unknown").lower().strip() or "unknown"
    now = datetime.now(timezone.utc)

    result = await session.execute(
        select(ToolConnection).where(
            ToolConnection.user_id == user_id,
            ToolConnection.client == client,
        )
    )
    conn = result.scalar_one_or_none()

    if conn is None:
        conn = ToolConnection(
            user_id=user_id,
            client=client,
            client_version=client_version,
            last_seen_at=now,
        )
        session.add(conn)
    else:
        conn.last_seen_at = now
        if client_version:
            conn.client_version = client_version

    await session.flush()
    return conn


async def list_tool_connections(
    session: AsyncSession,
    user_id: str,
) -> list[ToolConnection]:
    """Return all tool connections for a user, most-recently-seen first."""
    result = await session.execute(
        select(ToolConnection)
        .where(ToolConnection.user_id == user_id)
        .order_by(ToolConnection.last_seen_at.desc())
    )
    return list(result.scalars().all())


# ── Invoice / Payment Operations ───────────────────────────────


async def next_derivation_index(session: AsyncSession) -> int:
    """Return the next unused HD address index (global, monotonic).

    Each invoice derives a unique receiving address at this index. A unique
    constraint on the column plus create-time retry guards against the rare race
    where two concurrent invoices pick the same index.
    """
    from sqlalchemy import func

    result = await session.execute(select(func.max(Invoice.derivation_index)))
    current = result.scalar_one_or_none()
    return 0 if current is None else current + 1


async def create_invoice(
    session: AsyncSession,
    *,
    user_id: str,
    tier: str,
    amount_lovelace: int,
    pay_to_address: str,
    derivation_index: int,
    network: str,
    expires_at: datetime,
) -> Invoice:
    """Create a pending payment invoice."""
    invoice = Invoice(
        user_id=user_id,
        tier=tier,
        amount_lovelace=amount_lovelace,
        pay_to_address=pay_to_address,
        derivation_index=derivation_index,
        network=network,
        expires_at=expires_at,
        status=InvoiceStatus.PENDING.value,
    )
    session.add(invoice)
    await session.flush()
    return invoice


async def list_pending_invoices(session: AsyncSession, limit: int = 100) -> list[Invoice]:
    """Return pending invoices, oldest first — used by the background poller."""
    result = await session.execute(
        select(Invoice)
        .where(Invoice.status == InvoiceStatus.PENDING.value)
        .order_by(Invoice.created_at.asc())
        .limit(limit)
    )
    return list(result.scalars().all())


# ── Admin Operations (superadmin panel) ────────────────────────


async def platform_stats(session: AsyncSession) -> dict:
    """Return platform-wide counts for the admin overview."""

    async def _count(model, *where) -> int:
        stmt = select(func.count()).select_from(model)
        for w in where:
            stmt = stmt.where(w)
        return int(await session.scalar(stmt) or 0)

    tier_rows = await session.execute(
        select(Subscription.tier, func.count()).group_by(Subscription.tier)
    )
    revenue_lovelace = int(
        await session.scalar(
            select(func.coalesce(func.sum(Invoice.amount_lovelace), 0)).where(
                Invoice.status == InvoiceStatus.PAID.value
            )
        )
        or 0
    )
    return {
        "users_total": await _count(User),
        "users_active": await _count(User, User.is_active.is_(True)),
        "users_verified": await _count(User, User.email_verified.is_(True)),
        "tiers": dict(tier_rows.all()),
        "projects": await _count(Project),
        "sessions": await _count(Session),
        "context_blocks": await _count(ContextBlock),
        "invoices_paid": await _count(Invoice, Invoice.status == InvoiceStatus.PAID.value),
        "invoices_pending": await _count(Invoice, Invoice.status == InvoiceStatus.PENDING.value),
        "revenue_ada": revenue_lovelace / 1_000_000,
    }


async def list_users_admin(
    session: AsyncSession,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[User], dict[str, int], dict[str, int], int]:
    """Return (users, project_counts, session_counts, total) for the admin table."""
    q = select(User).options(selectinload(User.subscription))
    if search:
        q = q.where(User.email.ilike(f"%{search.strip()}%"))
    total = int(await session.scalar(select(func.count()).select_from(q.subquery())) or 0)

    users = list(
        (
            await session.execute(q.order_by(User.created_at.desc()).limit(limit).offset(offset))
        )
        .scalars()
        .all()
    )
    ids = [u.id for u in users]
    proj_counts: dict[str, int] = {}
    sess_counts: dict[str, int] = {}
    if ids:
        pr = await session.execute(
            select(Project.user_id, func.count())
            .where(Project.user_id.in_(ids))
            .group_by(Project.user_id)
        )
        proj_counts = {uid: int(c) for uid, c in pr.all()}
        sr = await session.execute(
            select(Project.user_id, func.count(Session.id))
            .join(Session, Session.project_id == Project.id)
            .where(Project.user_id.in_(ids))
            .group_by(Project.user_id)
        )
        sess_counts = {uid: int(c) for uid, c in sr.all()}
    return users, proj_counts, sess_counts, total


async def admin_update_user(
    session: AsyncSession,
    user_id: str,
    *,
    tier: str | None = None,
    is_active: bool | None = None,
    is_admin: bool | None = None,
) -> User | None:
    """Update admin-controllable fields on a user. Returns the updated user."""
    result = await session.execute(
        select(User).where(User.id == user_id).options(selectinload(User.subscription))
    )
    user = result.scalar_one_or_none()
    if user is None:
        return None

    if is_active is not None:
        user.is_active = is_active
    if is_admin is not None:
        user.is_admin = is_admin
    if tier is not None:
        if user.subscription is None:
            user.subscription = Subscription(user_id=user.id, tier=tier)
            session.add(user.subscription)
        else:
            user.subscription.tier = tier
    await session.flush()
    return user


async def list_invoices_admin(
    session: AsyncSession,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[tuple[Invoice, str]], int]:
    """Return ([(invoice, user_email)], total) for the admin payments table."""
    q = select(Invoice, User.email).join(User, User.id == Invoice.user_id)
    if status:
        q = q.where(Invoice.status == status)
    total = int(await session.scalar(select(func.count()).select_from(q.subquery())) or 0)
    rows = (
        await session.execute(q.order_by(Invoice.created_at.desc()).limit(limit).offset(offset))
    ).all()
    return [(inv, email) for inv, email in rows], total


async def get_invoice(session: AsyncSession, invoice_id: str, user_id: str) -> Invoice | None:
    """Return an invoice by id, scoped to its owner."""
    result = await session.execute(
        select(Invoice).where(Invoice.id == invoice_id, Invoice.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def mark_invoice_paid(
    session: AsyncSession,
    invoice: Invoice,
    tx_hash: str,
) -> None:
    """Mark an invoice paid and record the settling transaction."""
    invoice.status = InvoiceStatus.PAID.value
    invoice.tx_hash = tx_hash
    invoice.paid_at = datetime.now(timezone.utc)
    await session.flush()


async def mark_invoice_expired(session: AsyncSession, invoice: Invoice) -> None:
    """Mark an invoice expired."""
    invoice.status = InvoiceStatus.EXPIRED.value
    await session.flush()


async def apply_tier_upgrade(
    session: AsyncSession,
    *,
    user_id: str,
    tier: str,
    invoice_id: str,
    tx_hash: str,
    period_end: datetime,
) -> Subscription | None:
    """Upgrade a user's subscription to a paid tier after a confirmed payment."""
    result = await session.execute(
        select(Subscription).where(Subscription.user_id == user_id)
    )
    subscription = result.scalar_one_or_none()
    if subscription is None:
        subscription = Subscription(user_id=user_id)
        session.add(subscription)

    subscription.tier = tier
    subscription.status = "active"
    subscription.last_invoice_id = invoice_id
    subscription.last_tx_hash = tx_hash
    subscription.current_period_start = datetime.now(timezone.utc)
    subscription.current_period_end = period_end
    await session.flush()
    return subscription
