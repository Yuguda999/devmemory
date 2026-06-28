"""Context block model — the core unit of stored developer context."""

from __future__ import annotations

import json
from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from devmemory.models.base import Base, UUIDPrimaryKeyMixin, _utcnow


class BlockType(str, Enum):
    """Types of context blocks that can be stored."""

    GOAL = "goal"
    DECISION = "decision"
    CODE = "code"
    FILE_REF = "file_ref"
    ERROR = "error"
    INSIGHT = "insight"
    NEXT_STEP = "next_step"
    DEPENDENCY = "dependency"
    BLOCKER = "blocker"
    TASK = "task"
    NOTE = "note"


class ContextBlock(UUIDPrimaryKeyMixin, Base):
    """A single unit of structured developer context.

    Context blocks are the atomic pieces of memory that agents save and retrieve.
    Each block has a type, content, optional metadata, and a priority for ordering
    in resume prompts.
    """

    __tablename__ = "context_blocks"

    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    block_type: Mapped[str] = mapped_column(
        String(30), nullable=False, index=True,
        comment="One of: goal, decision, code, file_ref, error, insight, next_step, dependency, blocker, task, note",
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    meta_json: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="JSON-encoded metadata (file_path, language, line_range, tags, etc.)",
    )
    priority: Mapped[int] = mapped_column(
        Integer, default=5, nullable=False,
        comment="1-10 priority for resume prompt ordering (10 = highest)",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False,
    )

    # ── Relationships ───────────────────────────────────────────
    session: Mapped["Session"] = relationship(  # noqa: F821
        "Session", back_populates="context_blocks"
    )

    @property
    def block_type_enum(self) -> BlockType:
        """Return the block_type as an enum member."""
        return BlockType(self.block_type)

    @property
    def extra_metadata(self) -> dict:
        """Parse and return the metadata JSON, or empty dict."""
        if self.meta_json:
            return json.loads(self.meta_json)
        return {}

    @extra_metadata.setter
    def extra_metadata(self, value: dict) -> None:
        """Serialize a dict to JSON and store it."""
        self.meta_json = json.dumps(value) if value else None

    def __repr__(self) -> str:
        preview = self.content[:50] + "..." if len(self.content) > 50 else self.content
        return f"<ContextBlock type={self.block_type} preview={preview!r}>"
