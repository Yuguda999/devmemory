"""Context routes — API-key (or JWT) authenticated context + task endpoints.

These endpoints back the DevMemory MCP client. In hosted mode the MCP client
runs on the user's machine and calls these over HTTPS with an API key; the
server (which owns the database) performs the writes. Git/project resolution
happens client-side, so write requests carry a resolved ``ProjectRef`` rather
than a working directory.

Endpoints
---------
GET   /context/resume              — resume prompt via ``cwd`` (legacy, local only)
POST  /context                     — save one typed context block (save_context)
POST  /context/tasks               — save a batch of task blocks (save_tasks)
PATCH /context/blocks/{id}/status  — update a task block's status (update_task)
GET   /context                     — get blocks for a project/session (get_context)
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query, status

from devmemory.api.schemas import (
    ContextBlockResponse,
    GetContextResponse,
    SaveContextRequest,
    SaveContextResponse,
    SaveTasksRequest,
    SaveTasksResponse,
    TaskStatusResponse,
    UpdateTaskStatusRequest,
)
from devmemory.auth.middleware import AuthContext, require_api_key_user, require_user
from devmemory.billing.quota import (
    QuotaExceededError,
    check_block_quota,
    check_project_quota,
    check_session_quota,
)
from devmemory.db.engine import get_db_session
from devmemory.db.repository import (
    create_bulk_context_blocks,
    create_context_block,
    create_session,
    get_context_blocks,
    get_or_create_project,
    get_project_by_slug,
    get_session,
    list_sessions,
    update_context_block_status,
)
from devmemory.models.context import BlockType
from devmemory.resolver.git_resolver import resolve_project_slug
from devmemory.tools.resume import generate_resume_prompt

router = APIRouter(prefix="/context", tags=["context"])

_VALID_BLOCK_TYPES = {bt.value for bt in BlockType}
_VALID_TASK_STATUSES = {"pending", "in_progress", "done", "skipped"}


# ── Helpers ─────────────────────────────────────────────────────────────────────


def _quota_error(exc: QuotaExceededError) -> HTTPException:
    """Map a quota violation to HTTP 402 so clients can surface an upgrade prompt."""
    return HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=str(exc))


def _validate_block_type(block_type: str) -> str:
    norm = block_type.lower().strip()
    if norm not in _VALID_BLOCK_TYPES:
        valid = ", ".join(sorted(_VALID_BLOCK_TYPES))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Invalid block_type '{block_type}'. Must be one of: {valid}",
        )
    return norm


async def _resolve_target_session(db, user_id, proj, proj_is_new, session_id):
    """Return an existing/active/new session for a write, honoring quota.

    Mirrors the resolution the save_context / save_tasks MCP tools performed:
    explicit session_id → reuse; else newest active session; else create one.
    """
    if proj_is_new:
        try:
            await check_project_quota(db, user_id)
        except QuotaExceededError as exc:
            raise _quota_error(exc) from exc

    if session_id:
        dev_session = await get_session(db, session_id, user_id)
        if dev_session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session '{session_id}' not found or not accessible",
            )
        return dev_session

    active = await list_sessions(db, user_id, project_id=str(proj.id), status="active", limit=1)
    if active:
        return active[0]

    try:
        await check_session_quota(db, user_id, str(proj.id))
    except QuotaExceededError as exc:
        raise _quota_error(exc) from exc

    dev_session = await create_session(
        db,
        user_id=user_id,
        project_id=str(proj.id),
        title=f"Auto-session ({proj.name})",
        tool_source="devmemory-mcp",
    )
    if dev_session is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not resolve or create a session",
        )
    return dev_session


# ── Legacy: resume-by-cwd (used by local `devmemory inject`) ─────────────────────


@router.get(
    "/resume",
    summary="Get resume prompt for the current project",
    response_model=None,
)
async def get_resume_prompt(
    cwd: str = Query(..., description="Absolute path to the project working directory"),
    target_tool: str = Query(
        default="generic",
        description="Target tool preamble: claude, cursor, windsurf, augment, or generic",
    ),
    auth: AuthContext = Depends(require_api_key_user),
) -> dict:
    """Return a resume prompt for the latest active session in the project at ``cwd``.

    Local/self-hosted only: git resolution runs on the server, so ``cwd`` must
    exist on the same machine. Hosted clients use ``GET /sessions/{id}/resume``.

    Authentication: ``X-API-Key: dm_key_...`` header.
    """
    async with get_db_session() as db:
        proj_info = await resolve_project_slug(cwd)
        proj, _ = await get_or_create_project(db, auth.user_id, proj_info.slug, name=proj_info.name)

        sessions = await list_sessions(
            db, auth.user_id, project_id=str(proj.id), status="active", limit=1
        )

        if not sessions:
            return {
                "ok": True,
                "has_context": False,
                "project": proj_info.name,
                "session_id": None,
                "prompt": None,
                "message": (
                    f"No active session found for project '{proj_info.name}'. "
                    "Start one with `devmemory start`."
                ),
            }

        dev_session = sessions[0]
        blocks = await get_context_blocks(
            db,
            session_id=str(dev_session.id),
            user_id=auth.user_id,
            limit=200,
        )

    if not blocks:
        return {
            "ok": True,
            "has_context": False,
            "project": proj_info.name,
            "session_id": str(dev_session.id),
            "prompt": None,
            "message": "Active session exists but has no context blocks yet.",
        }

    prompt = generate_resume_prompt(
        project_name=proj_info.name,
        session_title=dev_session.title,
        blocks=blocks,
        target_tool=target_tool,
        session_id=str(dev_session.id),
    )

    return {
        "ok": True,
        "has_context": True,
        "project": proj_info.name,
        "session_id": str(dev_session.id),
        "session_title": dev_session.title,
        "block_count": len(blocks),
        "prompt": prompt,
    }


# ── save_context ─────────────────────────────────────────────────────────────────


@router.post(
    "",
    response_model=SaveContextResponse,
    summary="Save a context block",
    responses={402: {"description": "Quota exceeded"}, 404: {"description": "Session not found"}},
)
async def save_context_endpoint(
    body: SaveContextRequest,
    auth: AuthContext = Depends(require_user),
) -> SaveContextResponse:
    """Persist a single typed context block, auto-creating the project/session."""
    block_type = _validate_block_type(body.block_type)

    async with get_db_session() as db:
        proj, proj_is_new = await get_or_create_project(
            db,
            auth.user_id,
            body.project.slug,
            name=body.project.name,
            remote_url=body.project.remote_url,
        )
        dev_session = await _resolve_target_session(
            db, auth.user_id, proj, proj_is_new, body.session_id
        )

        try:
            await check_block_quota(db, auth.user_id, str(dev_session.id))
        except QuotaExceededError as exc:
            raise _quota_error(exc) from exc

        block = await create_context_block(
            db,
            session_id=str(dev_session.id),
            user_id=auth.user_id,
            block_type=block_type,
            content=body.content.strip(),
            priority=body.priority,
        )
        if block is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to save context block",
            )

        return SaveContextResponse(
            block_id=str(block.id),
            session_id=str(dev_session.id),
            project_slug=proj.slug,
            block_type=block_type,
        )


# ── save_tasks ───────────────────────────────────────────────────────────────────


@router.post(
    "/tasks",
    response_model=SaveTasksResponse,
    summary="Save a batch of task blocks",
    responses={402: {"description": "Quota exceeded"}, 404: {"description": "Session not found"}},
)
async def save_tasks_endpoint(
    body: SaveTasksRequest,
    auth: AuthContext = Depends(require_user),
) -> SaveTasksResponse:
    """Persist a list of tasks as individual 'task' context blocks."""
    async with get_db_session() as db:
        proj, proj_is_new = await get_or_create_project(
            db,
            auth.user_id,
            body.project.slug,
            name=body.project.name,
            remote_url=body.project.remote_url,
        )
        dev_session = await _resolve_target_session(
            db, auth.user_id, proj, proj_is_new, body.session_id
        )

        try:
            await check_block_quota(db, auth.user_id, str(dev_session.id))
        except QuotaExceededError as exc:
            raise _quota_error(exc) from exc

        blocks_data = []
        for i, t in enumerate(body.tasks):
            content = t.title
            if t.description:
                content += f"\n\n{t.description}"
            blocks_data.append(
                {
                    "block_type": "task",
                    "content": content.strip(),
                    "priority": t.priority,
                    "meta_json": json.dumps({"status": "pending", "index": i}),
                }
            )

        blocks = await create_bulk_context_blocks(
            db,
            session_id=str(dev_session.id),
            user_id=auth.user_id,
            blocks=blocks_data,
        )
        if blocks is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to save task blocks",
            )

        return SaveTasksResponse(
            session_id=str(dev_session.id),
            project_slug=proj.slug,
            task_ids=[str(b.id) for b in blocks],
        )


# ── update_task ──────────────────────────────────────────────────────────────────


@router.patch(
    "/blocks/{block_id}/status",
    response_model=TaskStatusResponse,
    summary="Update a task block's status",
    responses={
        404: {"description": "Task block not found"},
        422: {"description": "Invalid status"},
    },
)
async def update_task_status_endpoint(
    block_id: str,
    body: UpdateTaskStatusRequest,
    auth: AuthContext = Depends(require_user),
) -> TaskStatusResponse:
    """Update a task's status (pending, in_progress, done, skipped)."""
    if body.status not in _VALID_TASK_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"status must be one of: {', '.join(sorted(_VALID_TASK_STATUSES))}",
        )

    async with get_db_session() as db:
        block = await update_context_block_status(db, block_id, auth.user_id, body.status)

    if block is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task block '{block_id}' not found or not accessible",
        )

    return TaskStatusResponse(block_id=block_id, status=body.status)


