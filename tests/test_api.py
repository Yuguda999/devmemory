"""Integration tests for the REST API.

Tests the full HTTP flow: register → login → API key management.
Uses FastAPI's TestClient with httpx for async-compatible testing.
"""

from __future__ import annotations

import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Force test-mode settings before importing anything else
os.environ["DEVMEMORY_DATABASE_URL"] = "sqlite+aiosqlite://"
os.environ["DEVMEMORY_SECRET_KEY"] = "test-secret-key-for-jwt-testing-32bytes"
os.environ["DEVMEMORY_DEPLOYMENT_MODE"] = "saas"


@pytest_asyncio.fixture(autouse=True)
async def _reset_and_init_db():
    """Reset the global DB engine and create tables for each test."""
    from devmemory.db import engine as engine_mod
    from devmemory.db.engine import close_db, init_db

    # Reset engine globals so each test gets a fresh in-memory DB
    if engine_mod._engine is not None:
        await engine_mod._engine.dispose()
    engine_mod._engine = None
    engine_mod._session_factory = None

    # Create tables in the fresh in-memory database
    await init_db()

    yield

    # Cleanup after test
    await close_db()


@pytest.fixture
def app():
    """Create a fresh FastAPI app for each test."""
    from devmemory.api.app import create_app

    return create_app()


