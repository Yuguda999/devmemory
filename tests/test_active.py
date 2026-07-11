"""Tests for the active-session marker + the strict opt-in save gate."""

from __future__ import annotations

from types import SimpleNamespace

import pytest


# ── Marker CRUD + should_save gate ───────────────────────────────────────────


def test_marker_roundtrip_and_gate(tmp_path, monkeypatch):
    from devmemory.hooks import _common

    monkeypatch.setattr(_common, "ACTIVE_PATH", tmp_path / "active.json")

    # No marker → nothing is active, nothing saves.
    assert _common.read_active() is None
    assert _common.should_save("anything") is False

    m1 = _common.write_active({"slug": "a", "name": "A", "remote_url": None}, "claude")
    assert _common.should_save("a") is True
    assert _common.should_save("b") is False
    assert m1["tool"] == "claude"

    # Same project, new tool → started_at preserved, tool updated (a `continue`).
    m2 = _common.write_active({"slug": "a", "name": "A", "remote_url": None}, "cursor")
    assert m2["started_at"] == m1["started_at"]
    assert m2["tool"] == "cursor"

    # Different project → fresh session, gate follows.
    m3 = _common.write_active({"slug": "c", "name": "C", "remote_url": None}, "cursor")
    assert m3["slug"] == "c"
    assert _common.should_save("a") is False
    assert _common.should_save("c") is True

    # set_active_tool re-points tool but keeps the project.
    _common.set_active_tool("windsurf")
    active = _common.read_active()
    assert active["slug"] == "c" and active["tool"] == "windsurf"

    _common.clear_active()
    assert _common.read_active() is None


def test_set_active_tool_noop_when_none(tmp_path, monkeypatch):
    from devmemory.hooks import _common

    monkeypatch.setattr(_common, "ACTIVE_PATH", tmp_path / "active.json")
    assert _common.set_active_tool("cursor") is None


def test_corrupt_marker_is_none(tmp_path, monkeypatch):
    from devmemory.hooks import _common

    path = tmp_path / "active.json"
    path.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(_common, "ACTIVE_PATH", path)
    assert _common.read_active() is None


# ── Daemon gate: only the active project is saved ────────────────────────────


class _FakeClient:
    def __init__(self):
        self.saved = []

    def save_block(self, project, content, session_id=None):
        self.saved.append((project, content))
        return "sess-1"


def _conv():
    from devmemory.watch.models import Conversation, Message

    return Conversation(
        tool="cursor",
        id="1",
        title="t",
        messages=[
            Message("user", "hi there"),
            Message("assistant", "a genuine assistant answer with enough length"),
        ],
        remote_url="git@github.com:me/proj.git",  # → slug "me-proj"
    )


def test_process_saves_only_active_project(tmp_path, monkeypatch):
    from devmemory.hooks import _common
    from devmemory.watch import daemon
    from devmemory.watch.state import WatchState

    monkeypatch.setattr(_common, "ACTIVE_PATH", tmp_path / "active.json")
    state = WatchState(tmp_path / "state.json")
    client = _FakeClient()

    # No active session → skip, no watermark advance.
    assert daemon._process(_conv(), state, client) == 0
    assert client.saved == []

    # A different project is active → still skip.
    _common.write_active({"slug": "other", "name": "other", "remote_url": None}, "cli")
    assert daemon._process(_conv(), state, client) == 0
    assert client.saved == []

    # The conversation's own project is active → save.
    _common.write_active(
        {"slug": "me-proj", "name": "proj", "remote_url": "git@github.com:me/proj.git"}, "cli"
    )
    assert daemon._process(_conv(), state, client) == 1
    assert len(client.saved) == 1


# ── CLI session commands ─────────────────────────────────────────────────────


def test_continue_without_active_exits(tmp_path, monkeypatch):
    from devmemory.cli import session
    from devmemory.hooks import _common

    monkeypatch.setattr(_common, "ACTIVE_PATH", tmp_path / "active.json")
    with pytest.raises(SystemExit):
        session.run_continue(SimpleNamespace(cwd=str(tmp_path), tool="cursor"))


def test_run_stop_clears_marker(tmp_path, monkeypatch, capsys):
    from devmemory.cli import session
    from devmemory.hooks import _common

    monkeypatch.setattr(_common, "ACTIVE_PATH", tmp_path / "active.json")
    monkeypatch.setattr(session, "PID_FILE", tmp_path / "watch.pid")
    _common.write_active({"slug": "a", "name": "A", "remote_url": None}, "claude")

    session.run_stop(SimpleNamespace())
    assert _common.read_active() is None
    assert "Detached" in capsys.readouterr().out


def test_daemon_running_none_without_pidfile(tmp_path, monkeypatch):
    from devmemory.cli import session

    monkeypatch.setattr(session, "PID_FILE", tmp_path / "watch.pid")
    assert session._daemon_running() is None
