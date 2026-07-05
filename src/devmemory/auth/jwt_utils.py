"""JWT token creation and verification."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt

from devmemory.config import settings


class TokenError(Exception):
    """Raised when a JWT token is invalid or expired."""


def create_access_token(user_id: str, email: str) -> str:
    """Create a JWT access token for a user.

    Args:
        user_id: The user's UUID.
        email: The user's email.

    Returns:
        An encoded JWT string.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "email": email,
        "iat": now,
        "exp": now + timedelta(hours=settings.jwt_expiry_hours),
        "type": "access",
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    """Decode and verify a JWT access token.

    Args:
        token: The encoded JWT string.

    Returns:
        The decoded payload dict with keys: sub, email, iat, exp, type.

    Raises:
        TokenError: If the token is invalid or expired.
    """
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
        if payload.get("type") != "access":
            raise TokenError("Invalid token type")
        return payload
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("Token has expired") from exc
    except jwt.InvalidTokenError as e:
        raise TokenError(f"Invalid token: {e}") from e
