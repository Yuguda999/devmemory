"""Invoice settlement — shared by the REST poll endpoint and the background poller.

Given a pending invoice, checks Blockfrost for a matching on-chain payment to the
invoice's unique address and, if found, marks it paid and upgrades the user's
subscription. Idempotent and safe to call repeatedly.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from devmemory.billing.cardano import find_matching_payment
from devmemory.config import settings
from devmemory.db.repository import (
    apply_tier_upgrade,
    mark_invoice_expired,
    mark_invoice_paid,
)
from devmemory.models.invoice import Invoice, InvoiceStatus


async def settle_invoice(db: AsyncSession, invoice: Invoice) -> Invoice:
    """Advance a pending invoice: expire it, or confirm payment + upgrade tier.

    Returns the (possibly mutated) invoice. Terminal invoices are returned
    unchanged. Raises CardanoConfigError/BlockfrostError from the Blockfrost call.
    """
    if invoice.status != InvoiceStatus.PENDING.value:
        return invoice

    if datetime.now(timezone.utc) >= invoice.expires_at:
        await mark_invoice_expired(db, invoice)
        return invoice

    tx_hash = await find_matching_payment(invoice.pay_to_address, invoice.amount_lovelace)
    if tx_hash:
        await _confirm(db, invoice, tx_hash)
    return invoice


async def _confirm(db: AsyncSession, invoice: Invoice, tx_hash: str) -> None:
    await mark_invoice_paid(db, invoice, tx_hash)
    period_end = datetime.now(timezone.utc) + timedelta(days=settings.cardano_subscription_days)
    await apply_tier_upgrade(
        db,
        user_id=invoice.user_id,
        tier=invoice.tier,
        invoice_id=invoice.id,
        tx_hash=tx_hash,
        period_end=period_end,
    )
