"""API-key resolver for MCP tool handlers.

MCP tools authenticate via a DevMemory API key supplied either:
  1. As the ``DEVMEMORY_API_KEY`` environment variable (recommended — set in the
     AI tool's MCP server config, e.g. Claude Desktop ``claude_desktop_config.json``).
  2. As an explicit ``api_key`` argument passed directly to the tool call (fallback
     for environments that cannot inject environment variables).

Usage inside a tool handler::

    user_id = await resolve_mcp_api_key(api_key_arg=api_key)

Raises :exc:`ValueError` with a human-readable message if no valid key is found.
"""

from __future__ import annotations

import os

from devmemory.db.engine import get_db_session
from devmemory.db.repository import (
    get_api_key_by_hash,
    record_tool_connection,
    touch_api_key,
)


_ENV_VAR = "DEVMEMORY_API_KEY"
_CLIENT_ENV_VAR = "DEVMEMORY_CLIENT"


async def resolve_mcp_api_key(api_key_arg: str | None = None) -> str:
    """Resolve an API key to its owning user_id.

    Resolution order:
        1. Explicit ``api_key_arg`` passed to the tool (non-empty string).
        2. ``DEVMEMORY_API_KEY`` environment variable.

    After a successful lookup the key's ``last_used_at`` timestamp is updated.

    Args:
        api_key_arg: Optional key passed directly as a tool argument.

    Returns:
        The ``user_id`` (UUID string) that owns the key.

    Raises:
        ValueError: If no key is provided, the key is not found, or it has
            been revoked.
    """
    raw_key = _pick_key(api_key_arg)

    async with get_db_session() as db:
        api_key = await get_api_key_by_hash(db, raw_key)
        if api_key is None:
            raise ValueError(
                "Invalid or revoked API key. "
                "Generate a key at /auth/api-keys or check your DEVMEMORY_API_KEY."
            )
        await touch_api_key(db, api_key.id)
        user_id = str(api_key.user_id)

        # Heartbeat: record which tool is talking to us so the dashboard can
        # show live connection status. The tool slug is injected as
        # DEVMEMORY_CLIENT by ``devmemory install``; absent that we fall back
        # to "unknown". Never let tracking failures break a tool call.
        client = os.environ.get(_CLIENT_ENV_VAR, "").strip() or "unknown"
        try:
            await record_tool_connection(db, user_id=user_id, client=client)
        except Exception:  # pragma: no cover - tracking is best-effort
            pass

        return user_id


def _pick_key(api_key_arg: str | None) -> str:
    """Return the first non-empty key from the argument or env var.

    Raises:
        ValueError: If neither source provides a non-empty value.
    """
    if api_key_arg and api_key_arg.strip():
        return api_key_arg.strip()

    env_key = os.environ.get(_ENV_VAR, "").strip()
    if env_key:
        return env_key

    raise ValueError(
        f"No API key provided. Pass ``api_key`` as a tool argument or set the "
        f"``{_ENV_VAR}`` environment variable."
    )
