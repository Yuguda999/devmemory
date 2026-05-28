"""REST API routes for session and context block management."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from devmemory.api.schemas import (
    ContextBlockListResponse,
    ContextBlockResponse,
    MessageResponse,
    SessionListResponse,
    SessionResponse,
    UpdateSessionRequest,
)
from devmemory.auth.middleware import AuthContext, require_jwt_user
from devmemory.db.engine import get_db_session
from devmemory.db.repository import (
    delete_context_block,
    get_context_blocks,
    get_session,
    list_sessions,
    update_session,
)
from devmemory.models.session import SessionStatus

router = APIRouter(tags=["sessions"])

_VALID_STATUSES = {s.value for s in SessionStatus}


# ── Sessions ───────────────────────────────────────────────────────────────────


@router.get(
    "/sessions",
    response_model=SessionListResponse,
    summary="List sessions",
)
async def list_sessions_endpoint(
    project_id: str | None = Query(default=None, description="Filter by project ID"),
    session_status: str | None = Query(default=None, alias="status", description="Filter by status"),
    limit: int = Query(default=25, ge=1, le=100),
    auth: AuthContext = Depends(require_jwt_user),
) -> SessionListResponse:
    """List development sessions for the authenticated user.

    Optionally filter by ``project_id`` and/or ``status``.
    """
    if session_status is not None and session_status not in _VALID_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"status must be one of: {', '.join(sorted(_VALID_STATUSES))}",
        )

    async with get_db_session() as db:
        sessions = await list_sessions(
            db,
            user_id=auth.user_id,
            project_id=project_id,
            status=session_status,
            limit=limit,
        )

    return SessionListResponse(
        sessions=[
            SessionResponse(
                id=str(s.id),
                project_id=str(s.project_id),
                title=s.title,
                status=s.status,
                tool_source=s.tool_source,
                created_at=s.created_at,
                updated_at=s.updated_at,
            )
            for s in sessions
        ],
        count=len(sessions),
    )


@router.get(
    "/sessions/{session_id}",
    response_model=SessionResponse,
    summary="Get a session",
    responses={404: {"description": "Session not found"}},
)
async def get_session_endpoint(
    session_id: str,
    auth: AuthContext = Depends(require_jwt_user),
) -> SessionResponse:
    """Retrieve a single session by ID."""
    async with get_db_session() as db:
        dev_session = await get_session(db, session_id, auth.user_id)

    if dev_session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    return SessionResponse(
        id=str(dev_session.id),
        project_id=str(dev_session.project_id),
        title=dev_session.title,
        status=dev_session.status,
        tool_source=dev_session.tool_source,
        created_at=dev_session.created_at,
        updated_at=dev_session.updated_at,
    )


@router.patch(
    "/sessions/{session_id}",
    response_model=SessionResponse,
    summary="Update a session",
    responses={
        404: {"description": "Session not found"},
        422: {"description": "Invalid status value"},
    },
)
async def update_session_endpoint(
    session_id: str,
    body: UpdateSessionRequest,
    auth: AuthContext = Depends(require_jwt_user),
) -> SessionResponse:
    """Partially update a session's title and/or status.

    At least one of ``title`` or ``status`` must be provided.
    """
    if body.title is None and body.status is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="At least one of title or status must be provided",
        )

    if body.status is not None and body.status not in _VALID_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"status must be one of: {', '.join(sorted(_VALID_STATUSES))}",
        )

    async with get_db_session() as db:
        updated = await update_session(
            db,
            session_id=session_id,
            user_id=auth.user_id,
            status=body.status,
            title=body.title,
        )

    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    return SessionResponse(
        id=str(updated.id),
        project_id=str(updated.project_id),
        title=updated.title,
        status=updated.status,
        tool_source=updated.tool_source,
        created_at=updated.created_at,
        updated_at=updated.updated_at,
    )


# ── Context Blocks ─────────────────────────────────────────────────────────────


@router.get(
    "/sessions/{session_id}/blocks",
    response_model=ContextBlockListResponse,
    summary="List context blocks for a session",
    responses={404: {"description": "Session not found"}},
)
async def list_blocks_endpoint(
    session_id: str,
    block_type: str | None = Query(default=None, description="Filter by block type"),
    limit: int = Query(default=100, ge=1, le=500),
    auth: AuthContext = Depends(require_jwt_user),
) -> ContextBlockListResponse:
    """Retrieve context blocks for a session, ordered by priority then creation time."""
    async with get_db_session() as db:
        blocks = await get_context_blocks(
            db,
            session_id=session_id,
            user_id=auth.user_id,
            block_type=block_type,
            limit=limit,
        )

    if blocks is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    return ContextBlockListResponse(
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


@router.delete(
    "/context-blocks/{block_id}",
    response_model=MessageResponse,
    summary="Delete a context block",
    responses={404: {"description": "Block not found"}},
)
async def delete_block_endpoint(
    block_id: str,
    auth: AuthContext = Depends(require_jwt_user),
) -> MessageResponse:
    """Permanently delete a single context block."""
    async with get_db_session() as db:
        deleted = await delete_context_block(db, block_id, auth.user_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Context block not found",
        )

    return MessageResponse(message="Context block deleted")
