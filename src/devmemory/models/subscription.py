"""Subscription model."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from devmemory.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class SubscriptionTier(str, Enum):
    """Available subscription tiers."""

    FREE = "free"
    PRO = "pro"
    TEAM = "team"


class SubscriptionStatus(str, Enum):
    """Subscription lifecycle status."""

    ACTIVE = "active"
    CANCELED = "canceled"
    PAST_DUE = "past_due"


class Subscription(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A user's subscription tier and billing status."""

    __tablename__ = "subscriptions"

    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    tier: Mapped[str] = mapped_column(
        String(20), default=SubscriptionTier.FREE.value, nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), default=SubscriptionStatus.ACTIVE.value, nullable=False
    )

    # Stripe fields — null for self-hosted
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    current_period_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    current_period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ── Relationships ───────────────────────────────────────────
    user: Mapped["User"] = relationship("User", back_populates="subscription")  # noqa: F821

    @property
    def is_active(self) -> bool:
        """Return True if subscription is active."""
        return self.status == SubscriptionStatus.ACTIVE.value

    @property
    def tier_enum(self) -> SubscriptionTier:
        """Return the tier as an enum member."""
        return SubscriptionTier(self.tier)

    def __repr__(self) -> str:
        return f"<Subscription user_id={self.user_id} tier={self.tier}>"
