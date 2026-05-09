"""Tests for auth middleware dependencies."""

from __future__ import annotations

import pytest

from devmemory.auth.middleware import AuthContext, _extract_api_key


class TestExtractApiKey:
    """Tests for the _extract_api_key helper."""

    def test_from_x_api_key_header(self) -> None:
        result = _extract_api_key(x_api_key="dm_key_abc123", authorization=None)
        assert result == "dm_key_abc123"

    def test_from_authorization_bearer(self) -> None:
        result = _extract_api_key(
            x_api_key=None,
            authorization="Bearer dm_key_abc123",
        )
        assert result == "dm_key_abc123"

    def test_x_api_key_takes_priority(self) -> None:
        result = _extract_api_key(
            x_api_key="dm_key_primary",
            authorization="Bearer dm_key_fallback",
        )
        assert result == "dm_key_primary"

    def test_returns_none_when_no_headers(self) -> None:
        result = _extract_api_key(x_api_key=None, authorization=None)
        assert result is None

    def test_ignores_non_dm_key_bearer(self) -> None:
        """A bearer token that doesn't start with dm_key_ is not an API key."""
        result = _extract_api_key(
            x_api_key=None,
            authorization="Bearer some_jwt_token_here",
        )
        assert result is None

    def test_strips_whitespace(self) -> None:
        result = _extract_api_key(x_api_key="  dm_key_abc123  ", authorization=None)
        assert result == "dm_key_abc123"

    def test_case_insensitive_bearer(self) -> None:
        result = _extract_api_key(
            x_api_key=None,
            authorization="bearer dm_key_abc123",
        )
        assert result == "dm_key_abc123"


class TestAuthContext:
    """Tests for the AuthContext dataclass."""

    def test_create_auth_context(self) -> None:
        from devmemory.models import SubscriptionTier

        ctx = AuthContext(
            user_id="user-123",
            email="test@test.com",
            tier=SubscriptionTier.FREE,
        )
        assert ctx.user_id == "user-123"
        assert ctx.email == "test@test.com"
        assert ctx.tier == SubscriptionTier.FREE
        assert ctx.api_key_id is None

    def test_auth_context_with_api_key(self) -> None:
        from devmemory.models import SubscriptionTier

        ctx = AuthContext(
            user_id="user-123",
            email="test@test.com",
            tier=SubscriptionTier.PRO,
            api_key_id="key-456",
        )
        assert ctx.api_key_id == "key-456"
        assert ctx.tier == SubscriptionTier.PRO

    def test_auth_context_is_frozen(self) -> None:
        from devmemory.models import SubscriptionTier

        ctx = AuthContext(
            user_id="user-123",
            email="test@test.com",
            tier=SubscriptionTier.FREE,
        )
        with pytest.raises(AttributeError):
            ctx.user_id = "new-id"  # type: ignore[misc]
