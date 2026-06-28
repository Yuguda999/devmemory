"""REST API routes for connected-tool status.

Surfaces the heartbeats recorded by MCP processes (see
``devmemory.auth.mcp_auth``) so the dashboard can show which AI tools are
currently connected.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends

from devmemory.api.schemas import ToolConnectionListResponse, ToolConnectionResponse
from devmemory.auth.middleware import AuthContext, require_jwt_user
from devmemory.db.engine import get_db_session
from devmemory.db.repository import list_tool_connections

router = APIRouter(tags=["connections"])

# Freshness windows for deriving live status from the last heartbeat.
_CONNECTED_WINDOW = timedelta(minutes=5)
_IDLE_WINDOW = timedelta(hours=1)


def _derive_status(last_seen_at: datetime, now: datetime) -> str:
    """Map a last-seen timestamp to connected / idle / offline."""
    # Stored timestamps are tz-aware; guard against naive values just in case.
    if last_seen_at.tzinfo is None:
        last_seen_at = last_seen_at.replace(tzinfo=timezone.utc)
    age = now - last_seen_at
    if age <= _CONNECTED_WINDOW:
        return "connected"
    if age <= _IDLE_WINDOW:
        return "idle"
    return "offline"


@router.get(
    "/connections",
    response_model=ToolConnectionListResponse,
    summary="List connected AI tools",
)
async def list_connections_endpoint(
    auth: AuthContext = Depends(require_jwt_user),
) -> ToolConnectionListResponse:
    """List the AI tools that have connected via MCP, with live status.

    Status is derived from the most recent heartbeat: ``connected`` (seen in the
    last 5 minutes), ``idle`` (last hour), or ``offline``.
    """
    now = datetime.now(timezone.utc)

    async with get_db_session() as db:
        connections = await list_tool_connections(db, user_id=auth.user_id)

    return ToolConnectionListResponse(
        connections=[
            ToolConnectionResponse(
                client=c.client,
                client_version=c.client_version,
                status=_derive_status(c.last_seen_at, now),
                last_seen_at=c.last_seen_at,
                first_seen_at=c.created_at,
            )
            for c in connections
        ],
        count=len(connections),
    )
