"""Email token model — single-use tokens for verification and password reset."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from devmemory.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class EmailTokenPurpose(str, Enum):
    """What an email token authorises."""

    VERIFY_EMAIL = "verify_email"
    RESET_PASSWORD = "reset_password"


class EmailToken(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A single-use, expiring token delivered by email.

    Only the SHA-256 hash of the raw token is stored — the raw value lives only
    in the email link. Used for signup email verification and password reset.
    """

    __tablename__ = "email_tokens"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    purpose: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="One of: verify_email, reset_password",
    )
    token_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True, comment="SHA-256 hex of raw token"
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # ── Relationships ───────────────────────────────────────────
    user: Mapped[User] = relationship("User", back_populates="email_tokens")  # noqa: F821

    @property
    def is_valid(self) -> bool:
        """True when the token is unused and not expired."""
        if self.used_at is not None:
            return False
        expires = self.expires_at
        # Normalise naive datetimes (SQLite may drop tzinfo on read) to UTC.
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        return expires > datetime.now(timezone.utc)

    def __repr__(self) -> str:
        return f"<EmailToken purpose={self.purpose} used={self.used_at is not None}>"
