"""API Key model."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from devmemory.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ApiKey(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An API key for authenticating MCP and REST requests."""

    __tablename__ = "api_keys"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    prefix: Mapped[str] = mapped_column(
        String(16), nullable=False, index=True,
        comment="First 12 chars of the key for identification (e.g. dm_key_a1b2)",
    )
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ── Relationships ───────────────────────────────────────────
    user: Mapped["User"] = relationship("User", back_populates="api_keys")  # noqa: F821

    def __repr__(self) -> str:
        return f"<ApiKey {self.prefix}... name={self.name!r}>"
