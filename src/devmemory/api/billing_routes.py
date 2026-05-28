"""REST API routes for billing and quota status."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from devmemory.api.schemas import BillingLimits, BillingStatusResponse, BillingUsage
from devmemory.auth.middleware import AuthContext, require_jwt_user
from devmemory.billing.quota import get_usage_summary
from devmemory.db.engine import get_db_session

router = APIRouter(prefix="/billing", tags=["billing"])


@router.get(
    "/status",
    response_model=BillingStatusResponse,
    summary="Get billing status and quota usage",
)
async def billing_status(
    auth: AuthContext = Depends(require_jwt_user),
) -> BillingStatusResponse:
    """Return the current tier, quota limits, and usage counts for the account.

    Use this endpoint to surface upgrade prompts in a dashboard when the user
    is approaching their tier limits.
    """
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
