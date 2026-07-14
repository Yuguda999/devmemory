"""REST API routes for billing, quota status, and Cardano payments.

Payment model (pull / unique-address):
- ``POST /billing/upgrade`` derives a fresh receiving address for the invoice
  from the merchant account xpub and returns it with a clean round ADA amount.
- The user sends that amount to the address from any Cardano wallet.
- ``GET /billing/invoice/{id}`` (and a background poller) settle the invoice:
  when the payment is confirmed on-chain the subscription is upgraded.

Requires a Blockfrost project id + the merchant account xpub (``cardano_*`` /
``blockfrost_*`` settings). No webhook, no payment-processor account.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError

from devmemory.api.schemas import (
    BillingLimits,
    BillingStatusResponse,
    BillingUsage,
    InvoiceResponse,
    UpgradeRequest,
)
from devmemory.auth.middleware import AuthContext, require_jwt_user
from devmemory.billing.cardano import BlockfrostError, CardanoConfigError, ada_to_lovelace
from devmemory.billing.cardano_hd import CardanoHDError, derive_address
from devmemory.billing.quota import get_usage_summary
from devmemory.billing.settlement import settle_invoice
from devmemory.config import settings
from devmemory.db.engine import get_db_session
from devmemory.db.repository import (
    apply_tier_upgrade,
    create_invoice,
    get_invoice,
    mark_invoice_paid,
    next_derivation_index,
)
from devmemory.models.invoice import Invoice, InvoiceStatus

router = APIRouter(prefix="/billing", tags=["billing"])

_PAID_TIERS = ("pro", "team")
_INDEX_RETRIES = 5


@router.get(
    "/status",
    response_model=BillingStatusResponse,
    summary="Get billing status and quota usage",
)
async def billing_status(
    auth: AuthContext = Depends(require_jwt_user),
) -> BillingStatusResponse:
    """Return the current tier, quota limits, and usage counts for the account."""
    async with get_db_session() as db:
        summary = await get_usage_summary(db, auth.user_id)

    return BillingStatusResponse(
        tier=summary["tier"],
        limits=BillingLimits(
            max_projects=summary["limits"]["max_projects"],
            max_sessions_per_project=summary["limits"]["max_sessions_per_project"],
            max_blocks_per_session=summary["limits"]["max_blocks_per_session"],
        ),
        usage=BillingUsage(
            projects=summary["usage"]["projects"],
            total_sessions=summary["usage"]["total_sessions"],
        ),
    )


def _tier_price_ada(tier: str) -> float:
    return settings.cardano_price_pro_ada if tier == "pro" else settings.cardano_price_team_ada


def _to_response(invoice: Invoice) -> InvoiceResponse:
    return InvoiceResponse(
        invoice_id=invoice.id,
        tier=invoice.tier,
        status=invoice.status,
        network=invoice.network,
        pay_to_address=invoice.pay_to_address,
        amount_lovelace=invoice.amount_lovelace,
        amount_ada=invoice.amount_ada,
        expires_at=invoice.expires_at.isoformat(),
        tx_hash=invoice.tx_hash,
    )


def _require_payments_enabled() -> None:
    if not settings.payments_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cardano payments are not configured on this server.",
        )


@router.post(
    "/upgrade",
    response_model=InvoiceResponse,
    summary="Create a Cardano payment invoice to upgrade tier",
)
async def create_upgrade_invoice(
    body: UpgradeRequest,
    auth: AuthContext = Depends(require_jwt_user),
) -> InvoiceResponse:
    """Create an invoice for a paid tier: pay the round amount to the unique address."""
    _require_payments_enabled()

    tier = body.tier.lower().strip()
    if tier not in _PAID_TIERS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Invalid tier '{body.tier}'. Must be one of: {', '.join(_PAID_TIERS)}",
        )

    amount_lovelace = ada_to_lovelace(_tier_price_ada(tier))
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=settings.cardano_invoice_expiry_minutes
    )

    async with get_db_session() as db:
        # Allocate a unique HD index → unique address. Retry on the rare race
        # where two concurrent invoices grab the same index (unique constraint).
        for _ in range(_INDEX_RETRIES):
            index = await next_derivation_index(db)
            try:
                address = derive_address(
                    settings.cardano_account_xpub, index, settings.blockfrost_network
                )
            except CardanoHDError as exc:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
                ) from exc
            try:
                invoice = await create_invoice(
                    db,
                    user_id=auth.user_id,
                    tier=tier,
                    amount_lovelace=amount_lovelace,
                    pay_to_address=address,
                    derivation_index=index,
                    network=settings.blockfrost_network,
                    expires_at=expires_at,
                )
                return _to_response(invoice)
            except IntegrityError:
                await db.rollback()
                continue

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Could not allocate a unique payment address. Try again shortly.",
        )


@router.get(
    "/invoice/{invoice_id}",
    response_model=InvoiceResponse,
    summary="Check invoice payment status (polls Blockfrost)",
)
async def check_invoice(
    invoice_id: str,
    auth: AuthContext = Depends(require_jwt_user),
) -> InvoiceResponse:
    """Return invoice status; if still pending, settle it against Blockfrost now."""
    _require_payments_enabled()

    async with get_db_session() as db:
        invoice = await get_invoice(db, invoice_id, auth.user_id)
        if invoice is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")

        try:
            await settle_invoice(db, invoice)
        except CardanoConfigError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
            ) from exc
        except BlockfrostError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Payment provider error: {exc}",
            ) from exc

        return _to_response(invoice)


@router.post(
    "/invoice/{invoice_id}/simulate-paid",
    response_model=InvoiceResponse,
    summary="DEV ONLY: mark an invoice paid without an on-chain payment",
)
async def simulate_paid(
    invoice_id: str,
    auth: AuthContext = Depends(require_jwt_user),
) -> InvoiceResponse:
    """Testing shortcut — confirms an invoice + upgrades tier with a fake tx.

    Gated behind ``cardano_allow_test_payments`` so it is inert in production.
    """
    if not settings.cardano_allow_test_payments:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    async with get_db_session() as db:
        invoice = await get_invoice(db, invoice_id, auth.user_id)
        if invoice is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
        if invoice.status == InvoiceStatus.PENDING.value:
            await mark_invoice_paid(db, invoice, "SIMULATED-TEST-TX")
            period_end = datetime.now(timezone.utc) + timedelta(
                days=settings.cardano_subscription_days
            )
            await apply_tier_upgrade(
                db,
                user_id=auth.user_id,
                tier=invoice.tier,
                invoice_id=invoice.id,
                tx_hash="SIMULATED-TEST-TX",
                period_end=period_end,
            )
        return _to_response(invoice)
