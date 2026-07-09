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


# Tools with a real adapter (may or may not be installed on this machine).
SUPPORTED = [
    ToolSupport("cursor", "supported", "SQLite store (cursorDiskKV) — verified."),
    ToolSupport("cline", "supported", "JSON task history (api_conversation_history.json)."),
    ToolSupport("kilo", "supported", "Cline fork — same JSON format, different extension id."),
    ToolSupport("codex", "supported", "state_*.sqlite threads + rollout JSONL."),
    ToolSupport("<generic>", "supported", "Any JSONL store via ~/.devmemory/watch_adapters.json."),
]

# Known tools we deliberately do NOT fake support for.
NOT_SUPPORTED = [
    ToolSupport(
        "windsurf",
        "pending",
        "Cascade conversations live in a local Codeium store whose format isn't "
        "reversed yet. Restore works via the install-time hook; auto-save pending.",
    ),
    ToolSupport(
        "antigravity",
        "unsupported",
        "Conversations are opaque/compressed protobuf (~/.gemini/antigravity/"
        "conversations/*.pb) with no public schema — not parseable yet. Use a "
        "generic adapter if a JSONL export becomes available.",
    ),
]


def render_status() -> str:
    """Human-readable support + presence report for `devmemory watch --list`."""
    present = {a.name for a in available_adapters()}
    lines = ["DevMemory watch — tool support:\n"]

    lines.append("Supported (adapter exists):")
    for t in SUPPORTED:
        mark = "● found" if t.name in present else "○ not on this machine"
        lines.append(f"  {t.name:<12} [{mark}] {t.detail}")

    # Any generic adapters actually configured show up in `present` by their name.
    extra = present - {t.name for t in SUPPORTED} - {"<generic>"}
    if extra:
        lines.append("\nConfigured generic adapters (found):")
        for name in sorted(extra):
            lines.append(f"  {name}")

    lines.append("\nNot yet auto-saved:")
    for t in NOT_SUPPORTED:
        lines.append(f"  {t.name:<12} [{t.status}] {t.detail}")

    return "\n".join(lines)
