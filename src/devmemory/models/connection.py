"""ToolConnection model — tracks which AI tools are connected via MCP.

Each MCP server runs as a per-tool stdio subprocess, so there is no central
socket the dashboard can poll. Instead, every MCP process records a heartbeat
(``last_seen_at``) keyed by ``(user_id, client)`` whenever it authenticates a
tool call. The dashboard derives a live/idle/offline status from how recently
that heartbeat fired.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from devmemory.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, _utcnow


class ToolConnection(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A heartbeat record for one AI tool connected to DevMemory via MCP."""

    __tablename__ = "tool_connections"
    __table_args__ = (UniqueConstraint("user_id", "client", name="uq_tool_connection_user_client"),)

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    client: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Tool slug from DEVMEMORY_CLIENT or MCP clientInfo (cursor, claude-code, ...)",
    )
    client_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<ToolConnection user={self.user_id} client={self.client!r}>"
