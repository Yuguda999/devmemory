"""Tests for the API-key/client REST endpoints that back the MCP client.

Follows the same style as test_rest_api: auth is overridden and repository +
quota functions are patched, so no real database is touched. These verify
request parsing, the port of the MCP-tool business logic, quota → HTTP mapping,
and response shapes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from devmemory.api.app import create_app
from devmemory.auth.middleware import AuthContext, require_jwt_user, require_user
from devmemory.billing.quota import QuotaExceededError
from devmemory.models.subscription import SubscriptionTier


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
    project: Any = field(default_factory=_Project)


@dataclass
class _Block:
    id: str = "block-1"
    session_id: str = "sess-1"
    block_type: str = "goal"
    content: str = "Do the thing"
    priority: int = 5
    meta_json: str | None = None
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)


_FAKE_AUTH = AuthContext(user_id="user-uuid", email="dev@example.com", tier=SubscriptionTier.FREE)

_CTX = "devmemory.api.context_routes"
_SESS = "devmemory.api.session_routes"

_PROJECT_BODY = {"slug": "user-myproject", "name": "myproject"}


@pytest.fixture()
def client():
    app = create_app()
    app.dependency_overrides[require_user] = lambda: _FAKE_AUTH
    app.dependency_overrides[require_jwt_user] = lambda: _FAKE_AUTH
    return TestClient(app, raise_server_exceptions=True)


# ── POST /context (save_context) ─────────────────────────────────────────────────


class TestSaveContext:
    def test_save_reuses_active_session(self, client):
        with (
            patch(f"{_CTX}.get_or_create_project", AsyncMock(return_value=(_Project(), False))),
            patch(f"{_CTX}.list_sessions", AsyncMock(return_value=[_Session()])),
            patch(f"{_CTX}.check_block_quota", AsyncMock(return_value=None)),
            patch(f"{_CTX}.create_context_block", AsyncMock(return_value=_Block(id="b9"))),
        ):
            r = client.post(
                "/context",
                json={
                    "project": _PROJECT_BODY,
                    "block_type": "goal",
                    "content": "Ship it",
                },
            )
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["block_id"] == "b9"
        assert data["session_id"] == "sess-1"
        assert data["block_type"] == "goal"

    def test_save_creates_session_for_new_project(self, client):
        with (
            patch(f"{_CTX}.get_or_create_project", AsyncMock(return_value=(_Project(), True))),
            patch(f"{_CTX}.check_project_quota", AsyncMock(return_value=None)),
            patch(f"{_CTX}.list_sessions", AsyncMock(return_value=[])),
            patch(f"{_CTX}.check_session_quota", AsyncMock(return_value=None)),
            patch(f"{_CTX}.create_session", AsyncMock(return_value=_Session(id="s-new"))),
            patch(f"{_CTX}.check_block_quota", AsyncMock(return_value=None)),
            patch(f"{_CTX}.create_context_block", AsyncMock(return_value=_Block())),
        ):
            r = client.post(
                "/context",
                json={
                    "project": _PROJECT_BODY,
                    "block_type": "code",
                    "content": "diff",
                },
            )
        assert r.status_code == 200
        assert r.json()["session_id"] == "s-new"

    def test_invalid_block_type_422(self, client):
        r = client.post(
            "/context",
            json={
                "project": _PROJECT_BODY,
                "block_type": "banana",
                "content": "x",
            },
        )
        assert r.status_code == 422
        assert "block_type" in r.json()["detail"]

    def test_block_quota_exceeded_402(self, client):
        with (
            patch(f"{_CTX}.get_or_create_project", AsyncMock(return_value=(_Project(), False))),
            patch(f"{_CTX}.list_sessions", AsyncMock(return_value=[_Session()])),
            patch(
                f"{_CTX}.check_block_quota",
                AsyncMock(side_effect=QuotaExceededError("too many blocks", "free", 500, 500)),
            ),
        ):
            r = client.post(
                "/context",
                json={
                    "project": _PROJECT_BODY,
                    "block_type": "note",
                    "content": "x",
                },
            )
        assert r.status_code == 402
        assert "too many blocks" in r.json()["detail"]

    def test_explicit_session_not_found_404(self, client):
        with (
            patch(f"{_CTX}.get_or_create_project", AsyncMock(return_value=(_Project(), False))),
            patch(f"{_CTX}.get_session", AsyncMock(return_value=None)),
        ):
            r = client.post(
                "/context",
                json={
                    "project": _PROJECT_BODY,
                    "block_type": "note",
                    "content": "x",
                    "session_id": "ghost",
                },
            )
        assert r.status_code == 404

    def test_empty_content_rejected_422(self, client):
        r = client.post(
            "/context",
            json={
                "project": _PROJECT_BODY,
                "block_type": "note",
                "content": "",
            },
        )
        assert r.status_code == 422


# ── POST /context/tasks (save_tasks) ─────────────────────────────────────────────


class TestSaveTasks:
    def test_bulk_tasks(self, client):
        with (
            patch(f"{_CTX}.get_or_create_project", AsyncMock(return_value=(_Project(), False))),
            patch(f"{_CTX}.list_sessions", AsyncMock(return_value=[_Session()])),
            patch(f"{_CTX}.check_block_quota", AsyncMock(return_value=None)),
            patch(
                f"{_CTX}.create_bulk_context_blocks",
                AsyncMock(return_value=[_Block(id="t1"), _Block(id="t2")]),
            ),
        ):
            r = client.post(
                "/context/tasks",
                json={
                    "project": _PROJECT_BODY,
                    "tasks": [{"title": "A"}, {"title": "B", "description": "do b", "priority": 8}],
                },
            )
        assert r.status_code == 200
        assert r.json()["task_ids"] == ["t1", "t2"]

    def test_empty_tasks_422(self, client):
        r = client.post("/context/tasks", json={"project": _PROJECT_BODY, "tasks": []})
        assert r.status_code == 422


# ── PATCH /context/blocks/{id}/status (update_task) ──────────────────────────────


class TestUpdateTaskStatus:
    def test_update_ok(self, client):
        with patch(f"{_CTX}.update_context_block_status", AsyncMock(return_value=_Block(id="t1"))):
            r = client.patch("/context/blocks/t1/status", json={"status": "done"})
        assert r.status_code == 200
        assert r.json() == {"ok": True, "block_id": "t1", "status": "done"}

    def test_invalid_status_422(self, client):
        r = client.patch("/context/blocks/t1/status", json={"status": "banana"})
        assert r.status_code == 422

    def test_missing_block_404(self, client):
        with patch(f"{_CTX}.update_context_block_status", AsyncMock(return_value=None)):
            r = client.patch("/context/blocks/ghost/status", json={"status": "done"})
        assert r.status_code == 404


# ── GET /context (get_context) ───────────────────────────────────────────────────


class TestGetContext:
    def test_by_session_id(self, client):
        with (
            patch(f"{_CTX}.get_session", AsyncMock(return_value=_Session())),
            patch(
                f"{_CTX}.get_context_blocks", AsyncMock(return_value=[_Block(), _Block(id="b2")])
            ),
        ):
            r = client.get("/context", params={"session_id": "sess-1"})
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 2
        assert data["session_id"] == "sess-1"

    def test_by_project_slug(self, client):
        with (
            patch(f"{_CTX}.get_project_by_slug", AsyncMock(return_value=_Project())),
            patch(f"{_CTX}.list_sessions", AsyncMock(return_value=[_Session()])),
            patch(f"{_CTX}.get_context_blocks", AsyncMock(return_value=[_Block()])),
        ):
            r = client.get("/context", params={"project_slug": "user-myproject"})
        assert r.status_code == 200
        assert r.json()["count"] == 1

    def test_unknown_project_returns_empty(self, client):
        with patch(f"{_CTX}.get_project_by_slug", AsyncMock(return_value=None)):
            r = client.get("/context", params={"project_slug": "nope"})
        assert r.status_code == 200
        assert r.json() == {
            "ok": True,
            "session_id": None,
            "session_title": None,
            "blocks": [],
            "count": 0,
        }

    def test_requires_selector_422(self, client):
        r = client.get("/context")
        assert r.status_code == 422


# ── POST /sessions (start_session) ───────────────────────────────────────────────


class TestStartSession:
    def test_start_new(self, client):
        with (
            patch(f"{_SESS}.get_or_create_project", AsyncMock(return_value=(_Project(), True))),
            patch(f"{_SESS}.check_project_quota", AsyncMock(return_value=None)),
            patch(f"{_SESS}.check_session_quota", AsyncMock(return_value=None)),
            patch(f"{_SESS}.create_session", AsyncMock(return_value=_Session(id="s-new"))),
        ):
            r = client.post(
                "/sessions",
                json={
                    "project": _PROJECT_BODY,
                    "title": "Build auth",
                    "tool_source": "claude",
                },
            )
        assert r.status_code == 201
        data = r.json()
        assert data["session_id"] == "s-new"
        assert data["project_created"] is True

    def test_session_quota_402(self, client):
        with (
            patch(f"{_SESS}.get_or_create_project", AsyncMock(return_value=(_Project(), False))),
            patch(
                f"{_SESS}.check_session_quota",
                AsyncMock(side_effect=QuotaExceededError("too many sessions", "free", 10, 10)),
            ),
        ):
            r = client.post("/sessions", json={"project": _PROJECT_BODY, "title": "X"})
        assert r.status_code == 402


# ── GET /sessions/{id}/resume (generate_resume_prompt) ───────────────────────────


class TestResume:
    def test_resume_ok(self, client):
        with (
            patch(f"{_SESS}.get_session", AsyncMock(return_value=_Session())),
            patch(f"{_SESS}.get_context_blocks", AsyncMock(return_value=[_Block()])),
            patch(f"{_SESS}._build_resume_prompt", return_value="RESUME PROMPT"),
        ):
            r = client.get("/sessions/sess-1/resume", params={"target_tool": "cursor"})
        assert r.status_code == 200
        data = r.json()
        assert data["prompt"] == "RESUME PROMPT"
        assert data["target_tool"] == "cursor"
        assert data["block_count"] == 1

    def test_resume_missing_session_404(self, client):
        with patch(f"{_SESS}.get_session", AsyncMock(return_value=None)):
            r = client.get("/sessions/ghost/resume")
        assert r.status_code == 404
