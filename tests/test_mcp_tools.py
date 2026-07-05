"""Unit tests for the MCP tool handlers.

The MCP tools are now thin HTTP clients of the REST API. These tests mock the
``devmemory.tools._api`` HTTP helper and ``resolve_project_slug`` (git), so they
run without a network, server, database, or git repo. Each test invokes the
underlying Python function directly (not via the MCP wire), the standard pattern
for FastMCP tool unit tests.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_API = "devmemory.tools._api"
_RESOLVE_PROJ = "devmemory.tools.resolve_project_slug"


def _proj(slug="user-myproject", name="myproject", remote_url=None):
    # SimpleNamespace (not MagicMock) — MagicMock treats `name=` as the mock's
    # own name, not an attribute, so proj.name would be a child mock.
    return SimpleNamespace(slug=slug, name=name, remote_url=remote_url)


# ─────────────────────────────────────────────────────────────────────────────
# save_context
# ─────────────────────────────────────────────────────────────────────────────


class TestSaveContext:
    async def test_posts_to_context_endpoint(self):
        from devmemory.tools import save_context

        api = AsyncMock(return_value={
            "ok": True, "block_id": "b1", "session_id": "s1",
            "project_slug": "user-myproject", "block_type": "goal",
        })
        with patch(_RESOLVE_PROJ, AsyncMock(return_value=_proj(remote_url="https://x/y"))), \
             patch(_API, api):
            result = await save_context(
                block_type="Goal", content="  Finish the MCP layer  ",
                cwd="/home/user/myproject", session_id="s1", priority=7,
            )

        assert result["ok"] is True
        assert result["block_id"] == "b1"
        method, path = api.call_args.args[0], api.call_args.args[1]
        body = api.call_args.kwargs["json"]
        assert (method, path) == ("POST", "/context")
        assert body["block_type"] == "goal"           # normalised
        assert body["content"] == "Finish the MCP layer"  # stripped
        assert body["priority"] == 7
        assert body["session_id"] == "s1"
        assert body["project"] == {
            "slug": "user-myproject", "name": "myproject", "remote_url": "https://x/y",
        }

    async def test_invalid_block_type_returns_error_without_calling_api(self):
        from devmemory.tools import save_context

        api = AsyncMock()
        with patch(_API, api):
            result = await save_context(block_type="banana", content="x", cwd="/tmp")
        assert result["ok"] is False
        assert "block_type" in result["error"]
        api.assert_not_called()

    async def test_empty_content_returns_error(self):
        from devmemory.tools import save_context

        result = await save_context(block_type="goal", content="   ", cwd="/tmp")
        assert result["ok"] is False
        assert "empty" in result["error"]

    async def test_bad_priority_returns_error(self):
        from devmemory.tools import save_context

        result = await save_context(block_type="goal", content="x", cwd="/tmp", priority=99)
        assert result["ok"] is False
        assert "priority" in result["error"]

    async def test_missing_api_key_returns_error(self, monkeypatch):
        from devmemory.tools import save_context

        monkeypatch.delenv("DEVMEMORY_API_KEY", raising=False)
        with patch(_RESOLVE_PROJ, AsyncMock(return_value=_proj())):
            result = await save_context(
                block_type="goal", content="x", cwd="/tmp", api_key=None,
            )
        assert result["ok"] is False
        assert "DEVMEMORY_API_KEY" in result["error"]


# ─────────────────────────────────────────────────────────────────────────────
# save_tasks
# ─────────────────────────────────────────────────────────────────────────────


class TestSaveTasks:
    async def test_posts_tasks(self):
        from devmemory.tools import save_tasks

        api = AsyncMock(return_value={
            "ok": True, "session_id": "s1", "project_slug": "user-myproject",
            "task_ids": ["t1", "t2"],
        })
        with patch(_RESOLVE_PROJ, AsyncMock(return_value=_proj())), patch(_API, api):
            result = await save_tasks(
                tasks=[{"title": "A"}, {"description": "no title", "priority": 8}],
                cwd="/home/user/myproject",
            )

        assert result["task_ids"] == ["t1", "t2"]
        body = api.call_args.kwargs["json"]
        assert api.call_args.args[:2] == ("POST", "/context/tasks")
        assert body["tasks"][0]["title"] == "A"
        assert body["tasks"][1]["title"] == "Task 2"   # default title
        assert body["tasks"][1]["priority"] == 8

    async def test_empty_tasks_returns_error(self):
        from devmemory.tools import save_tasks

        result = await save_tasks(tasks=[], cwd="/tmp")
        assert result["ok"] is False
        assert "empty" in result["error"]


# ─────────────────────────────────────────────────────────────────────────────
# update_task
# ─────────────────────────────────────────────────────────────────────────────


class TestUpdateTask:
    async def test_patches_status(self):
        from devmemory.tools import update_task

        api = AsyncMock(return_value={"ok": True, "block_id": "t1", "status": "done"})
        with patch(_API, api):
            result = await update_task(block_id="t1", status="done", cwd="/tmp")
        assert result == {"ok": True, "block_id": "t1", "status": "done"}
        assert api.call_args.args[:2] == ("PATCH", "/context/blocks/t1/status")
        assert api.call_args.kwargs["json"] == {"status": "done"}

    async def test_invalid_status_returns_error(self):
        from devmemory.tools import update_task

        result = await update_task(block_id="t1", status="banana", cwd="/tmp")
        assert result["ok"] is False


# ─────────────────────────────────────────────────────────────────────────────
# get_context
# ─────────────────────────────────────────────────────────────────────────────


class TestGetContext:
    async def test_by_session_id(self):
        from devmemory.tools import get_context

        api = AsyncMock(return_value={
            "ok": True, "session_id": "s1", "session_title": "T",
            "blocks": [{"id": "b1", "block_type": "goal", "content": "c"}], "count": 1,
        })
        with patch(_API, api):
            result = await get_context(cwd="/tmp", session_id="s1")
        assert result["count"] == 1
        assert api.call_args.args[:2] == ("GET", "/context")
        assert api.call_args.kwargs["params"]["session_id"] == "s1"

    async def test_by_project_slug_when_no_session(self):
        from devmemory.tools import get_context

        api = AsyncMock(return_value={"ok": True, "session_id": None, "blocks": [], "count": 0})
        with patch(_RESOLVE_PROJ, AsyncMock(return_value=_proj(slug="user-proj"))), \
             patch(_API, api):
            result = await get_context(cwd="/home/user/proj")
        assert result["count"] == 0
        assert api.call_args.kwargs["params"]["project_slug"] == "user-proj"

    async def test_invalid_block_type_filter_returns_error(self):
        from devmemory.tools import get_context

        result = await get_context(cwd="/tmp", block_type="nope")
        assert result["ok"] is False


# ─────────────────────────────────────────────────────────────────────────────
# start_session
# ─────────────────────────────────────────────────────────────────────────────


class TestStartSession:
    async def test_creates_session(self):
        from devmemory.tools import start_session

        api = AsyncMock(return_value={
            "ok": True, "session_id": "s-new", "project_id": "p1",
            "project_slug": "user-myproject", "project_name": "myproject",
            "project_created": True,
        })
        with patch(_RESOLVE_PROJ, AsyncMock(return_value=_proj())), patch(_API, api):
            result = await start_session(title="Build auth", cwd="/x", tool_source="cursor")
        assert result["session_id"] == "s-new"
        assert result["project_created"] is True
        assert api.call_args.args[:2] == ("POST", "/sessions")
        assert api.call_args.kwargs["json"]["tool_source"] == "cursor"

    async def test_empty_title_returns_error(self):
        from devmemory.tools import start_session

        result = await start_session(title="  ", cwd="/tmp")
        assert result["ok"] is False
        assert "title" in result["error"]


# ─────────────────────────────────────────────────────────────────────────────
# end_session
# ─────────────────────────────────────────────────────────────────────────────


class TestEndSession:
    async def test_marks_completed_and_normalises_response(self):
        from devmemory.tools import end_session

        # Endpoint returns a SessionResponse (no "ok" field).
        api = AsyncMock(return_value={"id": "s1", "status": "completed", "title": "T"})
        with patch(_API, api):
            result = await end_session(session_id="s1")
        assert result == {"ok": True, "session_id": "s1", "status": "completed"}

    async def test_invalid_status_returns_error(self):
        from devmemory.tools import end_session

        result = await end_session(session_id="s1", status="deleted")
        assert result["ok"] is False

    async def test_not_found_error_passthrough(self):
        from devmemory.tools import end_session

        api = AsyncMock(return_value={"ok": False, "error": "Session not found"})
        with patch(_API, api):
            result = await end_session(session_id="ghost")
        assert result["ok"] is False
        assert "not found" in result["error"]


# ─────────────────────────────────────────────────────────────────────────────
# list_sessions
# ─────────────────────────────────────────────────────────────────────────────


class TestListSessions:
    async def test_lists_by_project_slug(self):
        from devmemory.tools import list_sessions_tool

        api = AsyncMock(return_value={"sessions": [{"id": "s1"}], "count": 1})
        with patch(_RESOLVE_PROJ, AsyncMock(return_value=_proj(slug="user-myproject"))), \
             patch(_API, api):
            result = await list_sessions_tool(cwd="/x", status="active")
        assert result["ok"] is True
        assert result["project_slug"] == "user-myproject"
        assert result["count"] == 1
        assert api.call_args.kwargs["params"]["project_slug"] == "user-myproject"
        assert api.call_args.kwargs["params"]["status"] == "active"


# ─────────────────────────────────────────────────────────────────────────────
# generate_resume_prompt
# ─────────────────────────────────────────────────────────────────────────────


class TestGenerateResumePrompt:
    async def test_returns_prompt(self):
        from devmemory.tools import generate_resume_prompt as grt

        api = AsyncMock(return_value={
            "ok": True, "session_id": "s1", "target_tool": "claude",
            "block_count": 2, "prompt": "RESUME",
        })
        with patch(_API, api):
            result = await grt(session_id="s1", target_tool="claude")
        assert result["prompt"] == "RESUME"
        assert api.call_args.args[:2] == ("GET", "/sessions/s1/resume")
        assert api.call_args.kwargs["params"]["target_tool"] == "claude"

    async def test_error_passthrough(self):
        from devmemory.tools import generate_resume_prompt as grt

        api = AsyncMock(return_value={"ok": False, "error": "Session 'ghost' not found"})
        with patch(_API, api):
            result = await grt(session_id="ghost")
        assert result["ok"] is False


# ─────────────────────────────────────────────────────────────────────────────
# list_projects
# ─────────────────────────────────────────────────────────────────────────────


class TestListProjects:
    async def test_returns_projects(self):
        from devmemory.tools import list_projects_tool

        api = AsyncMock(return_value={
            "projects": [{"slug": "a-b", "name": "b"}, {"slug": "c-d", "name": "d"}],
            "count": 2,
        })
        with patch(_API, api):
            result = await list_projects_tool()
        assert result["ok"] is True
        assert result["count"] == 2
        assert result["projects"][0]["slug"] == "a-b"
        assert api.call_args.args[:2] == ("GET", "/projects")

    async def test_empty(self):
        from devmemory.tools import list_projects_tool

        api = AsyncMock(return_value={"projects": [], "count": 0})
        with patch(_API, api):
            result = await list_projects_tool()
        assert result["ok"] is True
        assert result["projects"] == []


# ─────────────────────────────────────────────────────────────────────────────
# _api HTTP helper: error mapping
# ─────────────────────────────────────────────────────────────────────────────


class TestApiHelper:
    async def test_missing_key_returns_error(self, monkeypatch):
        from devmemory.tools import _api

        monkeypatch.delenv("DEVMEMORY_API_KEY", raising=False)
        result = await _api("GET", "/projects", None)
        assert result["ok"] is False
        assert "DEVMEMORY_API_KEY" in result["error"]

    async def test_http_4xx_maps_to_error_detail(self, monkeypatch):
        from devmemory.tools import _api

        monkeypatch.setenv("DEVMEMORY_API_KEY", "dm_key_x")

        resp = MagicMock()
        resp.status_code = 401
        resp.json.return_value = {"detail": "Invalid or revoked API key"}

        class _Client:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                pass

            async def request(self, *a, **k):
                return resp

        with patch("devmemory.tools.httpx.AsyncClient", return_value=_Client()):
            result = await _api("GET", "/projects", "dm_key_x")
        assert result == {"ok": False, "error": "Invalid or revoked API key"}

    async def test_network_error_maps_to_error(self, monkeypatch):
        import httpx

        from devmemory.tools import _api

        monkeypatch.setenv("DEVMEMORY_API_KEY", "dm_key_x")

        class _Client:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                pass

            async def request(self, *a, **k):
                raise httpx.ConnectError("refused")

        with patch("devmemory.tools.httpx.AsyncClient", return_value=_Client()):
            result = await _api("GET", "/projects", "dm_key_x")
        assert result["ok"] is False
        assert "Could not reach DevMemory" in result["error"]


# ─────────────────────────────────────────────────────────────────────────────
# mcp_auth._pick_key
# ─────────────────────────────────────────────────────────────────────────────


class TestPickKey:
    def test_arg_takes_precedence_over_env(self, monkeypatch):
        from devmemory.auth.mcp_auth import _pick_key

        monkeypatch.setenv("DEVMEMORY_API_KEY", "env-key")
        assert _pick_key("arg-key") == "arg-key"

    def test_env_used_when_arg_is_none(self, monkeypatch):
        from devmemory.auth.mcp_auth import _pick_key

        monkeypatch.setenv("DEVMEMORY_API_KEY", "env-key")
        assert _pick_key(None) == "env-key"

    def test_empty_arg_falls_back_to_env(self, monkeypatch):
        from devmemory.auth.mcp_auth import _pick_key

        monkeypatch.setenv("DEVMEMORY_API_KEY", "env-key")
        assert _pick_key("   ") == "env-key"

    def test_no_key_raises_value_error(self, monkeypatch):
        from devmemory.auth.mcp_auth import _pick_key

        monkeypatch.delenv("DEVMEMORY_API_KEY", raising=False)
        with pytest.raises(ValueError, match="DEVMEMORY_API_KEY"):
            _pick_key(None)
