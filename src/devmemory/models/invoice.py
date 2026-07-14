"""Cardano payment invoice model.

An invoice is a one-time ADA payment request that upgrades a user's tier once
the exact amount is received at the receiving address. Identity is by *unique
amount*: each pending invoice is assigned a base tier price plus a small random
lovelace offset, so a single receive address can disambiguate concurrent
payments without per-invoice address derivation.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from devmemory.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class InvoiceStatus(str, Enum):
    """Invoice lifecycle status."""

    PENDING = "pending"
    PAID = "paid"
    EXPIRED = "expired"


class Invoice(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A one-time ADA payment request for a tier upgrade."""

    __tablename__ = "invoices"

    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Target tier this invoice upgrades to when paid ("pro" | "team").
    tier: Mapped[str] = mapped_column(String(20), nullable=False)
    # Exact expected amount, in lovelace (1 ADA = 1_000_000 lovelace). BigInteger
    # because amounts exceed 32-bit once denominated in lovelace.
    amount_lovelace: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # The address the user must pay, and which network it lives on. The address
    # is derived from the merchant account xpub at ``derivation_index`` — unique
    # per invoice so a plain round-amount payment is unambiguously identified.
    pay_to_address: Mapped[str] = mapped_column(String(255), nullable=False)
    derivation_index: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    network: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default=InvoiceStatus.PENDING.value, nullable=False, index=True
    )
    # Set once a matching on-chain payment is confirmed.
    tx_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    @property
    def amount_ada(self) -> float:
        """Return the expected amount denominated in ADA."""
        return self.amount_lovelace / 1_000_000

    def __repr__(self) -> str:
        return f"<Invoice user_id={self.user_id} tier={self.tier} status={self.status}>"
