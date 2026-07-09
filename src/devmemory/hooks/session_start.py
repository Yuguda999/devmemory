#!/usr/bin/env python3
"""DevMemory SessionStart hook — auto-restore prior context (hosted-correct).

Resolves the project slug LOCALLY (git remote → slug, same as the MCP client),
finds the latest active session for it, and injects that session's resume
prompt via ``hookSpecificOutput.additionalContext``. Does NOT touch CLAUDE.md
or any project file. Always exits 0 so a DevMemory outage never blocks startup.

Uses the client-side-slug endpoints (/sessions, /sessions/{id}/resume) rather
than /context/resume, whose server-side git resolution is wrong on a hosted
server that cannot see the local repo.
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import api_key, http_get, log, read_stdin_json, resolve_project  # noqa: E402


def emit(additional_context: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": additional_context,
                }
            }
        )
    )


PRIMER = (
    "## DevMemory active — no prior context for this project yet.\n"
    "This session's work is being persisted automatically (a Stop hook "
    "snapshots each turn). You may also call mcp__devmemory__save_context "
    "with block_type='goal' now to record the objective."
)


def main() -> int:
    payload = read_stdin_json()
    log(
        "session_start",
        {
            "stage": "received",
            "payload_keys": sorted(payload.keys()),
            "cwd_arg": payload.get("cwd"),
        },
    )
    cwd = payload.get("cwd") or os.getcwd()

    key = api_key()
    if not key:
        return 0

    proj = resolve_project(cwd)
    try:
        sessions = http_get(
            "/sessions",
            {"project_slug": proj["slug"], "status": "active", "limit": 1},
            key,
        ).get("sessions", [])
    except Exception:
        return 0  # backend down — never block startup

    if not sessions:
        emit(PRIMER)
        return 0

    session_id = sessions[0]["id"]
    try:
        data = http_get(f"/sessions/{session_id}/resume", {"target_tool": "claude"}, key)
    except Exception:
        return 0

    if data.get("prompt"):
        header = (
            "## DevMemory — restored context\n"
            "Prior work on this project, loaded automatically. Continue from here. "
            "To keep adding to THIS session, pass "
            f'session_id="{session_id}" to mcp__devmemory__save_context. '
            "(A Stop hook also snapshots each turn as a safety net.)\n\n"
        )
        emit(header + data["prompt"])
    else:
        emit(PRIMER)
    return 0


if __name__ == "__main__":
    sys.exit(main())
