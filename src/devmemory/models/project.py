"""Project model."""

from __future__ import annotations

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from devmemory.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Project(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A development project, auto-detected from git or created manually."""

    __tablename__ = "projects"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    slug: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="URL-safe identifier derived from git remote or explicit name",
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Human-readable display name",
    )
    remote_url: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Git remote origin URL, used for cross-machine project matching",
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Relationships ───────────────────────────────────────────
    user: Mapped[User] = relationship("User", back_populates="projects")  # noqa: F821
    sessions: Mapped[list[Session]] = relationship(  # noqa: F821
        "Session", back_populates="project", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Project {self.slug}>"
