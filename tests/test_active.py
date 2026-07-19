"""Tests for the active-session marker and the default-on save gate.

Auto-save is global-on (mempalace-style): every project's turns persist unless
the slug is paused (``paused.json`` / ``devmemory stop``) or auto-save is
disabled globally via ``DEVMEMORY_AUTOSAVE=off``. The ``active.json`` marker
tracks which project/tool a ``continue`` session is attached to; it no longer
gates saving.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

# ── should_save gate (default-on, opt-out) ───────────────────────────────────


def test_should_save_default_on_and_optouts(tmp_path, monkeypatch):
    from devmemory.hooks import _common

    monkeypatch.setattr(_common, "PAUSED_PATH", tmp_path / "paused.json")
    monkeypatch.delenv("DEVMEMORY_AUTOSAVE", raising=False)

    # Default: every project saves, no attach needed.
    assert _common.should_save("anything") is True
    assert _common.should_save("another") is True

    # Per-project pause opts one slug out; others keep saving.
    _common.write_paused({"b"})
    assert _common.should_save("a") is True
    assert _common.should_save("b") is False

    # Global kill switch turns everything off.
    monkeypatch.setenv("DEVMEMORY_AUTOSAVE", "off")
    assert _common.should_save("a") is False


# ── Marker CRUD (continue-session tracking) ──────────────────────────────────


def test_marker_roundtrip(tmp_path, monkeypatch):
    from devmemory.hooks import _common

    monkeypatch.setattr(_common, "ACTIVE_PATH", tmp_path / "active.json")

    assert _common.read_active() is None

    m1 = _common.write_active({"slug": "a", "name": "A", "remote_url": None}, "claude")
    assert m1["tool"] == "claude"
    assert _common.read_active()["slug"] == "a"

    # Same project, new tool → started_at preserved, tool updated (a `continue`).
    m2 = _common.write_active({"slug": "a", "name": "A", "remote_url": None}, "cursor")
    assert m2["started_at"] == m1["started_at"]
    assert m2["tool"] == "cursor"

    # Different project → fresh session.
    m3 = _common.write_active({"slug": "c", "name": "C", "remote_url": None}, "cursor")
    assert m3["slug"] == "c"

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


# ── Daemon gate: save unless the project is paused ───────────────────────────


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


def test_process_saves_when_not_paused(tmp_path, monkeypatch):
    from devmemory.hooks import _common
    from devmemory.watch import daemon
    from devmemory.watch.state import WatchState

    monkeypatch.setattr(_common, "PAUSED_PATH", tmp_path / "paused.json")
    monkeypatch.delenv("DEVMEMORY_AUTOSAVE", raising=False)

    state = WatchState(tmp_path / "state.json")
    client = _FakeClient()

    assert daemon._process(_conv(), state, client) == 1
    assert len(client.saved) == 1


def test_process_skips_when_project_paused(tmp_path, monkeypatch):
    from devmemory.hooks import _common
    from devmemory.watch import daemon
    from devmemory.watch.state import WatchState

    monkeypatch.setattr(_common, "PAUSED_PATH", tmp_path / "paused.json")
    monkeypatch.delenv("DEVMEMORY_AUTOSAVE", raising=False)

    conv = _conv()
    # Pause exactly the slug the daemon resolves this conversation to.
    proj = daemon.resolve_project(conv.paths, fallback_name=conv.title, remote_url=conv.remote_url)
    _common.write_paused({proj["slug"]})

    state = WatchState(tmp_path / "state.json")
    client = _FakeClient()

    assert daemon._process(conv, state, client) == 0
    assert client.saved == []


# ── CLI session commands ─────────────────────────────────────────────────────


def test_continue_without_active_exits(tmp_path, monkeypatch):
    from devmemory.cli import session
    from devmemory.hooks import _common

    monkeypatch.setattr(_common, "ACTIVE_PATH", tmp_path / "active.json")
    with pytest.raises(SystemExit):
        session.run_continue(SimpleNamespace(cwd=str(tmp_path), tool="cursor"))


def test_run_stop_pauses_current_project(tmp_path, monkeypatch, capsys):
    from devmemory.cli import session
    from devmemory.hooks import _common

    monkeypatch.setattr(_common, "ACTIVE_PATH", tmp_path / "active.json")
    monkeypatch.setattr(_common, "PAUSED_PATH", tmp_path / "paused.json")
    monkeypatch.setattr(session, "PID_FILE", tmp_path / "watch.pid")
    monkeypatch.setattr(
        session, "resolve_project", lambda cwd: {"slug": "a", "name": "A", "remote_url": None}
    )
    _common.write_active({"slug": "a", "name": "A", "remote_url": None}, "claude")

    session.run_stop(SimpleNamespace(cwd=str(tmp_path)))

    # Current project paused → it stops saving; its active marker is cleared.
    assert _common.should_save("a") is False
    assert _common.read_active() is None
    assert "paused" in capsys.readouterr().out.lower()


def test_daemon_running_none_without_pidfile(tmp_path, monkeypatch):
    from devmemory.cli import session

    monkeypatch.setattr(session, "PID_FILE", tmp_path / "watch.pid")
    assert session._daemon_running() is None
