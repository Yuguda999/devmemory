"""What the watch daemon can and can't do, per tool — reported by `watch --list`.

Honesty matters here: DevMemory's whole point is not lying about what persists.
Tools we can't yet auto-save are listed explicitly with the reason, rather than
shipped as adapters that silently capture nothing.
"""

from __future__ import annotations

from dataclasses import dataclass

from devmemory.watch.adapters import available_adapters


@dataclass(frozen=True)
class ToolSupport:
    name: str
    status: str  # "supported" | "pending" | "unsupported"
    detail: str


# Tools captured by a HOOK the tool itself fires (transcript handed to us).
# Deterministic, no watch daemon, no reading an encrypted store.
HOOK_TOOLS = [
    ToolSupport("claude-code", "supported", "SessionStart + Stop hooks (transcript)."),
    ToolSupport("windsurf", "supported", "post_cascade_response_with_transcript hook (JSONL)."),
    ToolSupport("antigravity", "supported", "PostInvocation + Stop agent hooks (transcript_path)."),
]

# Tools captured by the watch DAEMON tailing their local store (no hook exists).
WATCH_TOOLS = [
    ToolSupport("cursor", "supported", "SQLite store (cursorDiskKV) — verified."),
    ToolSupport("cline", "supported", "JSON task history (api_conversation_history.json)."),
    ToolSupport("kilo", "supported", "Cline fork — same JSON format, different extension id."),
    ToolSupport("codex", "supported", "state_*.sqlite threads + rollout JSONL."),
    ToolSupport("<generic>", "supported", "Any JSONL store via ~/.devmemory/watch_adapters.json."),
]


def render_status() -> str:
    """Human-readable support + presence report for `devmemory watch --list`."""
    present = {a.name for a in available_adapters()}
    lines = ["DevMemory — deterministic auto-save support:\n"]

    lines.append("Hook-based (the tool fires a hook, no daemon needed):")
    for t in HOOK_TOOLS:
        lines.append(f"  {t.name:<12} [installed by `devmemory install`] {t.detail}")

    lines.append("\nWatch-daemon (tails the tool's local store — needs `devmemory watch`):")
    for t in WATCH_TOOLS:
        mark = "● found" if t.name in present else "○ not on this machine"
        lines.append(f"  {t.name:<12} [{mark}] {t.detail}")

    extra = present - {t.name for t in WATCH_TOOLS} - {"<generic>"}
    if extra:
        lines.append("\nConfigured generic adapters (found):")
        for name in sorted(extra):
            lines.append(f"  {name}")

    lines.append(
        "\nNote: Windsurf/Antigravity conversations are encrypted on disk; we capture"
        "\nthem via the plaintext transcript their hook provides, not by reading the store."
    )
    return "\n".join(lines)
