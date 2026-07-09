"""Codex CLI adapter.

Codex (OpenAI's CLI agent) records each conversation as a *rollout* JSONL file
and indexes them in a SQLite state DB at ``~/.codex/state_<n>.sqlite`` (the
suffix is a schema version — we glob for it). The ``threads`` table gives us,
per conversation: ``rollout_path`` (the JSONL), ``cwd``, ``git_origin_url`` and
``title`` — so project resolution is exact.

The rollout JSONL has shifted format across Codex versions, so message parsing
here is deliberately permissive: it accepts a message wrapped in a
``response_item``/``payload`` envelope or a bare ``{role, content}`` line, and
pulls text from ``input_text``/``output_text``/``text`` content blocks.
"""

from __future__ import annotations

import glob
import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path

from devmemory.watch.adapters.base import Adapter
from devmemory.watch.models import Conversation, Message

_ROLES = ("user", "assistant")


def _codex_dir() -> Path:
    return Path.home() / ".codex"


def _state_dbs() -> list[Path]:
    return [Path(p) for p in sorted(glob.glob(str(_codex_dir() / "state_*.sqlite")))]


def _content_text(content) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") in ("input_text", "output_text", "text") or "text" in block:
                    parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(p for p in parts if p).strip()
    return ""


def _message_from_line(obj: dict) -> Message | None:
    """Extract a user/assistant Message from one rollout JSONL object, if any."""
    # Unwrap response_item / payload envelopes used by newer rollouts.
    node = obj
    if isinstance(node.get("payload"), dict):
        node = node["payload"]
    # Skip non-message events (reasoning / function_call / tool) that carry no role.
    if node.get("type") not in (None, "message", "response_item") and "role" not in node:
        return None
    role = node.get("role")
    if role not in _ROLES:
        return None
    text = _content_text(node.get("content"))
    if not text:
        return None
    return Message(role=role, text=text)


class CodexAdapter(Adapter):
    name = "codex"

    def __init__(self, state_db: Path | None = None) -> None:
        # Explicit db for tests; otherwise discover the versioned state DB.
        self._explicit = state_db

    def _dbs(self) -> list[Path]:
        if self._explicit is not None:
            return [self._explicit] if self._explicit.exists() else []
        return _state_dbs()

    def available(self) -> bool:
        for db in self._dbs():
            try:
                conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
                has = conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='threads'"
                ).fetchone()
                conn.close()
                if has:
                    return True
            except sqlite3.Error:
                continue
        return False

    def conversations(self) -> Iterator[Conversation]:
        for db in self._dbs():
            try:
                conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
            except sqlite3.Error:
                continue
            try:
                rows = conn.execute(
                    "SELECT id, rollout_path, cwd, git_origin_url, title FROM threads"
                ).fetchall()
            except sqlite3.Error:
                conn.close()
                continue
            conn.close()
            for thread_id, rollout_path, cwd, git_url, title in rows:
                conv = self._build(thread_id, rollout_path, cwd, git_url, title)
                if conv is not None and conv.messages:
                    yield conv

    def _build(self, thread_id, rollout_path, cwd, git_url, title) -> Conversation | None:
        if not rollout_path:
            return None
        path = Path(str(rollout_path)).expanduser()
        if not path.is_file():
            return None
        messages: list[Message] = []
        try:
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except ValueError:
                        continue
                    if not isinstance(obj, dict):
                        continue
                    msg = _message_from_line(obj)
                    if msg is not None:
                        messages.append(msg)
        except OSError:
            return None

        # git_origin_url / cwd feed project resolution; the resolver slugs a
        # remote URL identically to the server, so pass the URL as a path hint
        # too (harmless if it's not a filesystem path).
        paths = [p for p in (cwd,) if p]
        return Conversation(
            tool=self.name,
            id=str(thread_id),
            title=(title or "Codex session")[:120],
            messages=messages,
            paths=paths,
            remote_url=git_url or None,
        )
