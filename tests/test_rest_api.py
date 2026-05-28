"""Unit tests for Phase 4 REST API routes.

Uses FastAPI TestClient with mocked DB and auth dependencies so no real
database is required.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from devmemory.api.app import create_app
from devmemory.auth.middleware import AuthContext, require_jwt_user
from devmemory.models.subscription import SubscriptionTier


# ── Fixtures ───────────────────────────────────────────────────────────────────


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class _Project:
    id: str = "proj-1"
    slug: str = "user-myproject"
    name: str = "myproject"
    remote_url: str | None = "https://github.com/user/myproject"
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)


@dataclass
class _Session:
    id: str = "sess-1"
    project_id: str = "proj-1"
    title: str = "Test session"
    status: str = "active"
    tool_source: str = "claude"
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)
    context_blocks: list = field(default_factory=list)
    project: Any = field(default_factory=_Project)


@dataclass
class _Block:
    id: str = "block-1"
    session_id: str = "sess-1"
    block_type: str = "goal"
    content: str = "Implement the API layer"
    priority: int = 5
    meta_json: str | None = None
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)


_FAKE_AUTH = AuthContext(
    user_id="user-uuid",
    email="dev@example.com",
    tier=SubscriptionTier.FREE,
)

_USAGE_SUMMARY = {
    "tier": "free",
    "limits": {"max_projects": 3, "max_sessions_per_project": 10, "max_blocks_per_session": 500},
    "usage": {"projects": 1, "total_sessions": 2},
}


@pytest.fixture()
def client():
    """Return a TestClient with JWT auth dependency overridden."""
    app = create_app()
    app.dependency_overrides[require_jwt_user] = lambda: _FAKE_AUTH
    return TestClient(app, raise_server_exceptions=True)


# ── /projects ──────────────────────────────────────────────────────────────────


class TestProjectRoutes:
    def test_list_projects_returns_200(self, client):
        projects = [_Project(id="p1", slug="a", name="A"), _Project(id="p2", slug="b", name="B")]

        with patch(
            "devmemory.api.project_routes.list_projects",
            AsyncMock(return_value=projects),
        ):
            response = client.get("/projects")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2
        assert data["projects"][0]["slug"] == "a"
        assert data["projects"][1]["id"] == "p2"

    def test_list_projects_empty(self, client):
        with patch(
            "devmemory.api.project_routes.list_projects",
            AsyncMock(return_value=[]),
        ):
            response = client.get("/projects")

        assert response.status_code == 200
        assert response.json() == {"projects": [], "count": 0}


# ── /sessions ──────────────────────────────────────────────────────────────────


class TestSessionRoutes:
    def test_list_sessions_returns_200(self, client):
        sessions = [_Session(id="s1"), _Session(id="s2", title="Other")]

        with patch(
            "devmemory.api.session_routes.list_sessions",
            AsyncMock(return_value=sessions),
        ):
            response = client.get("/sessions")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2
        assert data["sessions"][0]["id"] == "s1"

    def test_list_sessions_filter_by_project(self, client):
        with patch(
            "devmemory.api.session_routes.list_sessions",
            AsyncMock(return_value=[_Session()]),
        ) as mock_list:
            response = client.get("/sessions?project_id=proj-1&status=active")

        assert response.status_code == 200
        call_kwargs = mock_list.call_args.kwargs
        assert call_kwargs["project_id"] == "proj-1"
        assert call_kwargs["status"] == "active"

    def test_list_sessions_invalid_status_returns_422(self, client):
        response = client.get("/sessions?status=invalid_status")
        assert response.status_code == 422

    def test_get_session_returns_200(self, client):
        with patch(
            "devmemory.api.session_routes.get_session",
            AsyncMock(return_value=_Session()),
        ):
            response = client.get("/sessions/sess-1")

        assert response.status_code == 200
        assert response.json()["id"] == "sess-1"
        assert response.json()["title"] == "Test session"

    def test_get_session_not_found_returns_404(self, client):
        with patch(
            "devmemory.api.session_routes.get_session",
            AsyncMock(return_value=None),
        ):
            response = client.get("/sessions/ghost-id")

        assert response.status_code == 404

    def test_patch_session_title(self, client):
        updated = _Session(title="Renamed session")

        with patch(
            "devmemory.api.session_routes.update_session",
            AsyncMock(return_value=updated),
        ):
            response = client.patch(
                "/sessions/sess-1",
                json={"title": "Renamed session"},
            )

        assert response.status_code == 200
        assert response.json()["title"] == "Renamed session"

    def test_patch_session_status(self, client):
        updated = _Session(status="completed")

        with patch(
            "devmemory.api.session_routes.update_session",
            AsyncMock(return_value=updated),
        ):
            response = client.patch(
                "/sessions/sess-1",
                json={"status": "completed"},
            )

        assert response.status_code == 200
        assert response.json()["status"] == "completed"

    def test_patch_session_invalid_status_returns_422(self, client):
        response = client.patch("/sessions/sess-1", json={"status": "deleted"})
        assert response.status_code == 422

    def test_patch_session_no_fields_returns_422(self, client):
        response = client.patch("/sessions/sess-1", json={})
        assert response.status_code == 422

    def test_patch_session_not_found_returns_404(self, client):
        with patch(
            "devmemory.api.session_routes.update_session",
            AsyncMock(return_value=None),
        ):
            response = client.patch("/sessions/ghost", json={"title": "x"})

        assert response.status_code == 404


# ── /sessions/{id}/blocks ──────────────────────────────────────────────────────


class TestContextBlockRoutes:
    def test_list_blocks_returns_200(self, client):
        blocks = [_Block(), _Block(id="b2", block_type="next_step")]

        with patch(
            "devmemory.api.session_routes.get_context_blocks",
            AsyncMock(return_value=blocks),
        ):
            response = client.get("/sessions/sess-1/blocks")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2
        assert data["blocks"][0]["block_type"] == "goal"

    def test_list_blocks_session_not_found_returns_404(self, client):
        with patch(
            "devmemory.api.session_routes.get_context_blocks",
            AsyncMock(return_value=None),
        ):
            response = client.get("/sessions/ghost/blocks")

        assert response.status_code == 404

    def test_delete_block_returns_200(self, client):
        with patch(
            "devmemory.api.session_routes.delete_context_block",
            AsyncMock(return_value=True),
        ):
            response = client.delete("/context-blocks/block-1")

        assert response.status_code == 200
        assert "deleted" in response.json()["message"]

    def test_delete_block_not_found_returns_404(self, client):
        with patch(
            "devmemory.api.session_routes.delete_context_block",
            AsyncMock(return_value=False),
        ):
            response = client.delete("/context-blocks/ghost-block")

        assert response.status_code == 404


# ── /billing/status ────────────────────────────────────────────────────────────


class TestBillingRoutes:
    def test_billing_status_returns_200(self, client):
        with patch(
            "devmemory.api.billing_routes.get_usage_summary",
            AsyncMock(return_value=_USAGE_SUMMARY),
        ):
            response = client.get("/billing/status")

        assert response.status_code == 200
        data = response.json()
        assert data["tier"] == "free"
        assert data["limits"]["max_projects"] == 3
        assert data["usage"]["projects"] == 1
        assert data["usage"]["total_sessions"] == 2

    def test_billing_status_team_has_null_limits(self, client):
        team_summary = {
            "tier": "team",
            "limits": {
                "max_projects": None,
                "max_sessions_per_project": None,
                "max_blocks_per_session": None,
            },
            "usage": {"projects": 50, "total_sessions": 400},
        }

        with patch(
            "devmemory.api.billing_routes.get_usage_summary",
            AsyncMock(return_value=team_summary),
        ):
            response = client.get("/billing/status")

        assert response.status_code == 200
        data = response.json()
        assert data["tier"] == "team"
        assert data["limits"]["max_projects"] is None
