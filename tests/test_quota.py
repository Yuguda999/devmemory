"""Unit tests for devmemory.billing.quota.

All DB interactions are mocked — no real database required.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from devmemory.billing.quota import (
    QuotaExceededError,
    TierQuota,
    _UNLIMITED,
    _quota_for,
    check_block_quota,
    check_project_quota,
    check_session_quota,
    get_usage_summary,
)
from devmemory.models.subscription import SubscriptionTier


# ── Fixtures ───────────────────────────────────────────────────────────────────


def _mock_db(scalar_return: int, tier: str = SubscriptionTier.FREE.value) -> AsyncMock:
    """Return an AsyncMock db session whose execute().scalar_one*() returns fixed values."""
    db = AsyncMock()

    # First execute call returns the tier; subsequent calls return the count.
    tier_result = MagicMock()
    tier_result.scalar_one_or_none.return_value = tier

    count_result = MagicMock()
    count_result.scalar_one.return_value = scalar_return

    db.execute.side_effect = [tier_result, count_result]
    return db


def _mock_db_multi(tier: str, *counts: int) -> AsyncMock:
    """Return a db mock whose successive scalar results are tier then each count."""
    db = AsyncMock()
    results = []

    tier_result = MagicMock()
    tier_result.scalar_one_or_none.return_value = tier
    results.append(tier_result)

    for c in counts:
        r = MagicMock()
        r.scalar_one.return_value = c
        results.append(r)

    db.execute.side_effect = results
    return db


# ── _quota_for ─────────────────────────────────────────────────────────────────


def test_quota_for_free():
    q = _quota_for(SubscriptionTier.FREE.value)
    assert q.max_projects == 3
    assert q.max_sessions_per_project == 10
    assert q.max_blocks_per_session == 500


def test_quota_for_pro():
    q = _quota_for(SubscriptionTier.PRO.value)
    assert q.max_projects == 25
    assert q.max_sessions_per_project == 100
    assert q.max_blocks_per_session == 5_000


def test_quota_for_team():
    q = _quota_for(SubscriptionTier.TEAM.value)
    assert q.max_projects >= _UNLIMITED
    assert q.max_sessions_per_project >= _UNLIMITED
    assert q.max_blocks_per_session >= _UNLIMITED


def test_quota_for_unknown_tier_falls_back_to_free():
    q = _quota_for("enterprise_future_tier")
    assert q == _quota_for(SubscriptionTier.FREE.value)


# ── check_project_quota ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_check_project_quota_under_limit():
    """Should pass silently when project count is below the tier limit."""
    db = _mock_db(scalar_return=2, tier=SubscriptionTier.FREE.value)
    # 2 < 3 (free limit) — no exception expected
    await check_project_quota(db, user_id="user-1")


@pytest.mark.asyncio
async def test_check_project_quota_at_limit_raises():
    """Should raise when project count equals the tier limit."""
    db = _mock_db(scalar_return=3, tier=SubscriptionTier.FREE.value)
    with pytest.raises(QuotaExceededError) as exc_info:
        await check_project_quota(db, user_id="user-1")

    err = exc_info.value
    assert err.tier == SubscriptionTier.FREE.value
    assert err.limit == 3
    assert err.current == 3
    assert "Upgrade" in str(err)


@pytest.mark.asyncio
async def test_check_project_quota_over_limit_raises():
    db = _mock_db(scalar_return=5, tier=SubscriptionTier.FREE.value)
    with pytest.raises(QuotaExceededError):
        await check_project_quota(db, user_id="user-1")


@pytest.mark.asyncio
async def test_check_project_quota_pro_under_limit():
    db = _mock_db(scalar_return=20, tier=SubscriptionTier.PRO.value)
    await check_project_quota(db, user_id="user-pro")  # 20 < 25


@pytest.mark.asyncio
async def test_check_project_quota_team_never_raises():
    """TEAM tier has unlimited projects — should never raise."""
    db = _mock_db(scalar_return=9_999, tier=SubscriptionTier.TEAM.value)
    await check_project_quota(db, user_id="user-team")


@pytest.mark.asyncio
async def test_check_project_quota_missing_subscription_defaults_to_free():
    """If no subscription row exists, default to FREE limits."""
    db = _mock_db(scalar_return=3, tier=None)  # scalar_one_or_none → None

    # Patch _get_tier directly to return FREE when subscription is None
    tier_result = MagicMock()
    tier_result.scalar_one_or_none.return_value = None
    count_result = MagicMock()
    count_result.scalar_one.return_value = 3
    db.execute.side_effect = [tier_result, count_result]

    with pytest.raises(QuotaExceededError) as exc_info:
        await check_project_quota(db, user_id="no-sub-user")
    assert exc_info.value.tier == SubscriptionTier.FREE.value


# ── check_session_quota ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_check_session_quota_under_limit():
    db = _mock_db(scalar_return=5, tier=SubscriptionTier.FREE.value)
    await check_session_quota(db, user_id="user-1", project_id="proj-a")


@pytest.mark.asyncio
async def test_check_session_quota_at_limit_raises():
    db = _mock_db(scalar_return=10, tier=SubscriptionTier.FREE.value)
    with pytest.raises(QuotaExceededError) as exc_info:
        await check_session_quota(db, user_id="user-1", project_id="proj-a")

    err = exc_info.value
    assert err.limit == 10
    assert err.current == 10


@pytest.mark.asyncio
async def test_check_session_quota_pro_higher_limit():
    db = _mock_db(scalar_return=10, tier=SubscriptionTier.PRO.value)
    # 10 < 100 (pro limit) — should pass
    await check_session_quota(db, user_id="user-pro", project_id="proj-b")


@pytest.mark.asyncio
async def test_check_session_quota_team_never_raises():
    db = _mock_db(scalar_return=9_999, tier=SubscriptionTier.TEAM.value)
    await check_session_quota(db, user_id="user-team", project_id="proj-c")


# ── check_block_quota ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_check_block_quota_under_limit():
    db = _mock_db(scalar_return=100, tier=SubscriptionTier.FREE.value)
    await check_block_quota(db, user_id="user-1", session_id="sess-x")


@pytest.mark.asyncio
async def test_check_block_quota_at_limit_raises():
    db = _mock_db(scalar_return=500, tier=SubscriptionTier.FREE.value)
    with pytest.raises(QuotaExceededError) as exc_info:
        await check_block_quota(db, user_id="user-1", session_id="sess-x")
    assert exc_info.value.limit == 500


@pytest.mark.asyncio
async def test_check_block_quota_pro_limit():
    db = _mock_db(scalar_return=4_999, tier=SubscriptionTier.PRO.value)
    await check_block_quota(db, user_id="user-pro", session_id="sess-y")

    db2 = _mock_db(scalar_return=5_000, tier=SubscriptionTier.PRO.value)
    with pytest.raises(QuotaExceededError):
        await check_block_quota(db2, user_id="user-pro", session_id="sess-y")


@pytest.mark.asyncio
async def test_check_block_quota_team_never_raises():
    db = _mock_db(scalar_return=999_999, tier=SubscriptionTier.TEAM.value)
    await check_block_quota(db, user_id="user-team", session_id="sess-z")


# ── QuotaExceededError attributes ─────────────────────────────────────────────


def test_quota_exceeded_error_attributes():
    err = QuotaExceededError("over limit", tier="free", limit=3, current=4)
    assert err.tier == "free"
    assert err.limit == 3
    assert err.current == 4
    assert str(err) == "over limit"


# ── get_usage_summary ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_usage_summary_free_tier():
    db = _mock_db_multi(SubscriptionTier.FREE.value, 2, 7)
    summary = await get_usage_summary(db, user_id="user-1")

    assert summary["tier"] == SubscriptionTier.FREE.value
    assert summary["limits"]["max_projects"] == 3
    assert summary["limits"]["max_sessions_per_project"] == 10
    assert summary["limits"]["max_blocks_per_session"] == 500
    assert summary["usage"]["projects"] == 2
    assert summary["usage"]["total_sessions"] == 7


@pytest.mark.asyncio
async def test_get_usage_summary_team_tier_has_none_limits():
    db = _mock_db_multi(SubscriptionTier.TEAM.value, 50, 300)
    summary = await get_usage_summary(db, user_id="user-team")

    assert summary["tier"] == SubscriptionTier.TEAM.value
    # Unlimited tiers return None instead of a number
    assert summary["limits"]["max_projects"] is None
    assert summary["limits"]["max_sessions_per_project"] is None
    assert summary["limits"]["max_blocks_per_session"] is None
    assert summary["usage"]["projects"] == 50
    assert summary["usage"]["total_sessions"] == 300
