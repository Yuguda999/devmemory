"""DevMemory MCP tools — the core product layer.

Seven tools that AI coding tools (Claude, Cursor, Windsurf, etc.) call via the
Model Context Protocol to persist and retrieve coding context.

Tool list
---------
* save_context          — Save a typed context block to the active session
* get_context           — Retrieve context blocks for the current project/session
* start_session         — Begin a new dev session (auto-resolves project from git)
* end_session           — Mark a session complete or archived
* list_sessions         — List recent sessions for a project
* generate_resume_prompt — Produce an optimised "continue here" prompt
* list_projects         — List all known projects for the user

Authentication
--------------
Every tool accepts an optional ``api_key`` argument. If omitted the
``DEVMEMORY_API_KEY`` environment variable is used as a fallback.  See
:mod:`devmemory.auth.mcp_auth` for details.
"""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from devmemory.auth.mcp_auth import resolve_mcp_api_key
from devmemory.billing.quota import (
    QuotaExceededError,
    check_block_quota,
    check_project_quota,
    check_session_quota,
    get_usage_summary,
)
from devmemory.db.engine import get_db_session
from devmemory.db.repository import (
    create_bulk_context_blocks,
    create_context_block,
    create_session,
    get_context_blocks,
    get_or_create_project,
    get_session,
    list_projects,
    list_sessions,
    update_session,
)
from devmemory.models.context import BlockType
from devmemory.resolver.git_resolver import resolve_project_slug
from devmemory.tools.resume import generate_resume_prompt as _build_resume_prompt

# ── FastMCP instance (imported by server.py) ───────────────────────────────────

mcp = FastMCP(
    name="devmemory",
    instructions=(
        "DevMemory is a persistent memory layer for AI coding tools. "
        "Use save_context to record goals, decisions, code snippets, errors, and next steps. "
        "Use get_context or generate_resume_prompt to restore context when resuming work. "
        "Authenticate via the api_key argument or the DEVMEMORY_API_KEY environment variable."
    ),
)


# ── Helpers ────────────────────────────────────────────────────────────────────


_VALID_BLOCK_TYPES = {bt.value for bt in BlockType}


def _validate_block_type(block_type: str) -> str:
    """Normalise and validate a block_type string."""
    norm = block_type.lower().strip()
    if norm not in _VALID_BLOCK_TYPES:
        valid = ", ".join(sorted(_VALID_BLOCK_TYPES))
        raise ValueError(f"Invalid block_type '{block_type}'. Must be one of: {valid}")
    return norm


def _err(msg: str) -> dict:
    """Standard error response dict."""
    return {"ok": False, "error": msg}


def _ok(**kwargs) -> dict:
    """Standard success response dict."""
    return {"ok": True, **kwargs}


# ── Tool: save_context ─────────────────────────────────────────────────────────


@mcp.tool()
async def save_context(
    block_type: str,
    content: str,
    cwd: str,
    session_id: str | None = None,
    project: str | None = None,
    priority: int = 5,
    api_key: str | None = None,
) -> dict:
    """Save a typed context block to the active session.

    If no ``session_id`` is supplied a new session is automatically created
    (or the most recent active session for the project is reused — caller
    may pass ``session_id`` to be explicit).

    Args:
        block_type: One of: goal, decision, code, error, next_step, note.
        content:    The context content to save.
        cwd:        Working directory — used for automatic project detection
                    via git remote URL.
        session_id: Optional existing session ID to append to.
        project:    Optional explicit project name (overrides git detection).
        priority:   Ordering weight for resume prompts (1–10, default 5).
        api_key:    DevMemory API key. Falls back to DEVMEMORY_API_KEY env var.
    """
    try:
        user_id = await resolve_mcp_api_key(api_key)
        bt = _validate_block_type(block_type)
    except ValueError as exc:
        return _err(str(exc))

    if not content.strip():
        return _err("content must not be empty")
    if not 1 <= priority <= 10:
        return _err("priority must be between 1 and 10")

    async with get_db_session() as db:
        # ── Resolve / create project ──────────────────────────────────────────
        proj_info = await resolve_project_slug(cwd, explicit_project=project)
        proj, proj_is_new = await get_or_create_project(
            db, user_id, proj_info.slug, name=proj_info.name, remote_url=proj_info.remote_url
        )

        # ── Quota: new project ────────────────────────────────────────────────
        if proj_is_new:
            try:
                await check_project_quota(db, user_id)
            except QuotaExceededError as exc:
                return _err(str(exc))

        # ── Resolve session ───────────────────────────────────────────────────
        if session_id:
            dev_session = await get_session(db, session_id, user_id)
            if dev_session is None:
                return _err(f"Session '{session_id}' not found or not accessible")
        else:
            # ── Quota: new session ────────────────────────────────────────────
            try:
                await check_session_quota(db, user_id, str(proj.id))
            except QuotaExceededError as exc:
                return _err(str(exc))

            # Auto-create a session for this project
            dev_session = await create_session(
                db,
                user_id=user_id,
                project_id=str(proj.id),
                title=f"Auto-session ({proj_info.name})",
                tool_source="devmemory-mcp",
            )

        if dev_session is None:
            return _err("Could not resolve or create a session")

        # ── Quota: new block ──────────────────────────────────────────────────
        try:
            await check_block_quota(db, user_id, str(dev_session.id))
        except QuotaExceededError as exc:
            return _err(str(exc))

        # ── Save block ────────────────────────────────────────────────────────
        block = await create_context_block(
            db,
            session_id=str(dev_session.id),
            user_id=user_id,
            block_type=bt,
            content=content.strip(),
            priority=priority,
        )
        if block is None:
            return _err("Failed to save context block")

    return _ok(
        block_id=str(block.id),
        session_id=str(dev_session.id),
        project_slug=proj_info.slug,
        block_type=bt,
    )


