"""Unit tests for the resume prompt generator.

Pure-function tests — no DB required.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# ── Minimal stub for ContextBlock ──────────────────────────────────────────────


@dataclass
class _Block:
    """Lightweight stand-in for devmemory.models.context.ContextBlock."""

    block_type: str
    content: str
    priority: int = 5
    id: str = "stub-id"
    created_at: Any = None


# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_blocks(*specs: tuple[str, str]) -> list[_Block]:
    """Create a list of stub blocks from (block_type, content) tuples."""
    return [_Block(block_type=bt, content=c) for bt, c in specs]


from devmemory.tools.resume import generate_resume_prompt  # noqa: E402

# ── Tests ──────────────────────────────────────────────────────────────────────


class TestGenerateResumePrompt:
    def test_empty_blocks_shows_placeholder(self):
        prompt = generate_resume_prompt("myproject", "My Session", [], target_tool="generic")
        assert "_No context blocks have been saved" in prompt
        assert "myproject" in prompt
        assert "My Session" in prompt

    def test_single_goal_appears_in_output(self):
        blocks = _make_blocks(("goal", "Implement MCP tools layer"))
        prompt = generate_resume_prompt("devmemory", "Phase 2", blocks)
        assert "🎯 Goals" in prompt
        assert "Implement MCP tools layer" in prompt

    def test_section_order_goals_before_next_steps(self):
        blocks = _make_blocks(
            ("next_step", "Write tests"),
            ("goal", "Finish tools layer"),
        )
        prompt = generate_resume_prompt("proj", "session", blocks)
        goals_pos = prompt.index("🎯 Goals")
        nextstep_pos = prompt.index("👣 Next Steps")
        assert goals_pos < nextstep_pos, "Goals section must appear before Next Steps"

    def test_section_order_decisions_before_errors(self):
        blocks = _make_blocks(
            ("error", "NullPointerException on line 42"),
            ("decision", "Use SQLAlchemy async"),
        )
        prompt = generate_resume_prompt("proj", "session", blocks)
        decision_pos = prompt.index("🧩 Key Decisions")
        error_pos = prompt.index("🐛 Known Errors")
        assert decision_pos < error_pos

    async def test_api_key_from_env_var(self, monkeypatch):
        """_pick_key should use env var when no arg is given."""
        monkeypatch.setenv("DEVMEMORY_API_KEY", "dm_key_from_env")
        from devmemory.auth.mcp_auth import _pick_key

        # The env var path should return the env key when arg is absent
        assert _pick_key(None) == "dm_key_from_env"

    def test_all_block_types_rendered(self):
        blocks = _make_blocks(
            ("goal", "G"),
            ("decision", "D"),
            ("code", "C"),
            ("error", "E"),
            ("next_step", "N"),
            ("note", "X"),
        )
        prompt = generate_resume_prompt("proj", "s", blocks)
        for heading in [
            "🎯 Goals",
            "🧩 Key Decisions",
            "💻 Code Context",
            "🐛 Known Errors",
            "👣 Next Steps",
            "📝 Notes",
        ]:
            assert heading in prompt, f"Missing section: {heading}"

    def test_unknown_block_type_goes_to_additional_context(self):
        blocks = _make_blocks(("mystery_type", "some content"))
        prompt = generate_resume_prompt("proj", "s", blocks)
        assert "Additional Context" in prompt
        assert "some content" in prompt

    def test_empty_sections_not_rendered(self):
        blocks = _make_blocks(("goal", "Only goals here"))
        prompt = generate_resume_prompt("proj", "s", blocks)
        assert "👣 Next Steps" not in prompt
        assert "🐛 Known Errors" not in prompt

    def test_claude_preamble(self):
        prompt = generate_resume_prompt("proj", "s", [], target_tool="claude")
        assert "resuming a development session" in prompt.lower()

    def test_cursor_preamble(self):
        prompt = generate_resume_prompt("proj", "s", [], target_tool="cursor")
        assert "cursor" in prompt.lower()

    def test_windsurf_preamble(self):
        prompt = generate_resume_prompt("proj", "s", [], target_tool="windsurf")
        # Windsurf preamble says "Resuming development session"
        assert "resuming development session" in prompt.lower()

    def test_unknown_tool_falls_back_to_generic(self):
        prompt = generate_resume_prompt("proj", "s", [], target_tool="some_new_tool")
        # Should not raise, and should contain the generic preamble text
        assert "previous development session" in prompt

    def test_devmemory_footer_present(self):
        prompt = generate_resume_prompt("proj", "s", [])
        assert "DevMemory" in prompt

    def test_multiline_content_indented(self):
        content = "line one\nline two\nline three"
        blocks = _make_blocks(("note", content))
        prompt = generate_resume_prompt("proj", "s", blocks)
        # All content lines must appear
        for line in ["line one", "line two", "line three"]:
            assert line in prompt

    def test_project_and_session_in_header(self):
        prompt = generate_resume_prompt("my-proj", "My Great Session", [])
        assert "## Project: my-proj" in prompt
        assert "## Session: My Great Session" in prompt

    def test_multiple_blocks_same_type_all_rendered(self):
        blocks = _make_blocks(
            ("next_step", "Step A"),
            ("next_step", "Step B"),
            ("next_step", "Step C"),
        )
        prompt = generate_resume_prompt("proj", "s", blocks)
        assert "Step A" in prompt
        assert "Step B" in prompt
        assert "Step C" in prompt

    def test_session_id_embedded_in_prompt(self):
        prompt = generate_resume_prompt("proj", "My Session", [], session_id="abc-123-def")
        assert "## DevMemory Session ID: abc-123-def" in prompt
        assert "save_context" in prompt  # usage hint present

    def test_session_id_none_omits_line(self):
        prompt = generate_resume_prompt("proj", "My Session", [], session_id=None)
        assert "DevMemory Session ID" not in prompt