@pytest_asyncio.fixture
async def client(app):
    """Async HTTP test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ── Health Check ───────────────────────────────────────────────


class TestHealthCheck:
    """Tests for the /health endpoint."""

    async def test_health_check(self, client: AsyncClient) -> None:
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data


# ── Registration ───────────────────────────────────────────────


class TestRegistration:
    """Tests for POST /auth/register."""

    async def test_register_success(self, client: AsyncClient) -> None:
        resp = await client.post("/auth/register", json={
            "email": "newuser@test.com",
            "password": "securepassword123",
            "display_name": "New User",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["email"] == "newuser@test.com"
        assert data["display_name"] == "New User"
        assert data["tier"] == "free"
        assert "id" in data
        assert "created_at" in data

    async def test_register_duplicate_email(self, client: AsyncClient) -> None:
        """Second registration with the same email should fail."""
        payload = {
            "email": "dupe@test.com",
            "password": "securepassword123",
            "display_name": "First User",
        }
        resp1 = await client.post("/auth/register", json=payload)
        assert resp1.status_code == 201

        resp2 = await client.post("/auth/register", json=payload)
        assert resp2.status_code == 409
        assert "already exists" in resp2.json()["detail"]

    async def test_register_normalizes_email(self, client: AsyncClient) -> None:
        resp = await client.post("/auth/register", json={
            "email": "upper@test.com",
            "password": "securepassword123",
            "display_name": "Upper",
        })
        assert resp.status_code == 201
        assert resp.json()["email"] == "upper@test.com"

    async def test_register_short_password(self, client: AsyncClient) -> None:
        resp = await client.post("/auth/register", json={
            "email": "short@test.com",
            "password": "short",
            "display_name": "User",
        })
        assert resp.status_code == 422  # validation error

    async def test_register_invalid_email(self, client: AsyncClient) -> None:
        resp = await client.post("/auth/register", json={
            "email": "not-an-email",
            "password": "securepassword123",
            "display_name": "User",
        })
        assert resp.status_code == 422

    async def test_register_empty_display_name(self, client: AsyncClient) -> None:
        resp = await client.post("/auth/register", json={
            "email": "empty@test.com",
            "password": "securepassword123",
            "display_name": "",
        })
        assert resp.status_code == 422


# ── Login ──────────────────────────────────────────────────────


class TestLogin:
    """Tests for POST /auth/login."""

    async def test_login_success(self, client: AsyncClient) -> None:
        # Register first
        await client.post("/auth/register", json={
            "email": "loginuser@test.com",
            "password": "securepassword123",
            "display_name": "Login User",
        })

        # Login
        resp = await client.post("/auth/login", json={
            "email": "loginuser@test.com",
            "password": "securepassword123",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["email"] == "loginuser@test.com"
        assert "user_id" in data

    async def test_login_wrong_password(self, client: AsyncClient) -> None:
        await client.post("/auth/register", json={
            "email": "wrongpw@test.com",
            "password": "securepassword123",
            "display_name": "User",
        })

        resp = await client.post("/auth/login", json={
            "email": "wrongpw@test.com",
            "password": "wrongpassword",
        })
        assert resp.status_code == 401
        assert "Invalid email or password" in resp.json()["detail"]

    async def test_login_nonexistent_user(self, client: AsyncClient) -> None:
        resp = await client.post("/auth/login", json={
            "email": "noone@test.com",
            "password": "doesntmatter",
        })
        assert resp.status_code == 401

    async def test_login_normalizes_email(self, client: AsyncClient) -> None:
        await client.post("/auth/register", json={
            "email": "normalized@test.com",
            "password": "securepassword123",
            "display_name": "User",
        })

        resp = await client.post("/auth/login", json={
            "email": "normalized@test.com",
            "password": "securepassword123",
        })
        assert resp.status_code == 200


# ── API Keys ──────────────────────────────────────────────────


class TestApiKeys:
    """Tests for API key management endpoints."""

    async def _register_and_login(self, client: AsyncClient, email: str = "keys@test.com"):
        """Helper: register + login + return auth header."""
        await client.post("/auth/register", json={
            "email": email,
            "password": "securepassword123",
            "display_name": "Key User",
        })
        resp = await client.post("/auth/login", json={
            "email": email,
            "password": "securepassword123",
        })
        token = resp.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    async def test_create_api_key(self, client: AsyncClient) -> None:
        headers = await self._register_and_login(client, "create-key@test.com")

        resp = await client.post(
            "/auth/api-keys",
            json={"name": "cursor-home"},
            headers=headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "cursor-home"
        assert data["key"].startswith("dm_key_")
        assert data["prefix"] == data["key"][:12]
        assert "id" in data
        assert "created_at" in data

    async def test_list_api_keys(self, client: AsyncClient) -> None:
        headers = await self._register_and_login(client, "list-keys@test.com")

        # Create two keys
        await client.post("/auth/api-keys", json={"name": "key-one"}, headers=headers)
        await client.post("/auth/api-keys", json={"name": "key-two"}, headers=headers)

        resp = await client.get("/auth/api-keys", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2
        assert len(data["keys"]) == 2
        names = {k["name"] for k in data["keys"]}
        assert names == {"key-one", "key-two"}

    async def test_revoke_api_key(self, client: AsyncClient) -> None:
        headers = await self._register_and_login(client, "revoke-key@test.com")

        # Create a key
        create_resp = await client.post(
            "/auth/api-keys",
            json={"name": "to-revoke"},
            headers=headers,
        )
        key_id = create_resp.json()["id"]

        # Revoke it
        resp = await client.delete(f"/auth/api-keys/{key_id}", headers=headers)
        assert resp.status_code == 200
        assert "revoked" in resp.json()["message"].lower()

        # List should now be empty (only non-revoked shown)
        list_resp = await client.get("/auth/api-keys", headers=headers)
        assert list_resp.json()["count"] == 0

    async def test_revoke_nonexistent_key(self, client: AsyncClient) -> None:
        headers = await self._register_and_login(client, "nokey@test.com")

        resp = await client.delete("/auth/api-keys/nonexistent-id", headers=headers)
        assert resp.status_code == 404

    async def test_create_key_without_auth(self, client: AsyncClient) -> None:
        resp = await client.post("/auth/api-keys", json={"name": "no-auth"})
        assert resp.status_code == 401

    async def test_list_keys_without_auth(self, client: AsyncClient) -> None:
        resp = await client.get("/auth/api-keys")
        assert resp.status_code == 401

    async def test_api_key_name_validation(self, client: AsyncClient) -> None:
        headers = await self._register_and_login(client, "badname@test.com")

        # Empty name should fail
        resp = await client.post(
            "/auth/api-keys",
            json={"name": ""},
            headers=headers,
        )
        assert resp.status_code == 422


# ── Full Flow ─────────────────────────────────────────────────


class TestFullFlow:
    """End-to-end test: register → login → create key → list keys → revoke."""

    async def test_complete_auth_flow(self, client: AsyncClient) -> None:
        # 1. Register
        reg = await client.post("/auth/register", json={
            "email": "flow@test.com",
            "password": "securepassword123",
            "display_name": "Flow User",
        })
        assert reg.status_code == 201
        user_id = reg.json()["id"]

        # 2. Login
        login = await client.post("/auth/login", json={
            "email": "flow@test.com",
            "password": "securepassword123",
        })
        assert login.status_code == 200
        token = login.json()["access_token"]
        assert login.json()["user_id"] == user_id
        headers = {"Authorization": f"Bearer {token}"}

        # 3. Create API key
        key = await client.post(
            "/auth/api-keys",
            json={"name": "my-cursor"},
            headers=headers,
        )
        assert key.status_code == 201
        raw_key = key.json()["key"]
        key_id = key.json()["id"]
        assert raw_key.startswith("dm_key_")

        # 4. List keys
        keys = await client.get("/auth/api-keys", headers=headers)
        assert keys.status_code == 200
        assert keys.json()["count"] == 1
        assert keys.json()["keys"][0]["name"] == "my-cursor"
        # Raw key should NOT be in the list response
        assert "key" not in keys.json()["keys"][0]

        # 5. Revoke key
        rev = await client.delete(f"/auth/api-keys/{key_id}", headers=headers)
        assert rev.status_code == 200

        # 6. Verify key is gone
        keys2 = await client.get("/auth/api-keys", headers=headers)
        assert keys2.json()["count"] == 0
