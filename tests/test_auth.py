"""Tests for auth utilities — hashing, API keys, and JWT tokens."""

from __future__ import annotations

import pytest

from devmemory.auth import (
    TokenError,
    create_access_token,
    decode_access_token,
    generate_api_key,
    hash_api_key,
    hash_password,
    verify_password,
)


class TestPasswordHashing:
    """Tests for bcrypt password hashing."""

    def test_hash_password_returns_string(self):
        hashed = hash_password("my_password")
        assert isinstance(hashed, str)
        assert len(hashed) > 20

    def test_hash_is_not_plaintext(self):
        hashed = hash_password("secret123")
        assert hashed != "secret123"

    def test_verify_correct_password(self):
        hashed = hash_password("correct_password")
        assert verify_password("correct_password", hashed) is True

    def test_verify_wrong_password(self):
        hashed = hash_password("correct_password")
        assert verify_password("wrong_password", hashed) is False

    def test_different_hashes_for_same_password(self):
        """bcrypt salts should produce different hashes."""
        h1 = hash_password("same_password")
        h2 = hash_password("same_password")
        assert h1 != h2  # Different salts
        assert verify_password("same_password", h1) is True
        assert verify_password("same_password", h2) is True


class TestApiKeyGeneration:
    """Tests for API key generation and hashing."""

    def test_generate_api_key_format(self):
        raw_key, prefix = generate_api_key()
        assert raw_key.startswith("dm_key_")
        assert prefix == raw_key[:12]
        assert len(raw_key) == 71  # "dm_key_" (7) + 64 hex chars

    def test_generate_unique_keys(self):
        key1, _ = generate_api_key()
        key2, _ = generate_api_key()
        assert key1 != key2

    def test_hash_api_key_deterministic(self):
        raw_key, _ = generate_api_key()
        h1 = hash_api_key(raw_key)
        h2 = hash_api_key(raw_key)
        assert h1 == h2  # SHA-256 is deterministic

    def test_hash_api_key_different_keys(self):
        key1, _ = generate_api_key()
        key2, _ = generate_api_key()
        assert hash_api_key(key1) != hash_api_key(key2)


class TestJWTTokens:
    """Tests for JWT token creation and verification."""

    def test_create_and_decode_token(self):
        token = create_access_token("user-123", "test@example.com")
        payload = decode_access_token(token)
        assert payload["sub"] == "user-123"
        assert payload["email"] == "test@example.com"
        assert payload["type"] == "access"

    def test_decode_invalid_token(self):
        with pytest.raises(TokenError, match="Invalid token"):
            decode_access_token("not.a.valid.token")

    def test_decode_tampered_token(self):
        token = create_access_token("user-123", "test@example.com")
        # Tamper with the token
        tampered = token[:-5] + "XXXXX"
        with pytest.raises(TokenError):
            decode_access_token(tampered)


class TestRepositoryAuth:
    """Tests for auth-related repository operations."""

    async def test_create_user_with_subscription(self, db_session):
        from devmemory.db.repository import create_user, get_user_by_email

        user = await create_user(
            db_session,
            email="repo@test.com",
            password="password123",
            display_name="Repo User",
        )

        assert user.id is not None
        assert user.email == "repo@test.com"
        # Password should be hashed, not plaintext
        assert user.password_hash != "password123"
        assert verify_password("password123", user.password_hash) is True

        # Should be findable by email
        found = await get_user_by_email(db_session, "repo@test.com")
        assert found is not None
        assert found.id == user.id

    async def test_create_user_normalizes_email(self, db_session):
        from devmemory.db.repository import create_user

        user = await create_user(
            db_session,
            email="  UPPER@Test.COM  ",
            password="pass",
            display_name="Normalized",
        )
        assert user.email == "upper@test.com"

    async def test_api_key_crud(self, db_session):
        from devmemory.auth.hashing import generate_api_key as gen_key
        from devmemory.db.repository import (
            create_api_key_record,
            create_user,
            get_api_key_by_hash,
            list_api_keys,
            revoke_api_key,
        )

        user = await create_user(db_session, "apikey@repo.com", "pass", "Key User")
        raw_key, prefix = gen_key()

        # Create
        key_record = await create_api_key_record(db_session, user.id, raw_key, prefix, "test-key")
        assert key_record.name == "test-key"
        assert key_record.prefix == prefix

        # Lookup by raw key
        found = await get_api_key_by_hash(db_session, raw_key)
        assert found is not None
        assert found.id == key_record.id

        # List keys
        keys = await list_api_keys(db_session, user.id)
        assert len(keys) >= 1

        # Revoke
        success = await revoke_api_key(db_session, key_record.id, user.id)
        assert success is True

        # Revoked key should not be found
        found_after = await get_api_key_by_hash(db_session, raw_key)
        assert found_after is None

    async def test_get_or_create_project(self, db_session):
        from devmemory.db.repository import create_user, get_or_create_project

        user = await create_user(db_session, "proj@repo.com", "pass", "Proj User")

        # First call creates
        project, created = await get_or_create_project(
            db_session,
            user.id,
            slug="yuguda999-devmemory",
            name="DevMemory",
            remote_url="git@github.com:Yuguda999/devmemory.git",
        )
        assert created is True
        assert project.slug == "yuguda999-devmemory"

        # Second call returns existing
        project2, created2 = await get_or_create_project(
            db_session,
            user.id,
            slug="yuguda999-devmemory",
        )
        assert created2 is False
        assert project2.id == project.id
