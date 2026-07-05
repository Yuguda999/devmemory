"""FastAPI authentication dependencies.

Provides two dependency injectors:
1. ``require_jwt_user`` — for REST API routes (browser/client login flow)
2. ``require_api_key_user`` — for MCP tool routes (API key in header)
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from devmemory.auth.jwt_utils import TokenError, decode_access_token
from devmemory.db.engine import get_db_session
from devmemory.db.repository import (
    get_api_key_by_hash,
    get_user_with_subscription,
    touch_api_key,
)
from devmemory.models import SubscriptionTier

# ── Authenticated Context ──────────────────────────────────────


@dataclass(frozen=True)
class AuthContext:
    """Container for authenticated user info, injected into route handlers."""

    user_id: str
    email: str
    tier: SubscriptionTier
    api_key_id: str | None = None  # set when authenticated via API key


# ── JWT Bearer Dependency (REST API) ──────────────────────────

_bearer_scheme = HTTPBearer(auto_error=False)


async def require_jwt_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> AuthContext:
    """Validate a JWT bearer token and return the authenticated user context.

    Usage::

        @router.get("/me")
        async def get_me(auth: AuthContext = Depends(require_jwt_user)):
            ...
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_access_token(credentials.credentials)
    except TokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        ) from e

    user_id = payload["sub"]

    # Verify user still exists, is active, and resolve tier
    async with get_db_session() as session:
        user = await get_user_with_subscription(session, user_id)

        if user is None or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or deactivated",
            )

        # Resolve tier while still in session (subscription is eager-loaded)
        tier = _resolve_tier(user)

    return AuthContext(
        user_id=user_id,
        email=payload["email"],
        tier=tier,
    )


# ── API Key Dependency (MCP / programmatic access) ────────────


async def require_api_key_user(
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    authorization: str | None = Header(None),
) -> AuthContext:
    """Validate an API key and return the authenticated user context.

    Accepts the key in either:
    - ``X-API-Key: dm_key_...`` header
    - ``Authorization: Bearer dm_key_...`` header (for MCP clients)

    Usage::

        @router.get("/data")
        async def get_data(auth: AuthContext = Depends(require_api_key_user)):
            ...
    """
    raw_key = _extract_api_key(x_api_key, authorization)

    if raw_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Missing API key. Provide via X-API-Key header or Authorization: Bearer dm_key_..."
            ),
        )

    if not raw_key.startswith("dm_key_"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key format. Keys must start with 'dm_key_'",
        )

    async with get_db_session() as session:
        api_key = await get_api_key_by_hash(session, raw_key)

        if api_key is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or revoked API key",
            )

        # Touch last_used_at
        await touch_api_key(session, api_key.id)

        # Load the user with subscription eagerly loaded
        user = await get_user_with_subscription(session, api_key.user_id)

        if user is None or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User associated with this API key is deactivated",
            )

        # Resolve tier while still in session
        tier = _resolve_tier(user)

        return AuthContext(
            user_id=user.id,
            email=user.email,
            tier=tier,
            api_key_id=api_key.id,
        )


# ── Combined Dependency (dashboard JWT *or* MCP/client API key) ───


async def require_user(
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    authorization: str | None = Header(None),
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> AuthContext:
    """Authenticate via an API key **or** a JWT, so one endpoint serves both
    the browser dashboard (JWT) and the MCP client / programmatic callers
    (``X-API-Key`` or ``Authorization: Bearer dm_key_...``).

    API-key auth wins when a key is present in either header; otherwise the
    request is treated as a JWT bearer login.

    Usage::

        @router.post("/context")
        async def save(auth: AuthContext = Depends(require_user)):
            ...
    """
    api_key_present = bool(x_api_key) or bool(authorization and "dm_key_" in authorization)
    if api_key_present:
        return await require_api_key_user(x_api_key=x_api_key, authorization=authorization)
    return await require_jwt_user(credentials=credentials)


# ── Helpers ────────────────────────────────────────────────────


def _extract_api_key(
    x_api_key: str | None,
    authorization: str | None,
) -> str | None:
    """Extract the raw API key from headers."""
    if x_api_key:
        return x_api_key.strip()

    if authorization:
        parts = authorization.split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "bearer" and parts[1].startswith("dm_key_"):
            return parts[1].strip()

    return None


def _resolve_tier(user: object) -> SubscriptionTier:
    """Resolve the user's subscription tier, defaulting to FREE.

    Args:
        user: A User model instance with subscription eagerly loaded.
    """
    from devmemory.config import settings

    # Self-hosted mode: everyone is effectively unlimited (treat as TEAM)
    if settings.is_self_hosted:
        return SubscriptionTier.TEAM

    # Check if subscription relationship is loaded
    subscription = getattr(user, "subscription", None)
    if subscription is not None:
        try:
            return SubscriptionTier(subscription.tier)
        except ValueError:
            return SubscriptionTier.FREE

    return SubscriptionTier.FREE
