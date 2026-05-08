"""Session model."""

from __future__ import annotations

from enum import Enum

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from devmemory.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class SessionStatus(str, Enum):
    """Session lifecycle status."""

    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class Session(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A development session within a project, typically one task or work-stream."""

    __tablename__ = "sessions"

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    tool_source: Mapped[str] = mapped_column(
        String(50), nullable=False,
        comment="Which AI tool created this session (cursor, claude, windsurf, gemini, etc.)",
    )
    status: Mapped[str] = mapped_column(
        String(20), default=SessionStatus.ACTIVE.value, nullable=False, index=True,
    )

    # ── Relationships ───────────────────────────────────────────
    project: Mapped["Project"] = relationship("Project", back_populates="sessions")  # noqa: F821
    context_blocks: Mapped[list["ContextBlock"]] = relationship(  # noqa: F821
        "ContextBlock", back_populates="session", cascade="all, delete-orphan"
    )

    @property
    def status_enum(self) -> SessionStatus:
        """Return the status as an enum member."""
        return SessionStatus(self.status)

    def __repr__(self) -> str:
        return f"<Session {self.title!r} tool={self.tool_source}>"
