"""Billing quota enforcement — tier-based usage limits.

Tier limits
-----------
- FREE  : 10 projects, 30 sessions per project, 1500 context blocks per session
- PRO   : 25 projects, 100 sessions per project, 5 000 context blocks per session
- TEAM  : unlimited (capped only by DB sanity limits)

Usage inside tool handlers::

    from devmemory.billing.quota import check_project_quota, check_session_quota
    from devmemory.billing.quota import check_block_quota, QuotaExceededError

    await check_project_quota(db, user_id)     # raises QuotaExceededError if over limit
    await check_session_quota(db, user_id, project_id)
    await check_block_quota(db, user_id, session_id)
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from devmemory.models.context import ContextBlock
from devmemory.models.project import Project
from devmemory.models.session import Session
from devmemory.models.subscription import Subscription, SubscriptionTier

# ── Quota limits by tier ───────────────────────────────────────────────────────

_UNLIMITED = 2**31  # sentinel for "no practical limit"


@dataclass(frozen=True)
class TierQuota:
    """Usage limits for a single subscription tier."""

    max_projects: int
    max_sessions_per_project: int
    max_blocks_per_session: int


_TIER_QUOTAS: dict[str, TierQuota] = {
    SubscriptionTier.FREE.value: TierQuota(
        # Personal single-tenant deployment: the per-turn Stop hook and
        # multi-project use across tools make the original 3/10/500 caps too
        # tight. Kept as a named tier rather than switched to _UNLIMITED so the
        # billing dashboard still shows finite numbers.
        max_projects=10,
        max_sessions_per_project=30,
        max_blocks_per_session=1500,
    ),
    SubscriptionTier.PRO.value: TierQuota(
        max_projects=25,
        max_sessions_per_project=100,
        max_blocks_per_session=5_000,
    ),
    SubscriptionTier.TEAM.value: TierQuota(
        max_projects=_UNLIMITED,
        max_sessions_per_project=_UNLIMITED,
        max_blocks_per_session=_UNLIMITED,
    ),
}


class QuotaExceededError(Exception):
    """Raised when a user's usage would exceed their tier limit."""

    def __init__(self, message: str, tier: str, limit: int, current: int) -> None:
        super().__init__(message)
        self.tier = tier
        self.limit = limit
        self.current = current


# ── Internal helpers ───────────────────────────────────────────────────────────


async def _get_tier(db: AsyncSession, user_id: str) -> str:
    """Return the subscription tier string for a user, defaulting to FREE."""
    result = await db.execute(select(Subscription.tier).where(Subscription.user_id == user_id))
    tier = result.scalar_one_or_none()
    return tier if tier is not None else SubscriptionTier.FREE.value


def _quota_for(tier: str) -> TierQuota:
    """Return the TierQuota for a tier string, falling back to FREE."""
    return _TIER_QUOTAS.get(tier, _TIER_QUOTAS[SubscriptionTier.FREE.value])


# ── Public enforcement functions ───────────────────────────────────────────────


async def check_project_quota(db: AsyncSession, user_id: str) -> None:
    """Raise QuotaExceededError if the user is at their project limit.

    Args:
        db:      Active async database session.
        user_id: The user whose quota to check.

    Raises:
        QuotaExceededError: If creating a new project would exceed the tier limit.
    """
    tier = await _get_tier(db, user_id)
    quota = _quota_for(tier)

    if quota.max_projects >= _UNLIMITED:
        return

    result = await db.execute(
        select(func.count()).select_from(Project).where(Project.user_id == user_id)
    )
    count = result.scalar_one()

    if count >= quota.max_projects:
        raise QuotaExceededError(
            f"Project limit reached for {tier} tier ({quota.max_projects} projects). "
            "Upgrade to Pro to create more projects.",
            tier=tier,
            limit=quota.max_projects,
            current=count,
        )


async def check_session_quota(db: AsyncSession, user_id: str, project_id: str) -> None:
    """Raise QuotaExceededError if the user is at their sessions-per-project limit.

    Args:
        db:         Active async database session.
        user_id:    The user whose quota to check.
        project_id: The project to count sessions within.

    Raises:
        QuotaExceededError: If creating a new session would exceed the tier limit.
    """
    tier = await _get_tier(db, user_id)
    quota = _quota_for(tier)

    if quota.max_sessions_per_project >= _UNLIMITED:
        return

    result = await db.execute(
        select(func.count()).select_from(Session).where(Session.project_id == project_id)
    )
    count = result.scalar_one()

    if count >= quota.max_sessions_per_project:
        raise QuotaExceededError(
            f"Session limit reached for {tier} tier "
            f"({quota.max_sessions_per_project} sessions per project). "
            "Upgrade to Pro for more sessions.",
            tier=tier,
            limit=quota.max_sessions_per_project,
            current=count,
        )


async def check_block_quota(
    db: AsyncSession,
    user_id: str,
    session_id: str,  # noqa: ARG001
) -> None:
    """Raise QuotaExceededError if the session is at its context block limit.

    Args:
        db:         Active async database session.
        user_id:    The user whose quota to check (used for tier lookup).
        session_id: The session to count blocks within.

    Raises:
        QuotaExceededError: If saving a new block would exceed the tier limit.
    """
    tier = await _get_tier(db, user_id)
    quota = _quota_for(tier)

    if quota.max_blocks_per_session >= _UNLIMITED:
        return

    result = await db.execute(
        select(func.count()).select_from(ContextBlock).where(ContextBlock.session_id == session_id)
    )
    count = result.scalar_one()

    if count >= quota.max_blocks_per_session:
        raise QuotaExceededError(
            f"Context block limit reached for {tier} tier "
            f"({quota.max_blocks_per_session} blocks per session). "
            "Upgrade to Pro for more storage.",
            tier=tier,
            limit=quota.max_blocks_per_session,
            current=count,
        )


async def get_usage_summary(db: AsyncSession, user_id: str) -> dict:
    """Return a summary of current usage vs tier limits.

    Useful for dashboard endpoints and the ``/billing/status`` REST route.

    Returns:
        A dict with ``tier``, ``limits``, and ``usage`` keys.
    """
    tier = await _get_tier(db, user_id)
    quota = _quota_for(tier)

    project_count_result = await db.execute(
        select(func.count()).select_from(Project).where(Project.user_id == user_id)
    )
    project_count = project_count_result.scalar_one()

    total_sessions_result = await db.execute(
        select(func.count())
        .select_from(Session)
        .join(Project, Session.project_id == Project.id)
        .where(Project.user_id == user_id)
    )
    total_sessions = total_sessions_result.scalar_one()

    return {
        "tier": tier,
        "limits": {
            "max_projects": quota.max_projects if quota.max_projects < _UNLIMITED else None,
            "max_sessions_per_project": (
                quota.max_sessions_per_project
                if quota.max_sessions_per_project < _UNLIMITED
                else None
            ),
            "max_blocks_per_session": (
                quota.max_blocks_per_session if quota.max_blocks_per_session < _UNLIMITED else None
            ),
        },
        "usage": {
            "projects": project_count,
            "total_sessions": total_sessions,
        },
    }
