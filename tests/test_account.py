"""Tests for account features: password/profile/email updates, notification
preferences, and email verification / password-reset tokens."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from devmemory.auth.hashing import verify_password
from devmemory.db.repository import (
    consume_email_token,
    create_email_token,
    create_user,
    get_valid_email_token,
    invalidate_email_tokens,
    mark_email_verified,
    set_notification_prefs,
    update_user_password,
    update_user_profile,
)
from devmemory.models import EmailTokenPurpose
from devmemory.models.user import DEFAULT_NOTIFICATION_PREFS


@pytest.fixture
async def user(db_session: AsyncSession):
    return await create_user(db_session, "alice@test.com", "password123", "Alice")


# ── User field updates ─────────────────────────────────────────


async def test_create_user_unverified_by_default(db_session: AsyncSession):
    u = await create_user(db_session, "new@test.com", "password123", "New")
    assert u.email_verified is False


async def test_create_user_can_be_prefverified(db_session: AsyncSession):
    u = await create_user(db_session, "v@test.com", "password123", "V", email_verified=True)
    assert u.email_verified is True


async def test_update_password(db_session: AsyncSession, user):
    old_hash = user.password_hash
    updated = await update_user_password(db_session, user.id, "brand-new-pass")
    assert updated is not None
    assert updated.password_hash != old_hash
    assert verify_password("brand-new-pass", updated.password_hash)
    assert not verify_password("password123", updated.password_hash)


async def test_update_profile(db_session: AsyncSession, user):
    updated = await update_user_profile(db_session, user.id, "  Alice Cooper  ")
    assert updated.display_name == "Alice Cooper"


async def test_mark_email_verified(db_session: AsyncSession, user):
    assert user.email_verified is False
    updated = await mark_email_verified(db_session, user.id)
    assert updated.email_verified is True


# ── Notification preferences ───────────────────────────────────


async def test_notification_prefs_default(db_session: AsyncSession, user):
    assert user.notification_prefs == DEFAULT_NOTIFICATION_PREFS


async def test_set_notification_prefs_partial_merge(db_session: AsyncSession, user):
    updated = await set_notification_prefs(db_session, user.id, {"security_alerts": False})
    assert updated.notification_prefs["security_alerts"] is False
    # account_events untouched → keeps default
    assert updated.notification_prefs["account_events"] is True


async def test_notification_prefs_ignores_unknown_keys(db_session: AsyncSession, user):
    updated = await set_notification_prefs(db_session, user.id, {"bogus": True})
    assert "bogus" not in updated.notification_prefs
    assert updated.notification_prefs == DEFAULT_NOTIFICATION_PREFS


# ── Email tokens ───────────────────────────────────────────────


def _future(hours: int = 1) -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=hours)


def _past() -> datetime:
    return datetime.now(timezone.utc) - timedelta(hours=1)


async def test_create_and_get_token(db_session: AsyncSession, user):
    raw = await create_email_token(
        db_session, user.id, EmailTokenPurpose.VERIFY_EMAIL.value, _future()
    )
    assert isinstance(raw, str) and len(raw) > 20
    token = await get_valid_email_token(db_session, raw, EmailTokenPurpose.VERIFY_EMAIL.value)
    assert token is not None
    assert token.user_id == user.id


async def test_token_wrong_purpose_not_found(db_session: AsyncSession, user):
    raw = await create_email_token(
        db_session, user.id, EmailTokenPurpose.VERIFY_EMAIL.value, _future()
    )
    # Looking it up as a reset token must fail.
    assert await get_valid_email_token(
        db_session, raw, EmailTokenPurpose.RESET_PASSWORD.value
    ) is None


async def test_expired_token_invalid(db_session: AsyncSession, user):
    raw = await create_email_token(
        db_session, user.id, EmailTokenPurpose.RESET_PASSWORD.value, _past()
    )
    assert await get_valid_email_token(
        db_session, raw, EmailTokenPurpose.RESET_PASSWORD.value
    ) is None


async def test_consumed_token_cannot_be_reused(db_session: AsyncSession, user):
    raw = await create_email_token(
        db_session, user.id, EmailTokenPurpose.RESET_PASSWORD.value, _future()
    )
    token = await get_valid_email_token(db_session, raw, EmailTokenPurpose.RESET_PASSWORD.value)
    await consume_email_token(db_session, token)
    assert await get_valid_email_token(
        db_session, raw, EmailTokenPurpose.RESET_PASSWORD.value
    ) is None


async def test_creating_new_token_invalidates_old(db_session: AsyncSession, user):
    raw1 = await create_email_token(
        db_session, user.id, EmailTokenPurpose.VERIFY_EMAIL.value, _future()
    )
    raw2 = await create_email_token(
        db_session, user.id, EmailTokenPurpose.VERIFY_EMAIL.value, _future()
    )
    # Old link dies; only the newest works.
    assert await get_valid_email_token(
        db_session, raw1, EmailTokenPurpose.VERIFY_EMAIL.value
    ) is None
    assert await get_valid_email_token(
        db_session, raw2, EmailTokenPurpose.VERIFY_EMAIL.value
    ) is not None


async def test_invalidate_email_tokens(db_session: AsyncSession, user):
    raw = await create_email_token(
        db_session, user.id, EmailTokenPurpose.RESET_PASSWORD.value, _future()
    )
    await invalidate_email_tokens(db_session, user.id, EmailTokenPurpose.RESET_PASSWORD.value)
    assert await get_valid_email_token(
        db_session, raw, EmailTokenPurpose.RESET_PASSWORD.value
    ) is None