# ── Tool: get_context ──────────────────────────────────────────────────────────


@mcp.tool()
async def get_context(
    cwd: str,
    session_id: str | None = None,
    block_type: str | None = None,
    limit: int = 50,
    api_key: str | None = None,
) -> dict:
    """Retrieve context blocks for the current project / session.

    Args:
        cwd:        Working directory — used for project detection if no
                    ``session_id`` is given.
        session_id: Specific session to query. If omitted, the most-recently
                    updated active session for the project is used.
        block_type: Optional filter — return only blocks of this type.
        limit:      Maximum number of blocks to return (default 50).
        api_key:    DevMemory API key. Falls back to DEVMEMORY_API_KEY env var.
    """
    try:
        user_id = await resolve_mcp_api_key(api_key)
    except ValueError as exc:
        return _err(str(exc))

    if block_type is not None:
        try:
            block_type = _validate_block_type(block_type)
        except ValueError as exc:
            return _err(str(exc))

    async with get_db_session() as db:
        # ── Resolve session ───────────────────────────────────────────────────
        if session_id:
            dev_session = await get_session(db, session_id, user_id)
            if dev_session is None:
                return _err(f"Session '{session_id}' not found or not accessible")
            resolved_session_id = session_id
        else:
            proj_info = await resolve_project_slug(cwd)
            proj, _ = await get_or_create_project(
                db, user_id, proj_info.slug, name=proj_info.name
            )
            sessions = await list_sessions(
                db, user_id, project_id=str(proj.id), status="active", limit=1
            )
            if not sessions:
                return _ok(blocks=[], count=0, session_id=None)
            dev_session = sessions[0]
            resolved_session_id = str(dev_session.id)

        blocks = await get_context_blocks(
            db,
            session_id=resolved_session_id,
            user_id=user_id,
            block_type=block_type,
            limit=limit,
        )

    if blocks is None:
        return _err("Session not accessible")

    return _ok(
        session_id=resolved_session_id,
        session_title=dev_session.title,
        blocks=[
            {
                "id": str(b.id),
                "block_type": b.block_type,
                "content": b.content,
                "priority": b.priority,
                "created_at": b.created_at.isoformat(),
            }
            for b in blocks
        ],
        count=len(blocks),
    )


# ── Tool: start_session ────────────────────────────────────────────────────────


@mcp.tool()
async def start_session(
    title: str,
    cwd: str,
    tool_source: str = "unknown",
    project: str | None = None,
    api_key: str | None = None,
) -> dict:
    """Begin a new development session.

    Automatically resolves the project from the git remote URL in ``cwd``
    (or creates a new project if one doesn't exist yet).

    Args:
        title:       Human-readable session title, e.g. "Implement auth layer".
        cwd:         Working directory — used for git-based project detection.
        tool_source: The AI tool starting this session (e.g. "claude", "cursor").
        project:     Optional explicit project name override.
        api_key:     DevMemory API key. Falls back to DEVMEMORY_API_KEY env var.
    """
    try:
        user_id = await resolve_mcp_api_key(api_key)
    except ValueError as exc:
        return _err(str(exc))

    if not title.strip():
        return _err("title must not be empty")

    async with get_db_session() as db:
        proj_info = await resolve_project_slug(cwd, explicit_project=project)
        proj, proj_created = await get_or_create_project(
            db, user_id, proj_info.slug, name=proj_info.name, remote_url=proj_info.remote_url
        )

        # ── Quota: new project ────────────────────────────────────────────────
        if proj_created:
            try:
                await check_project_quota(db, user_id)
            except QuotaExceededError as exc:
                return _err(str(exc))

        # ── Quota: new session ────────────────────────────────────────────────
        try:
            await check_session_quota(db, user_id, str(proj.id))
        except QuotaExceededError as exc:
            return _err(str(exc))

        dev_session = await create_session(
            db,
            user_id=user_id,
            project_id=str(proj.id),
            title=title.strip(),
            tool_source=tool_source.lower().strip() or "unknown",
        )

    if dev_session is None:
        return _err("Failed to create session")

    return _ok(
        session_id=str(dev_session.id),
        project_id=str(proj.id),
        project_slug=proj_info.slug,
        project_name=proj_info.name,
        project_created=proj_created,
    )