# ── get_context ──────────────────────────────────────────────────────────────────


@router.get(
    "",
    response_model=GetContextResponse,
    summary="Get context blocks for a project or session",
    responses={404: {"description": "Session not found"}},
)
async def get_context_endpoint(
    project_slug: str | None = Query(
        default=None, description="Project slug (resolved client-side)"
    ),
    session_id: str | None = Query(default=None, description="Explicit session to read"),
    block_type: str | None = Query(default=None, description="Filter by block type"),
    limit: int = Query(default=50, ge=1, le=500),
    auth: AuthContext = Depends(require_user),
) -> GetContextResponse:
    """Return context blocks for an explicit ``session_id`` or, failing that, the
    latest active session of ``project_slug``. One of the two must be provided."""
    if block_type is not None:
        block_type = _validate_block_type(block_type)

    if not session_id and not project_slug:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Provide either session_id or project_slug",
        )

    async with get_db_session() as db:
        if session_id:
            dev_session = await get_session(db, session_id, auth.user_id)
            if dev_session is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Session '{session_id}' not found or not accessible",
                )
        else:
            proj = await get_project_by_slug(db, auth.user_id, project_slug)
            if proj is None:
                return GetContextResponse(session_id=None, blocks=[], count=0)
            sessions = await list_sessions(
                db, auth.user_id, project_id=str(proj.id), status="active", limit=1
            )
            if not sessions:
                return GetContextResponse(session_id=None, blocks=[], count=0)
            dev_session = sessions[0]

        blocks = await get_context_blocks(
            db,
            session_id=str(dev_session.id),
            user_id=auth.user_id,
            block_type=block_type,
            limit=limit,
        )

    if blocks is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not accessible",
        )

    return GetContextResponse(
        session_id=str(dev_session.id),
        session_title=dev_session.title,
        blocks=[
            ContextBlockResponse(
                id=str(b.id),
                session_id=str(b.session_id),
                block_type=b.block_type,
                content=b.content,
                priority=b.priority,
                meta_json=b.meta_json,
                created_at=b.created_at,
                updated_at=b.updated_at,
            )
            for b in blocks
        ],
        count=len(blocks),
    )
