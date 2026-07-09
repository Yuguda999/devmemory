#!/usr/bin/env python3
"""DevMemory Antigravity transcript parser — NOT wired by the installer.

The Antigravity IDE exposes no per-turn transcript hook an installer can
reliably target: its documented hooks are the SDK's Python decorators (for
SDK-built agents, not the IDE), and the community-reported ``hooks.json`` path
differs across builds. So ``devmemory install --tool antigravity`` drives
save/restore through the MCP tools + a ``~/.gemini/GEMINI.md`` rules file
instead (see cli/install.py::_add_antigravity_rules).

This module is retained as a standalone parser: if a verified per-turn hook is
confirmed on a real build, wire this in. It accepts a stdin JSON payload with a
``transcript_path``/``transcriptPath`` field and parses JSONL or a single JSON
doc, pulling role/text from a variety of shapes. Always exits 0.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import api_key, http_post, log, read_stdin_json, resolve_project  # noqa: E402

USER_CAP = 1500
ASSISTANT_CAP = 3000
_USER = {"user", "human"}
_ASSISTANT = {"assistant", "model", "agent"}


def _text_of(content) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and ("text" in block or block.get("type") == "text"):
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(p for p in parts if p).strip()
    if isinstance(content, dict):
        # e.g. {"response": "..."} / {"text": "..."}
        for k in ("text", "response", "content", "message"):
            if isinstance(content.get(k), str):
                return content[k].strip()
    return ""


def _harvest(node, out: list[tuple[str, str]], depth: int = 0) -> None:
    """Recursively collect ordered (role, text) messages from any JSON shape."""
    if depth > 8:
        return
    if isinstance(node, dict):
        role = node.get("role") or node.get("author") or node.get("speaker")
        if isinstance(role, str):
            low = role.lower()
            norm = "user" if low in _USER else "assistant" if low in _ASSISTANT else None
            if norm:
                text = _text_of(node.get("content") or node.get("message") or node.get("text"))
                if text:
                    out.append((norm, text))
                    return
        for v in node.values():
            _harvest(v, out, depth + 1)
    elif isinstance(node, list):
        for v in node:
            _harvest(v, out, depth + 1)


def _messages(transcript_path: str) -> list[tuple[str, str]]:
    try:
        with open(transcript_path, encoding="utf-8") as fh:
            raw = fh.read()
    except OSError:
        return []
    out: list[tuple[str, str]] = []
    # Try JSONL first (one message/event per line).
    lines = [ln for ln in raw.splitlines() if ln.strip()]
    parsed_any = False
    for ln in lines:
        try:
            obj = json.loads(ln)
        except ValueError:
            parsed_any = False
            break
        parsed_any = True
        _harvest(obj, out)
    if not parsed_any or not out:
        # Fall back to a single JSON document.
        with contextlib.suppress(ValueError):
            _harvest(json.loads(raw), out)
    return out


def _last_turn(messages: list[tuple[str, str]]) -> tuple[str, str]:
    user_text = ""
    assistant_parts: list[str] = []
    for role, text in reversed(messages):
        if role == "assistant":
            assistant_parts.append(text)
        elif role == "user":
            user_text = text
            break
    return user_text, "\n\n".join(reversed(assistant_parts)).strip()


def main() -> int:
    payload = read_stdin_json()
    log(
        "antigravity_save",
        {
            "stage": "received",
            "keys": sorted(payload.keys()),
            "event": payload.get("hook_event_name"),
        },
    )
    cwd = payload.get("cwd") or os.getcwd()
    transcript_path = payload.get("transcript_path") or payload.get("transcriptPath")
    if not transcript_path:
        log("antigravity_save", {"stage": "abort", "reason": "no transcript_path"})
        return 0

    key = api_key()
    if not key:
        log("antigravity_save", {"stage": "abort", "reason": "no api key"})
        return 0

    user_text, assistant_text = _last_turn(_messages(transcript_path))
    if not assistant_text:
        log("antigravity_save", {"stage": "abort", "reason": "no assistant text parsed"})
        return 0

    content = (
        f"[antigravity] User asked:\n{user_text[:USER_CAP]}\n\n"
        f"Assistant response:\n{assistant_text[:ASSISTANT_CAP]}"
    )
    body = {
        "project": resolve_project(cwd),
        "block_type": "note",
        "content": content,
        "session_id": None,
        "priority": 3,
    }
    try:
        resp = http_post("/context", body, key)
        log("antigravity_save", {"stage": "success", "resp": resp})
    except Exception as e:
        log("antigravity_save", {"stage": "error", "error": repr(e)})
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
