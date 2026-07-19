"""Background poller that auto-confirms Cardano payments.

Runs as an asyncio task for the lifetime of the REST server. Every
``cardano_poll_interval_seconds`` it settles all pending invoices, so a user's
tier upgrades on its own once payment lands — no manual "check" needed. The
per-invoice REST poll endpoint remains as an on-demand fast path.
"""

from __future__ import annotations

import asyncio
import logging

from devmemory.billing.settlement import settle_invoice
from devmemory.config import settings
from devmemory.db.engine import get_db_session
from devmemory.db.repository import list_pending_invoices

logger = logging.getLogger("devmemory.billing.poller")


async def _poll_once() -> None:
    async with get_db_session() as db:
        pending = await list_pending_invoices(db)
        for invoice in pending:
            try:
                await settle_invoice(db, invoice)
            except Exception as exc:  # never let one bad invoice kill the loop
                logger.warning("poll: invoice %s settle failed: %s", invoice.id, exc)


async def run_poller() -> None:
    """Loop forever, settling pending invoices on an interval. Cancellation-safe."""
    interval = max(5, settings.cardano_poll_interval_seconds)
    logger.info("Cardano payment poller started (every %ss)", interval)
    while True:
        try:
            await _poll_once()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("poll cycle error: %s", exc)
        await asyncio.sleep(interval)
