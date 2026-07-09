"""Sync HTTP client the watch daemon uses to push turns to the REST API.

Deliberately synchronous and small: the daemon is a simple poll loop, not an
async app. Uses ``httpx`` (already a runtime dependency).
"""

from __future__ import annotations

import os
from pathlib import Path

import httpx

_DEFAULT_HOST = "https://devmemory.onrender.com"
_TIMEOUT = 30.0


def host() -> str:
    return (os.environ.get("DEVMEMORY_HOST") or _DEFAULT_HOST).rstrip("/")


def api_key() -> str | None:
    key = os.environ.get("DEVMEMORY_API_KEY")
    if key:
        return key.strip()
    key_file = Path.home() / ".devmemory" / "api_key"
    try:
        return key_file.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


class Client:
    def __init__(self, key: str) -> None:
        self._key = key
        self._http = httpx.Client(timeout=_TIMEOUT, headers={"X-API-Key": key})

    def close(self) -> None:
        self._http.close()

    def save_block(
        self,
        project: dict,
        content: str,
        *,
        block_type: str = "note",
        session_id: str | None = None,
        priority: int = 3,
    ) -> str | None:
        """POST one context block. Returns the session_id it landed in, or None."""
        body = {
            "project": project,
            "block_type": block_type,
            "content": content,
            "session_id": session_id,
            "priority": priority,
        }
        resp = self._http.post(f"{host()}/context", json=body)
        resp.raise_for_status()
        data = resp.json()
        return data.get("session_id")
