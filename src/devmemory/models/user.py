"""User model."""

from __future__ import annotations

import json

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from devmemory.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

# Default notification preferences. Transactional email (verification, password
# reset, password-changed) is NOT listed here — it is always sent and cannot be
# disabled. Only optional categories are toggleable.
DEFAULT_NOTIFICATION_PREFS: dict[str, bool] = {
    "security_alerts": True,   # new-login, password/email change alerts
    "account_events": True,    # welcome, subscription/plan changes
}


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A registered DevMemory user."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # JSON-encoded notification preferences (see DEFAULT_NOTIFICATION_PREFS).
    # Stored as Text for uniform SQLite/Postgres behaviour, mirroring
    # ContextBlock.meta_json. Access via the ``notification_prefs`` property.
    notification_prefs_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Relationships ───────────────────────────────────────────
    api_keys: Mapped[list[ApiKey]] = relationship(  # noqa: F821
        "ApiKey", back_populates="user", cascade="all, delete-orphan"
    )
    subscription: Mapped[Subscription | None] = relationship(  # noqa: F821
        "Subscription", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    projects: Mapped[list[Project]] = relationship(  # noqa: F821
        "Project", back_populates="user", cascade="all, delete-orphan"
    )
    email_tokens: Mapped[list[EmailToken]] = relationship(  # noqa: F821
        "EmailToken", back_populates="user", cascade="all, delete-orphan"
    )

    @property
    def notification_prefs(self) -> dict[str, bool]:
        """Return notification prefs merged over defaults (defaults win for gaps)."""
        prefs = dict(DEFAULT_NOTIFICATION_PREFS)
        if self.notification_prefs_json:
            try:
                stored = json.loads(self.notification_prefs_json)
                if isinstance(stored, dict):
                    prefs.update({k: bool(v) for k, v in stored.items() if k in prefs})
            except (ValueError, TypeError):
                pass
        return prefs

    @notification_prefs.setter
    def notification_prefs(self, value: dict[str, bool]) -> None:
        """Persist only recognised keys as JSON."""
        clean = {k: bool(v) for k, v in (value or {}).items() if k in DEFAULT_NOTIFICATION_PREFS}
        self.notification_prefs_json = json.dumps(clean) if clean else None

    def __repr__(self) -> str:
        return f"<User {self.email}>"
