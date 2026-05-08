"""Password and API key hashing utilities."""

from __future__ import annotations

import hashlib
import secrets

import bcrypt


# ── Password Hashing ───────────────────────────────────────────

def hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt."""
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


# ── API Key Hashing ────────────────────────────────────────────

# API keys are long random strings, so we use SHA-256 first (fast, deterministic)
# then store the SHA-256 hex digest. This lets us look up keys by hash quickly
# without the cost of bcrypt for every request.
# For passwords, bcrypt is essential because passwords are short and guessable.
# For API keys (64 chars of entropy), SHA-256 is sufficient.

def hash_api_key(raw_key: str) -> str:
    """Hash a raw API key with SHA-256 for fast lookup.

    API keys have high entropy (32+ random chars), so SHA-256 is sufficient.
    Unlike passwords, API keys don't need bcrypt's slow-hash protection.
    """
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def generate_api_key() -> tuple[str, str]:
    """Generate a new API key.

    Returns:
        A tuple of (raw_key, prefix) where:
        - raw_key: the full key to give to the user (shown once)
        - prefix: the first 12 chars for identification
    """
    # 32 random bytes → 64 hex chars of entropy
    random_part = secrets.token_hex(32)
    raw_key = f"dm_key_{random_part}"
    prefix = raw_key[:12]  # "dm_key_a1b2c3"
    return raw_key, prefix
