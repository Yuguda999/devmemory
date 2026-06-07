"""Unit tests for the MCP tool handlers.

All DB and git-resolver interactions are mocked so tests run without a real
database or git repo.  Each test directly invokes the underlying Python
function (not via the MCP protocol wire), which is the standard pattern for
FastMCP tool unit tests.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Stub models ────────────────────────────────────────────────────────────────


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class _Project:
    id: str = "proj-uuid-1"
    slug: str = "user-myproject"
    name: str = "myproject"
    remote_url: str | None = "https://github.com/user/myproject"
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)


@dataclass
class _Session:
    id: str = "sess-uuid-1"
    project_id: str = "proj-uuid-1"
    title: str = "Test Session"
    status: str = "active"
    tool_source: str = "devmemory-mcp"
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)
    context_blocks: list = field(default_factory=list)
    project: Any = field(default_factory=_Project)


@dataclass
class _Block:
    id: str = "block-uuid-1"
    session_id: str = "sess-uuid-1"
    block_type: str = "goal"
    content: str = "Implement MCP tools"
    priority: int = 5
    meta_json: str | None = None
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)


# ── Shared patch targets ───────────────────────────────────────────────────────


_RESOLVE_KEY = "devmemory.tools.resolve_mcp_api_key"
_RESOLVE_PROJ = "devmemory.tools.resolve_project_slug"
_GET_DB = "devmemory.tools.get_db_session"
_CHECK_PROJ_QUOTA = "devmemory.tools.check_project_quota"
_CHECK_SESS_QUOTA = "devmemory.tools.check_session_quota"
_CHECK_BLOCK_QUOTA = "devmemory.tools.check_block_quota"
_GET_USAGE = "devmemory.tools.get_usage_summary"

_USAGE_STUB = {
    "tier": "free",
    "limits": {"max_projects": 3, "max_sessions_per_project": 10, "max_blocks_per_session": 500},
    "usage": {"projects": 1, "total_sessions": 1},
}


# ── Async context manager mock for get_db_session ──────────────────────────────


class _FakeDB:
    """Context manager returning a MagicMock db session."""

    def __init__(self):
        self.db = MagicMock()

    async def __aenter__(self):
        return self.db

    async def __aexit__(self, *args):
        pass


def _fake_db():
    return _FakeDB()


# ─────────────────────────────────────────────────────────────────────────────
# save_context tests
# ─────────────────────────────────────────────────────────────────────────────


class TestSaveContext:
    @pytest.fixture
    def _patches(self):
        """Set up default happy-path mocks for save_context."""
        proj = _Project()
        sess = _Session()
        block = _Block()
        fake_db = _fake_db()

        with (
            patch(_RESOLVE_KEY, AsyncMock(return_value="user-uuid")),
            patch(_RESOLVE_PROJ, AsyncMock(return_value=MagicMock(
                slug="user-myproject", name="myproject", remote_url=None
            ))),
            patch(_GET_DB, return_value=fake_db),
            patch("devmemory.tools.get_or_create_project", AsyncMock(return_value=(proj, False))),
            patch("devmemory.tools.get_session", AsyncMock(return_value=sess)),
            patch("devmemory.tools.list_sessions", AsyncMock(return_value=[sess])),
            patch("devmemory.tools.create_session", AsyncMock(return_value=sess)),
            patch("devmemory.tools.create_context_block", AsyncMock(return_value=block)),
            patch(_CHECK_PROJ_QUOTA, AsyncMock(return_value=None)),
            patch(_CHECK_SESS_QUOTA, AsyncMock(return_value=None)),
            patch(_CHECK_BLOCK_QUOTA, AsyncMock(return_value=None)),
        ):
            yield

    async def test_save_with_explicit_session_id(self, _patches):
        from devmemory.tools import save_context

        result = await save_context(
            block_type="goal",
            content="Finish the MCP layer",
            cwd="/home/user/myproject",
            session_id="sess-uuid-1",
        )
        assert result["ok"] is True
        assert result["block_type"] == "goal"
        assert "block_id" in result
        assert "session_id" in result

    async def test_save_without_session_id_reuses_active_session(self, _patches):
        """When an active session exists, save_context should reuse it."""
        from devmemory.tools import save_context

        result = await save_context(
            block_type="next_step",
            content="Write tests",
            cwd="/home/user/myproject",
        )
        assert result["ok"] is True
        # Should reuse the existing session from the fixture, not create a new one
        assert result["session_id"] == "sess-uuid-1"

    async def test_save_without_session_id_creates_when_none_active(self):
        """When no active session exists, save_context should create one."""
        from devmemory.tools import save_context

        proj = _Project()
        new_sess = _Session(id="sess-new-auto")
        block = _Block()
        fake_db = _fake_db()

        with (
            patch(_RESOLVE_KEY, AsyncMock(return_value="user-uuid")),
            patch(_RESOLVE_PROJ, AsyncMock(return_value=MagicMock(
                slug="user-myproject", name="myproject", remote_url=None
            ))),
            patch(_GET_DB, return_value=fake_db),
            patch("devmemory.tools.get_or_create_project", AsyncMock(return_value=(proj, False))),
            patch("devmemory.tools.list_sessions", AsyncMock(return_value=[])),
            patch("devmemory.tools.create_session", AsyncMock(return_value=new_sess)) as mock_create,
            patch("devmemory.tools.create_context_block", AsyncMock(return_value=block)),
            patch(_CHECK_PROJ_QUOTA, AsyncMock(return_value=None)),
            patch(_CHECK_SESS_QUOTA, AsyncMock(return_value=None)),
            patch(_CHECK_BLOCK_QUOTA, AsyncMock(return_value=None)),
        ):
            result = await save_context(
                block_type="goal",
                content="Start fresh",
                cwd="/home/user/myproject",
            )

        assert result["ok"] is True
        assert result["session_id"] == "sess-new-auto"
        mock_create.assert_called_once()

    async def test_invalid_block_type_returns_error(self):
        from devmemory.tools import save_context

        with patch(_RESOLVE_KEY, AsyncMock(return_value="user-uuid")):
            result = await save_context(
                block_type="invalid_type",
                content="something",
                cwd="/tmp",
            )
        assert result["ok"] is False
        assert "block_type" in result["error"]

    async def test_empty_content_returns_error(self):
        from devmemory.tools import save_context

        with patch(_RESOLVE_KEY, AsyncMock(return_value="user-uuid")):
            result = await save_context(
                block_type="goal",
                content="   ",
                cwd="/tmp",
            )
        assert result["ok"] is False
        assert "empty" in result["error"]

    async def test_bad_priority_returns_error(self):
        from devmemory.tools import save_context

        with patch(_RESOLVE_KEY, AsyncMock(return_value="user-uuid")):
            result = await save_context(
                block_type="goal",
                content="something",
                cwd="/tmp",
                priority=99,
            )
        assert result["ok"] is False
        assert "priority" in result["error"]

    async def test_invalid_api_key_returns_error(self):
        from devmemory.tools import save_context

        with patch(_RESOLVE_KEY, AsyncMock(side_effect=ValueError("Invalid key"))):
            result = await save_context(
                block_type="goal",
                content="x",
                cwd="/tmp",
                api_key="bad-key",
            )
        assert result["ok"] is False
        assert "Invalid key" in result["error"]

    async def test_api_key_from_env_var(self, monkeypatch):
        """_pick_key should use DEVMEMORY_API_KEY when no arg is passed."""
        monkeypatch.setenv("DEVMEMORY_API_KEY", "dm_key_from_env")
        from devmemory.auth.mcp_auth import _pick_key

        assert _pick_key(None) == "dm_key_from_env"



# ─────────────────────────────────────────────────────────────────────────────
# get_context tests
# ─────────────────────────────────────────────────────────────────────────────


class TestGetContext:
    async def test_returns_blocks_for_session(self):
        from devmemory.tools import get_context

        block = _Block(block_type="goal", content="Finish tools layer")
        sess = _Session()

        with (
            patch(_RESOLVE_KEY, AsyncMock(return_value="user-uuid")),
            patch(_GET_DB, return_value=_fake_db()),
            patch("devmemory.tools.get_session", AsyncMock(return_value=sess)),
            patch("devmemory.tools.get_context_blocks", AsyncMock(return_value=[block])),
        ):
            result = await get_context(
                cwd="/home/user/myproject",
                session_id="sess-uuid-1",
            )

        assert result["ok"] is True
        assert result["count"] == 1
        assert result["blocks"][0]["block_type"] == "goal"

    async def test_no_active_session_returns_empty(self):
        from devmemory.tools import get_context

        with (
            patch(_RESOLVE_KEY, AsyncMock(return_value="user-uuid")),
            patch(_RESOLVE_PROJ, AsyncMock(return_value=MagicMock(
                slug="user-proj", name="proj", remote_url=None
            ))),
            patch(_GET_DB, return_value=_fake_db()),
            patch("devmemory.tools.get_or_create_project", AsyncMock(
                return_value=(_Project(), False)
            )),
            patch("devmemory.tools.list_sessions", AsyncMock(return_value=[])),
        ):
            result = await get_context(cwd="/home/user/proj")

        assert result["ok"] is True
        assert result["blocks"] == []
        assert result["count"] == 0

    async def test_invalid_block_type_filter_returns_error(self):
        from devmemory.tools import get_context

        with patch(_RESOLVE_KEY, AsyncMock(return_value="user-uuid")):
            result = await get_context(
                cwd="/tmp",
                block_type="nonexistent_type",
            )
        assert result["ok"] is False


# ─────────────────────────────────────────────────────────────────────────────
# start_session tests
# ─────────────────────────────────────────────────────────────────────────────


class TestStartSession:
    async def test_creates_session_and_project(self):
        from devmemory.tools import start_session

        proj = _Project(id="proj-new")
        sess = _Session(id="sess-new")

        with (
            patch(_RESOLVE_KEY, AsyncMock(return_value="user-uuid")),
            patch(_RESOLVE_PROJ, AsyncMock(return_value=MagicMock(
                slug="user-myproject", name="myproject", remote_url="https://github.com/user/myproject"
            ))),
            patch(_GET_DB, return_value=_fake_db()),
            patch("devmemory.tools.get_or_create_project", AsyncMock(return_value=(proj, True))),
            patch("devmemory.tools.create_session", AsyncMock(return_value=sess)),
            patch(_CHECK_PROJ_QUOTA, AsyncMock(return_value=None)),
            patch(_CHECK_SESS_QUOTA, AsyncMock(return_value=None)),
        ):
            result = await start_session(
                title="Implement auth",
                cwd="/home/user/myproject",
                tool_source="cursor",
            )

        assert result["ok"] is True
        assert result["session_id"] == "sess-new"
        assert result["project_created"] is True

    async def test_empty_title_returns_error(self):
        from devmemory.tools import start_session

        with patch(_RESOLVE_KEY, AsyncMock(return_value="user-uuid")):
            result = await start_session(title="   ", cwd="/tmp")
        assert result["ok"] is False
        assert "title" in result["error"]


# ─────────────────────────────────────────────────────────────────────────────
# end_session tests
# ─────────────────────────────────────────────────────────────────────────────


class TestEndSession:
    async def test_marks_session_completed(self):
        from devmemory.tools import end_session

        updated_sess = _Session(status="completed")

        with (
            patch(_RESOLVE_KEY, AsyncMock(return_value="user-uuid")),
            patch(_GET_DB, return_value=_fake_db()),
            patch("devmemory.tools.update_session", AsyncMock(return_value=updated_sess)),
        ):
            result = await end_session(session_id="sess-uuid-1")

        assert result["ok"] is True
        assert result["status"] == "completed"

    async def test_invalid_status_returns_error(self):
        from devmemory.tools import end_session

        with patch(_RESOLVE_KEY, AsyncMock(return_value="user-uuid")):
            result = await end_session(session_id="sess-uuid-1", status="deleted")
        assert result["ok"] is False

    async def test_session_not_found_returns_error(self):
        from devmemory.tools import end_session

        with (
            patch(_RESOLVE_KEY, AsyncMock(return_value="user-uuid")),
            patch(_GET_DB, return_value=_fake_db()),
            patch("devmemory.tools.update_session", AsyncMock(return_value=None)),
        ):
            result = await end_session(session_id="ghost-id")
        assert result["ok"] is False


# ─────────────────────────────────────────────────────────────────────────────
# generate_resume_prompt tests
# ─────────────────────────────────────────────────────────────────────────────


class TestGenerateResumePromptTool:
    async def test_returns_prompt_string(self):
        from devmemory.tools import generate_resume_prompt as grt

        blocks = [
            _Block(block_type="goal", content="Finish MCP layer"),
            _Block(id="b2", block_type="next_step", content="Write tests"),
        ]
        sess = _Session()

        with (
            patch(_RESOLVE_KEY, AsyncMock(return_value="user-uuid")),
            patch(_GET_DB, return_value=_fake_db()),
            patch("devmemory.tools.get_session", AsyncMock(return_value=sess)),
            patch("devmemory.tools.get_context_blocks", AsyncMock(return_value=blocks)),
        ):
            result = await grt(session_id="sess-uuid-1", target_tool="claude")

        assert result["ok"] is True
        assert result["block_count"] == 2
        assert "Finish MCP layer" in result["prompt"]
        assert "Write tests" in result["prompt"]

    async def test_session_not_found_returns_error(self):
        from devmemory.tools import generate_resume_prompt as grt

        with (
            patch(_RESOLVE_KEY, AsyncMock(return_value="user-uuid")),
            patch(_GET_DB, return_value=_fake_db()),
            patch("devmemory.tools.get_session", AsyncMock(return_value=None)),
        ):
            result = await grt(session_id="ghost-id")
        assert result["ok"] is False


# ─────────────────────────────────────────────────────────────────────────────
# list_projects tool tests
# ─────────────────────────────────────────────────────────────────────────────


class TestListProjectsTool:
    async def test_returns_projects(self):
        from devmemory.tools import list_projects_tool

        projects = [_Project(id="p1", slug="a-b", name="b"), _Project(id="p2", slug="c-d", name="d")]

        with (
            patch(_RESOLVE_KEY, AsyncMock(return_value="user-uuid")),
            patch(_GET_DB, return_value=_fake_db()),
            patch("devmemory.tools.list_projects", AsyncMock(return_value=projects)),
            patch(_GET_USAGE, AsyncMock(return_value=_USAGE_STUB)),
        ):
            result = await list_projects_tool()

        assert result["ok"] is True
        assert result["count"] == 2
        assert result["projects"][0]["slug"] == "a-b"
        assert result["quota"]["tier"] == "free"

    async def test_empty_returns_ok_with_empty_list(self):
        from devmemory.tools import list_projects_tool

        with (
            patch(_RESOLVE_KEY, AsyncMock(return_value="user-uuid")),
            patch(_GET_DB, return_value=_fake_db()),
            patch("devmemory.tools.list_projects", AsyncMock(return_value=[])),
            patch(_GET_USAGE, AsyncMock(return_value=_USAGE_STUB)),
        ):
            result = await list_projects_tool()

        assert result["ok"] is True
        assert result["projects"] == []
        assert "quota" in result


# ─────────────────────────────────────────────────────────────────────────────
# mcp_auth._pick_key tests
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
