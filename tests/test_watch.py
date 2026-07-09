"""Tests for the watch daemon: turn grouping, watermark, and the Cursor adapter."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from devmemory.watch.adapters.codex import CodexAdapter
from devmemory.watch.adapters.cursor import CursorAdapter
from devmemory.watch.adapters.generic import generic_adapters
from devmemory.watch.daemon import _exchanges
from devmemory.watch.models import Message
from devmemory.watch.project import resolve_project
from devmemory.watch.state import WatchState


def test_exchanges_pairs_user_and_assistant():
    msgs = [
        Message("user", "how do I add auth?"),
        Message("assistant", "Use JWT."),
        Message("user", "and refresh tokens?"),
        Message("assistant", "Rotate them."),
    ]
    blocks = _exchanges(msgs)
    assert len(blocks) == 2
    assert "how do I add auth?" in blocks[0]
    assert "Use JWT." in blocks[0]
    assert "refresh tokens?" in blocks[1]
    assert "Rotate them." in blocks[1]


def test_exchanges_merges_consecutive_same_role():
    msgs = [
        Message("assistant", "part one"),
        Message("assistant", "part two"),
    ]
    blocks = _exchanges(msgs)
    assert len(blocks) == 1
    assert "part one" in blocks[0] and "part two" in blocks[0]


def test_exchanges_empty():
    assert _exchanges([]) == []


def test_watch_state_watermark_roundtrip(tmp_path: Path):
    state = WatchState(tmp_path / "watch_state.json")
    assert state.saved_count("cursor:abc") == 0
    assert state.session_id("cursor:abc") is None

    state.record("cursor:abc", saved_count=4, session_id="sess-1")
    state.save()

    reloaded = WatchState(tmp_path / "watch_state.json")
    assert reloaded.saved_count("cursor:abc") == 4
    assert reloaded.session_id("cursor:abc") == "sess-1"


def test_watch_state_corrupt_is_empty(tmp_path: Path):
    p = tmp_path / "watch_state.json"
    p.write_text("not json{{{", encoding="utf-8")
    state = WatchState(p)
    assert state.saved_count("anything") == 0


def _make_cursor_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE cursorDiskKV (key TEXT PRIMARY KEY, value TEXT)")
    composer_id = "comp-1"
    headers = [
        {"bubbleId": "b1", "type": 1},
        {"bubbleId": "b2", "type": 2},
    ]
    conn.execute(
        "INSERT INTO cursorDiskKV VALUES (?, ?)",
        (
            f"composerData:{composer_id}",
            json.dumps(
                {
                    "composerId": composer_id,
                    "text": "Add login",
                    "fullConversationHeadersOnly": headers,
                }
            ),
        ),
    )
    conn.execute(
        "INSERT INTO cursorDiskKV VALUES (?, ?)",
        (
            f"bubbleId:{composer_id}:b1",
            json.dumps({"text": "add a login page", "relevantFiles": ["/home/u/proj/app.py"]}),
        ),
    )
    conn.execute(
        "INSERT INTO cursorDiskKV VALUES (?, ?)",
        (f"bubbleId:{composer_id}:b2", json.dumps({"text": "Done — added /login route."})),
    )
    conn.commit()
    conn.close()


def test_cursor_adapter_extracts_conversation(tmp_path: Path):
    db = tmp_path / "state.vscdb"
    _make_cursor_db(db)

    adapter = CursorAdapter(db_path=db)
    assert adapter.available()

    convs = list(adapter.conversations())
    assert len(convs) == 1
    conv = convs[0]
    assert conv.tool == "cursor"
    assert conv.id == "comp-1"
    assert conv.title == "Add login"
    assert [m.role for m in conv.messages] == ["user", "assistant"]
    assert conv.messages[0].text == "add a login page"
    assert "/home/u/proj/app.py" in conv.paths


def test_cursor_adapter_missing_db(tmp_path: Path):
    adapter = CursorAdapter(db_path=tmp_path / "nope.vscdb")
    assert not adapter.available()
    assert list(adapter.conversations()) == []


# ── project resolution ──────────────────────────────────────────────────────


def test_resolve_project_prefers_explicit_remote_url():
    proj = resolve_project(
        [], fallback_name="whatever", remote_url="git@github.com:acme/widget.git"
    )
    assert proj == {
        "slug": "acme-widget",
        "name": "widget",
        "remote_url": "git@github.com:acme/widget.git",
    }


def test_resolve_project_fallback_when_untethered():
    proj = resolve_project([], fallback_name="Some Chat")
    assert proj is not None
    assert proj["slug"].startswith("cursor-")


# ── Codex adapter ────────────────────────────────────────────────────────────


def _make_codex(tmp_path: Path) -> Path:
    rollout = tmp_path / "rollout.jsonl"
    lines = [
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "fix the bug"}],
        },
        {
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "Fixed it."}],
            }
        },
        {"type": "reasoning", "content": "ignore me"},  # not a chat message
    ]
    rollout.write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")

    db = tmp_path / "state_5.sqlite"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE threads "
        "(id TEXT, rollout_path TEXT, cwd TEXT, git_origin_url TEXT, title TEXT)"
    )
    conn.execute(
        "INSERT INTO threads VALUES (?, ?, ?, ?, ?)",
        ("t1", str(rollout), "/home/u/proj", "git@github.com:acme/proj.git", "Bug fix"),
    )
    conn.commit()
    conn.close()
    return db


def test_codex_adapter_reads_rollout(tmp_path: Path):
    db = _make_codex(tmp_path)
    adapter = CodexAdapter(state_db=db)
    assert adapter.available()

    convs = list(adapter.conversations())
    assert len(convs) == 1
    conv = convs[0]
    assert conv.tool == "codex"
    assert conv.remote_url == "git@github.com:acme/proj.git"
    assert [m.role for m in conv.messages] == ["user", "assistant"]
    assert conv.messages[0].text == "fix the bug"
    assert conv.messages[1].text == "Fixed it."

    proj = resolve_project(conv.paths, fallback_name=conv.title, remote_url=conv.remote_url)
    assert proj["slug"] == "acme-proj"


def test_codex_adapter_missing(tmp_path: Path):
    adapter = CodexAdapter(state_db=tmp_path / "none.sqlite")
    assert not adapter.available()
    assert list(adapter.conversations()) == []


# ── generic config-driven adapter ────────────────────────────────────────────


def test_generic_adapter_from_config(tmp_path: Path):
    convo = tmp_path / "chat-1.jsonl"
    convo.write_text(
        "\n".join(
            json.dumps(x)
            for x in [
                {"role": "user", "content": "hello"},
                {"role": "model", "content": "hi there"},
                {"role": "system", "content": "ignored"},
            ]
        ),
        encoding="utf-8",
    )
    config = tmp_path / "watch_adapters.json"
    config.write_text(
        json.dumps(
            {
                "adapters": [
                    {
                        "name": "gemini-cli",
                        "glob": str(tmp_path / "chat-*.jsonl"),
                        "role_field": "role",
                        "text_field": "content",
                        "user_values": ["user"],
                        "assistant_values": ["model", "assistant"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    adapters = generic_adapters(config)
    assert len(adapters) == 1
    a = adapters[0]
    assert a.name == "gemini-cli"
    assert a.available()

    convs = list(a.conversations())
    assert len(convs) == 1
    assert [m.role for m in convs[0].messages] == ["user", "assistant"]
    assert convs[0].messages[1].text == "hi there"


def test_generic_adapter_no_config(tmp_path: Path):
    assert generic_adapters(tmp_path / "absent.json") == []


# ── Windsurf + Antigravity hook parsers ──────────────────────────────────────


def _load_hook_module(name: str):
    import importlib.util

    path = Path(__file__).resolve().parent.parent / "src" / "devmemory" / "hooks" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_windsurf_hook_extracts_last_turn(tmp_path: Path):
    w = _load_hook_module("windsurf_save")
    transcript = tmp_path / "traj.jsonl"
    transcript.write_text(
        "\n".join(
            json.dumps(x)
            for x in [
                {
                    "type": "user_input",
                    "user_input": {"user_response": "add login"},
                    "status": "done",
                },
                {
                    "type": "planner_response",
                    "planner_response": {"response": "Adding /login."},
                    "status": "done",
                },
                {"type": "code_action", "code_action": {"path": "app.py"}, "status": "done"},
            ]
        ),
        encoding="utf-8",
    )
    user, assistant = w._last_turn(str(transcript))
    assert user == "add login"
    assert assistant == "Adding /login."


def test_windsurf_transcript_path_from_tool_info():
    w = _load_hook_module("windsurf_save")
    assert w._transcript_path({"tool_info": {"transcript_path": "/x/y.jsonl"}}) == "/x/y.jsonl"
    assert w._transcript_path({"transcript_path": "/top/level.jsonl"}) == "/top/level.jsonl"
    assert w._transcript_path({}) is None


def test_antigravity_hook_parses_json_and_jsonl(tmp_path: Path):
    a = _load_hook_module("antigravity_save")

    doc = tmp_path / "conv.json"
    doc.write_text(
        json.dumps(
            {
                "messages": [
                    {"role": "user", "content": "refactor auth"},
                    {"role": "model", "content": [{"type": "text", "text": "Done."}]},
                ]
            }
        ),
        encoding="utf-8",
    )
    user, assistant = a._last_turn(a._messages(str(doc)))
    assert user == "refactor auth"
    assert assistant == "Done."

    jl = tmp_path / "conv.jsonl"
    jl.write_text(
        "\n".join(
            json.dumps(x)
            for x in [
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "hello back"},
            ]
        ),
        encoding="utf-8",
    )
    user2, assistant2 = a._last_turn(a._messages(str(jl)))
    assert user2 == "hi"
    assert assistant2 == "hello back"
