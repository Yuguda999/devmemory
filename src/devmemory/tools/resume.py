"""Resume prompt generator.

Assembles a list of context blocks into a structured, tool-optimized
continuation prompt.  This is a **pure function** — no DB access required.

Block types are rendered in a fixed priority order that matches how an AI tool
should consume context when picking up work:

    goal → decision → code → error → next_step → note → (unknown)

Within each group, blocks are assumed to be pre-sorted by ``priority DESC,
created_at ASC`` (as returned by :func:`devmemory.db.repository.get_context_blocks`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from devmemory.models.context import ContextBlock


# ── Section metadata ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class _Section:
    block_type: str
    heading: str
    intro: str


_SECTIONS: list[_Section] = [
    _Section("goal",      "🎯 Goals",         "The objectives for this session:"),
    _Section("decision",  "🧩 Key Decisions", "Decisions made that shape the implementation:"),
    _Section("code",      "💻 Code Context",  "Relevant code snippets and implementation details:"),
    _Section("error",     "🐛 Known Errors",  "Errors encountered (may still be open):"),
    _Section("next_step", "👣 Next Steps",    "What to work on next, in order:"),
    _Section("task",      "✅ Tasks",         "Task checklist:"),
    _Section("note",      "📝 Notes",         "Additional context and notes:"),
]

_SECTION_ORDER: dict[str, int] = {s.block_type: i for i, s in enumerate(_SECTIONS)}


# ── Tool-specific preambles ────────────────────────────────────────────────────

_PREAMBLES: dict[str, str] = {
    "claude": (
        "You are resuming a development session. "
        "All context below was saved by a previous AI-assisted coding session. "
        "Use it to continue seamlessly without re-asking the user what they were working on."
    ),
    "cursor": (
        "Resuming previous work. "
        "The following context was saved from your last Cursor session — "
        "pick up exactly where you left off."
    ),
    "windsurf": (
        "Resuming development session. "
        "Context below was persisted by DevMemory. "
        "Continue from the next steps listed."
    ),
    "generic": (
        "The following context was saved from a previous development session. "
        "Use it to continue work without losing momentum."
    ),
}


# ── Public API ─────────────────────────────────────────────────────────────────


def generate_resume_prompt(
    project_name: str,
    session_title: str,
    blocks: list["ContextBlock"],
    target_tool: str = "generic",
    session_id: str | None = None,
) -> str:
    """Assemble context blocks into a structured resume prompt.

    Args:
        project_name: Display name of the project.
        session_title: Human-readable session title.
        blocks: Context blocks, ordered by priority DESC then created_at ASC.
        target_tool: One of ``claude``, ``cursor``, ``windsurf``, or ``generic``.
        session_id: Optional session ID to embed for cross-tool continuity.

    Returns:
        A formatted multi-line string ready to be pasted into an AI tool.
    """
    preamble = _PREAMBLES.get(target_tool.lower(), _PREAMBLES["generic"])

    grouped: dict[str, list["ContextBlock"]] = {}
    unknown: list["ContextBlock"] = []

    for block in blocks:
        bt = (block.block_type or "").lower()
        if bt in _SECTION_ORDER:
            grouped.setdefault(bt, []).append(block)
        else:
            unknown.append(block)

    lines: list[str] = [
        preamble,
        "",
        f"## Project: {project_name}",
        f"## Session: {session_title}",
    ]
    if session_id:
        lines.append(f"## DevMemory Session ID: {session_id}")
        lines.append(
            "> Pass this session_id to DevMemory tools "
            "(e.g. `save_context(session_id=\"{session_id}\")`) "
            "to continue this exact session."
        )
    lines.append("")

    # Render known sections in canonical order
    for section in _SECTIONS:
        items = grouped.get(section.block_type)
        if not items:
            continue
        lines.append(f"### {section.heading}")
        lines.append(section.intro)
        for block in items:
            content = block.content
            if section.block_type == "task":
                status = block.extra_metadata.get("status", "pending")
                marker = "[ ]"
                if status == "in_progress": marker = "[/]"
                elif status == "done": marker = "[x]"
                elif status == "skipped": marker = "[-]"
                indented = "\n".join(f"  {l}" for l in content.splitlines())
                lines.append(f"- {marker} {indented.lstrip()}")
            else:
                indented = "\n".join(f"  {l}" for l in content.splitlines())
                lines.append(f"- {indented.lstrip()}")
        lines.append("")

    # Append any unrecognised block types at the end
    if unknown:
        lines.append("### Additional Context")
        for block in unknown:
            lines.append(f"- {block.content}")
        lines.append("")

    if not grouped and not unknown:
        lines.append("_No context blocks have been saved for this session yet._")
        lines.append("")

    lines.append(
        "---\n"
        "_Context provided by [DevMemory](https://devmemory.io) — "
        "Universal Dev Memory for AI coding tools._"
    )

    return "\n".join(lines)