# ── Tool: end_session ──────────────────────────────────────────────────────────


@mcp.tool()
async def end_session(
    session_id: str,
    status: str = "completed",
    api_key: str | None = None,
) -> dict:
    """Mark a session as completed or archived.

    Args:
        session_id: The session ID returned by ``start_session``.
        status:     One of: completed, archived, paused (default: completed).
        api_key:    DevMemory API key. Falls back to DEVMEMORY_API_KEY env var.
    """
    try:
        user_id = await resolve_mcp_api_key(api_key)
    except ValueError as exc:
        return _err(str(exc))

    valid_statuses = {"completed", "archived", "paused"}
    if status not in valid_statuses:
        return _err(f"status must be one of: {', '.join(sorted(valid_statuses))}")

    async with get_db_session() as db:
        updated = await update_session(db, session_id, user_id, status=status)

    if updated is None:
        return _err(f"Session '{session_id}' not found or not accessible")

    return _ok(session_id=session_id, status=status)


# ── Tool: list_sessions ────────────────────────────────────────────────────────


@mcp.tool()
async def list_sessions_tool(
    cwd: str,
    project: str | None = None,
    status: str | None = None,
    limit: int = 10,
    api_key: str | None = None,
) -> dict:
    """List recent development sessions for the current project.

    Args:
        cwd:     Working directory — used for project detection.
        project: Optional explicit project name override.
        status:  Optional filter: active, paused, completed, archived.
        limit:   Maximum sessions to return (default 10).
        api_key: DevMemory API key. Falls back to DEVMEMORY_API_KEY env var.
    """
    try:
        user_id = await resolve_mcp_api_key(api_key)
    except ValueError as exc:
        return _err(str(exc))

    async with get_db_session() as db:
        proj_info = await resolve_project_slug(cwd, explicit_project=project)
        proj, _ = await get_or_create_project(
            db, user_id, proj_info.slug, name=proj_info.name
        )

        sessions = await list_sessions(
            db,
            user_id=user_id,
            project_id=str(proj.id),
            status=status,
            limit=limit,
        )

    return _ok(
        project_slug=proj_info.slug,
        sessions=[
            {
                "id": str(s.id),
                "title": s.title,
                "status": s.status,
                "tool_source": s.tool_source,
                "created_at": s.created_at.isoformat(),
                "updated_at": s.updated_at.isoformat(),
            }
            for s in sessions
        ],
        count=len(sessions),
    )


# ── Tool: generate_resume_prompt ───────────────────────────────────────────────


@mcp.tool()
async def generate_resume_prompt(
    session_id: str,
    target_tool: str = "generic",
    api_key: str | None = None,
) -> dict:
    """Generate an optimised "continue here" prompt for switching AI tools.

    Retrieves all context blocks for the given session and assembles them into
    a structured prompt, ordered by semantic priority (goals → decisions →
    code → errors → next steps → notes).

    Args:
        session_id:  The session to generate a prompt for.
        target_tool: Tailors the preamble: claude, cursor, windsurf, or generic.
        api_key:     DevMemory API key. Falls back to DEVMEMORY_API_KEY env var.
    """
    try:
        user_id = await resolve_mcp_api_key(api_key)
    except ValueError as exc:
        return _err(str(exc))

    async with get_db_session() as db:
        dev_session = await get_session(db, session_id, user_id)
        if dev_session is None:
            return _err(f"Session '{session_id}' not found or not accessible")

        blocks = await get_context_blocks(
            db, session_id=session_id, user_id=user_id, limit=200
        )

    if blocks is None:
        return _err("Could not load context blocks")

    project_name = dev_session.project.name if dev_session.project else "Unknown Project"
    prompt = _build_resume_prompt(
        project_name=project_name,
        session_title=dev_session.title,
        blocks=blocks,
        target_tool=target_tool,
    )

    return _ok(
        session_id=session_id,
        target_tool=target_tool,
        block_count=len(blocks),
        prompt=prompt,
    )


# ── Tool: list_projects ────────────────────────────────────────────────────────


@mcp.tool()
async def list_projects_tool(api_key: str | None = None) -> dict:
    """List all projects known to DevMemory for this account.

    Also returns current usage vs tier limits so clients can surface
    upgrade prompts when the user is near their quota.

    Args:
        api_key: DevMemory API key. Falls back to DEVMEMORY_API_KEY env var.
    """
    try:
        user_id = await resolve_mcp_api_key(api_key)
    except ValueError as exc:
        return _err(str(exc))

    async with get_db_session() as db:
        projects = await list_projects(db, user_id)
        usage = await get_usage_summary(db, user_id)

    return _ok(
        projects=[
            {
                "id": str(p.id),
                "slug": p.slug,
                "name": p.name,
                "remote_url": p.remote_url,
                "created_at": p.created_at.isoformat(),
                "updated_at": p.updated_at.isoformat(),
            }
            for p in projects
        ],
        count=len(projects),
        quota=usage,
    )
