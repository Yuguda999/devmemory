#!/usr/bin/env python3
"""DevMemory Stop hook — auto-save each turn (deterministic safety net).

When Claude finishes a turn, extract the last user prompt + assistant reply
from the transcript and persist them as a context block. Runs regardless of
whether the model chose to call save_context, so nothing is ever lost.

Never blocks (no ``continue: false``) and always exits 0.
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import (  # noqa: E402
    api_key,
    http_post,
    log,
    read_stdin_json,
    resolve_project,
    should_save,
)

USER_CAP = 1200
ASSISTANT_CAP = 2500
MIN_ASSISTANT_LEN = 40  # floor for a text-only turn; tool-work turns bypass this


def _text_from_content(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(p for p in parts if p)
    return ""


def _has_tool_use(content) -> bool:
    """True if this assistant entry contains a tool call (work happened)."""
    if isinstance(content, list):
        return any(isinstance(b, dict) and b.get("type") == "tool_use" for b in content)
    return False


def _last_turn(transcript_path: str) -> tuple[str, str, bool]:
    """Return (last_user_text, whole_assistant_turn, did_tool_work).

    A single turn is spread across many transcript entries (thinking, multiple
    tool_use / text blocks, then a short closing text). The old code grabbed
    only the LAST text fragment and rejected it on a 200-char floor, so every
    turn aborted. Here we aggregate ALL assistant text emitted since the most
    recent real user prompt, and flag whether any tool ran.
    """
    try:
        with open(transcript_path, encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError:
        return "", "", False

    user_text = ""
    assistant_parts: list[str] = []
    did_tool_work = False

    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        etype = entry.get("type")
        msg = entry.get("message") or {}
        role = msg.get("role") or etype
        content = msg.get("content")
        text = _text_from_content(content).strip()

        if role == "assistant":
            if text:
                assistant_parts.append(text)
            if _has_tool_use(content):
                did_tool_work = True
        elif role == "user" and text:
            # A user message WITH plain text marks the start of this turn.
            # tool_result-only user entries have no text and are skipped, so
            # they don't prematurely cut the turn.
            user_text = text
            break

    assistant_text = "\n\n".join(reversed(assistant_parts)).strip()
    return user_text, assistant_text, did_tool_work


def main() -> int:
    payload = read_stdin_json()
    log(
        "stop_save",
        {
            "stage": "received",
            "payload_keys": sorted(payload.keys()),
            "cwd_arg": payload.get("cwd"),
        },
    )
    cwd = payload.get("cwd") or os.getcwd()
    transcript_path = payload.get("transcript_path")
    if not transcript_path:
        log("stop_save", {"stage": "abort", "reason": "no transcript_path in payload"})
        return 0

    key = api_key()
    if not key:
        log("stop_save", {"stage": "abort", "reason": "no api key"})
        return 0

    user_text, assistant_text, did_tool_work = _last_turn(transcript_path)
    if not assistant_text:
        log("stop_save", {"stage": "abort", "reason": "no assistant text in turn"})
        return 0
    # Save if the turn did real work (any tool call) OR produced non-trivial
    # text. Terse-but-substantive turns (e.g. caveman mode) still save.
    if not did_tool_work and len(assistant_text) < MIN_ASSISTANT_LEN:
        log(
            "stop_save",
            {
                "stage": "abort",
                "reason": "trivial turn",
                "len": len(assistant_text),
                "tool_work": did_tool_work,
            },
        )
        return 0

    content = (
        f"User asked:\n{user_text[:USER_CAP]}\n\n"
        f"Assistant response:\n{assistant_text[:ASSISTANT_CAP]}"
    )

    proj = resolve_project(cwd)
    if not should_save(proj["slug"]):
        log("stop_save", {"stage": "skip", "reason": "auto-save paused/off", "slug": proj["slug"]})
        return 0
    body = {
        "project": proj,
        "block_type": "note",
        "content": content,
        "session_id": None,  # reuse newest active session, else auto-create
        "priority": 3,
    }
    try:
        resp = http_post("/context", body, key)
        log("stop_save", {"stage": "success", "resp": resp})
    except Exception as e:
        log("stop_save", {"stage": "error", "error": repr(e)})
        return 0  # backend down — never block Stop
    return 0


if __name__ == "__main__":
    sys.exit(main())
