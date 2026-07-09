"""Cursor adapter.

Cursor stores conversations in a SQLite DB at
``~/.config/Cursor/User/globalStorage/state.vscdb`` (Linux; see ``_DB_PATHS``
for macOS/Windows), table ``cursorDiskKV``:

- ``composerData:<composerId>``  → one conversation. Fields used:
  ``text``/``name`` (title), ``createdAt``, and ``fullConversationHeadersOnly``:
  an ordered list of ``{"bubbleId": ..., "type": 1|2}`` (1 = user, 2 = assistant).
- ``bubbleId:<composerId>:<bubbleId>`` → one message: ``text`` + ``type``.

We open the DB read-only + immutable so we never block Cursor's own writes.
"""

from __future__ import annotations

import json
import platform
import sqlite3
from collections.abc import Iterator
from pathlib import Path

from devmemory.watch.adapters.base import Adapter
from devmemory.watch.models import Conversation, Message

_DB_PATHS = {
    "Linux": "~/.config/Cursor/User/globalStorage/state.vscdb",
    "Darwin": "~/Library/Application Support/Cursor/User/globalStorage/state.vscdb",
    "Windows": "~/AppData/Roaming/Cursor/User/globalStorage/state.vscdb",
}

_ROLE = {1: "user", 2: "assistant"}


def _db_path() -> Path:
    template = _DB_PATHS.get(platform.system(), _DB_PATHS["Linux"])
    return Path(template.replace("~", str(Path.home())))


def _loads(value) -> dict | None:
    if not value:
        return None
    try:
        obj = json.loads(value)
    except (ValueError, TypeError):
        return None
    return obj if isinstance(obj, dict) else None


def _collect_paths(bubble: dict, out: list[str], depth: int = 0) -> None:
    """Harvest absolute file/folder paths a message referenced (for project id)."""
    if depth > 7 or len(out) > 40:
        return
    if isinstance(bubble, str):
        if bubble.startswith(("/", "file://")) and bubble.count("/") >= 2 and len(bubble) < 400:
            out.append(bubble)
    elif isinstance(bubble, dict):
        for v in bubble.values():
            _collect_paths(v, out, depth + 1)
    elif isinstance(bubble, list):
        for v in bubble:
            _collect_paths(v, out, depth + 1)


class CursorAdapter(Adapter):
    name = "cursor"

    def __init__(self, db_path: Path | None = None) -> None:
        self._db = db_path or _db_path()

    def available(self) -> bool:
        return self._db.exists()

    def _connect(self) -> sqlite3.Connection:
        # Read-only + immutable: never block or corrupt Cursor's live DB.
        return sqlite3.connect(f"file:{self._db}?mode=ro&immutable=1", uri=True)

    def conversations(self) -> Iterator[Conversation]:
        try:
            conn = self._connect()
        except sqlite3.Error:
            return
        try:
            rows = conn.execute(
                "SELECT key, value FROM cursorDiskKV WHERE key LIKE 'composerData:%'"
            ).fetchall()
            for key, value in rows:
                conv = self._build(conn, key, value)
                if conv is not None and conv.messages:
                    yield conv
        except sqlite3.Error:
            return
        finally:
            conn.close()

    def _build(self, conn: sqlite3.Connection, key: str, value) -> Conversation | None:
        data = _loads(value)
        if not data:
            return None
        composer_id = data.get("composerId") or key.split(":", 1)[-1]
        title = (data.get("text") or data.get("name") or "Untitled Cursor chat").strip()
        headers = data.get("fullConversationHeadersOnly") or []
        if not isinstance(headers, list):
            return None

        messages: list[Message] = []
        paths: list[str] = []
        for header in headers:
            if not isinstance(header, dict):
                continue
            bubble_id = header.get("bubbleId")
            if not bubble_id:
                continue
            role = _ROLE.get(header.get("type"))
            if role is None:
                continue
            row = conn.execute(
                "SELECT value FROM cursorDiskKV WHERE key = ?",
                (f"bubbleId:{composer_id}:{bubble_id}",),
            ).fetchone()
            bubble = _loads(row[0]) if row else None
            if not bubble:
                continue
            text = (bubble.get("text") or "").strip()
            _collect_paths(bubble, paths)
            if text:
                messages.append(Message(role=role, text=text))

        return Conversation(
            tool=self.name,
            id=composer_id,
            title=title[:120] or "Untitled Cursor chat",
            messages=messages,
            paths=paths,
        )
