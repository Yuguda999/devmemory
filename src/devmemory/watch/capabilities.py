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
    ToolSupport(
        "claude-code",
        "supported",
        "SessionStart + Stop hooks (transcript); watch daemon over ~/.claude/projects as fallback.",
    ),
    ToolSupport("windsurf", "supported", "post_cascade_response_with_transcript hook (JSONL)."),
]

# Tools driven by the MCP tools + an always-on global rules file (agent-driven,
# not deterministic). Used where the IDE exposes no verified per-turn hook AND
# there's no tailable local store — the watch daemon cannot save these.
RULES_TOOLS = [
    ToolSupport("antigravity", "supported", "MCP tools + ~/.gemini/GEMINI.md global rules."),
    ToolSupport("claude-desktop", "supported", "MCP tools only — save/recall on demand in chat."),
]

# Tools captured by the watch DAEMON tailing their local store (no hook exists).
WATCH_TOOLS = [
    ToolSupport("claude-code", "supported", "~/.claude/projects/*/*.jsonl transcripts (hook fallback)."),
    ToolSupport("cursor", "supported", "SQLite store (cursorDiskKV) — verified."),
    ToolSupport("cline", "supported", "JSON task history (api_conversation_history.json)."),
    ToolSupport("kilo", "supported", "Cline fork — same JSON format, different extension id."),
    ToolSupport("codex", "supported", "state_*.sqlite threads + rollout JSONL."),
    ToolSupport("<generic>", "supported", "Any JSONL store via ~/.devmemory/watch_adapters.json."),
]


# Save mode for the attach model (`devmemory start` / `continue`), by tool slug.
#   "auto"  — a SAVE hook or the watch daemon persists the attached project with
#             no further action: claude-code / cursor / cline / kilo / codex
#             (daemon) and windsurf (its transcript hook saves each turn).
#   "mcp"   — no save hook and no tailable store; saving happens ONLY when the
#             agent calls save_context / continue_here in-chat: antigravity,
#             claude-desktop, and augment (its only hook is SessionStart =
#             restore, not save). The daemon cannot auto-save these.
#   "unknown" — tool not passed / not recognised.
_AUTO_TOOLS = {"claude-code", "cursor", "cline", "kilo", "codex", "windsurf"}
_MCP_TOOLS = {"antigravity", "claude-desktop", "augment"}


def save_mode(tool: str | None) -> str:
    if tool in _AUTO_TOOLS:
        return "auto"
    if tool in _MCP_TOOLS:
        return "mcp"
    return "unknown"


def render_status() -> str:
    """Human-readable support + presence report for `devmemory watch --list`."""
    present = {a.name for a in available_adapters()}
    lines = ["DevMemory — deterministic auto-save support:\n"]

    lines.append("Hook-based (the tool fires a hook, no daemon needed):")
    for t in HOOK_TOOLS:
        lines.append(f"  {t.name:<12} [installed by `devmemory install`] {t.detail}")

    lines.append("\nMCP + rules (agent-driven; no verified per-turn hook):")
    for t in RULES_TOOLS:
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
        "\nNote: Windsurf/Antigravity conversations are encrypted on disk. Windsurf is"
        "\ncaptured via the plaintext transcript its hook provides; Antigravity has no"
        "\nverified per-turn hook, so it saves/restores through the MCP tools + rules."
    )
    return "\n".join(lines)
