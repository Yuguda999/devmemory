"""Watermark persistence for the watch daemon.

Tracks, per conversation, how many messages have already been saved and which
DevMemory session they were saved to — so a restart never re-saves old turns
and every turn of one conversation lands in the same session.

Stored as JSON at ``~/.devmemory/watch_state.json``. Corrupt/missing state is
treated as empty (safe: at worst we re-save recent turns once).
"""

from __future__ import annotations

import json
from pathlib import Path


class WatchState:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (Path.home() / ".devmemory" / "watch_state.json")
        self._data: dict = {}
        self._load()

    def _load(self) -> None:
        try:
            self._data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self._data = {}
        if not isinstance(self._data, dict):
            self._data = {}
        self._data.setdefault("conversations", {})

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self._data, indent=2) + "\n", encoding="utf-8")
        tmp.replace(self.path)

    # ── per-conversation watermark ──────────────────────────────────────────

    def saved_count(self, key: str) -> int:
        """How many messages of this conversation have already been saved."""
        return int(self._data["conversations"].get(key, {}).get("saved_count", 0))

    def session_id(self, key: str) -> str | None:
        return self._data["conversations"].get(key, {}).get("session_id")

    def record(self, key: str, saved_count: int, session_id: str | None) -> None:
        entry = self._data["conversations"].setdefault(key, {})
        entry["saved_count"] = saved_count
        if session_id:
            entry["session_id"] = session_id
