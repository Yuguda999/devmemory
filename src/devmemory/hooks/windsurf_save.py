#!/usr/bin/env python3
"""DevMemory Windsurf hook — auto-save each Cascade turn (deterministic).

Wired to Windsurf's ``post_cascade_response_with_transcript`` hook, which fires
after every Cascade response and writes the full conversation to a JSONL file,
passing its path on stdin as ``tool_info.transcript_path``. We read the LAST
turn (newest user prompt + the planner responses after it) and POST it — no
reliance on the model calling save_context, and no need to read Windsurf's
encrypted on-disk conversation store.

Transcript lines look like::

    {"type":"user_input","user_input":{"user_response":"..."},"status":"done"}
    {"type":"planner_response","planner_response":{"response":"..."},"status":"done"}

Always exits 0 so a DevMemory outage never blocks Cascade.
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

USER_CAP = 1500
ASSISTANT_CAP = 3000


def _transcript_path(payload: dict) -> str | None:
    info = payload.get("tool_info")
    if isinstance(info, dict) and info.get("transcript_path"):
        return info["transcript_path"]
    # Some builds put it at the top level.
    return payload.get("transcript_path")


def _last_turn(transcript_path: str) -> tuple[str, str]:
    """Return (last_user_text, assistant_text_after_it) from the Windsurf JSONL."""
    try:
        with open(transcript_path, encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError:
        return "", ""

    user_text = ""
    assistant_parts: list[str] = []
    # Walk backwards: collect planner responses until we hit the newest user_input.
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        etype = entry.get("type")
        if etype == "planner_response":
            resp = (entry.get("planner_response") or {}).get("response", "")
            if resp.strip():
                assistant_parts.append(resp.strip())
        elif etype == "user_input":
            user_text = (entry.get("user_input") or {}).get("user_response", "").strip()
            break

    return user_text, "\n\n".join(reversed(assistant_parts)).strip()


def main() -> int:
    payload = read_stdin_json()
    log(
        "windsurf_save",
        {
            "stage": "received",
            "keys": sorted(payload.keys()),
            "action": payload.get("agent_action_name"),
        },
    )
    cwd = payload.get("cwd") or payload.get("working_directory") or os.getcwd()

    transcript_path = _transcript_path(payload)
    if not transcript_path:
        log("windsurf_save", {"stage": "abort", "reason": "no transcript_path"})
        return 0

    key = api_key()
    if not key:
        log("windsurf_save", {"stage": "abort", "reason": "no api key"})
        return 0

    user_text, assistant_text = _last_turn(transcript_path)
    if not assistant_text:
        log("windsurf_save", {"stage": "abort", "reason": "no assistant text in turn"})
        return 0

    proj = resolve_project(cwd)
    if not should_save(proj["slug"]):
        log("windsurf_save", {"stage": "skip", "reason": "project not active", "slug": proj["slug"]})
        return 0

    content = (
        f"[windsurf] User asked:\n{user_text[:USER_CAP]}\n\n"
        f"Assistant response:\n{assistant_text[:ASSISTANT_CAP]}"
    )
    body = {
        "project": proj,
        "block_type": "note",
        "content": content,
        "session_id": None,
        "priority": 3,
    }
    try:
        resp = http_post("/context", body, key)
        log("windsurf_save", {"stage": "success", "resp": resp})
    except Exception as e:
        log("windsurf_save", {"stage": "error", "error": repr(e)})
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
