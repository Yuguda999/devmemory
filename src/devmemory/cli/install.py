"""devmemory install — One-command MCP setup for any AI coding tool.

Supports: Claude Code, Claude Desktop, Cursor, Windsurf, Augment, Antigravity,
Cline, Kilo Code.  Detects OS automatically and writes the correct config file.

Usage::

    devmemory install --tool cursor --api-key dm_key_...
    devmemory install --tool augment --api-key dm_key_...
    devmemory install --all --api-key dm_key_...
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path


# ── Tool Definitions ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ToolConfig:
    """Metadata for a supported AI coding tool."""

    name: str
    slug: str
    config_paths: dict[str, str]  # OS → path template (~ expanded at runtime)
    supports_env: bool = True
    supports_cwd: bool = False
    use_cli: bool = False  # Use the tool's own CLI instead of editing JSON
    cli_command: str | None = None
    has_hook: bool = False  # Supports session-start hooks
    notes: str = ""
    extra_fields: dict = field(default_factory=dict)


def _home() -> str:
    return str(Path.home())


def _appdata() -> str:
    return os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))


TOOLS: dict[str, ToolConfig] = {
    "claude-code": ToolConfig(
        name="Claude Code",
        slug="claude-code",
        config_paths={
            "Linux": "~/.claude.json",
            "Darwin": "~/.claude.json",
            "Windows": "~/.claude.json",
        },
        has_hook=True,
        notes="Wires Stop + PostToolUse hooks in ~/.claude/settings.json so context is auto-refreshed after every session and every file edit.",
    ),
    "claude-desktop": ToolConfig(
        name="Claude Desktop",
        slug="claude-desktop",
        config_paths={
            "Linux": "~/.config/Claude/claude_desktop_config.json",
            "Darwin": "~/Library/Application Support/Claude/claude_desktop_config.json",
            "Windows": "%APPDATA%/Claude/claude_desktop_config.json",
        },
    ),
    "cursor": ToolConfig(
        name="Cursor",
        slug="cursor",
        config_paths={
            "Linux": "~/.cursor/mcp.json",
            "Darwin": "~/.cursor/mcp.json",
            "Windows": "~/.cursor/mcp.json",
        },
        has_hook=True,
        notes="Writes a global ~/.cursor/rules/devmemory.mdc (alwaysApply) so every session loads DevMemory instructions.",
    ),
    "windsurf": ToolConfig(
        name="Windsurf",
        slug="windsurf",
        config_paths={
            "Linux": "~/.codeium/windsurf/mcp_config.json",
            "Darwin": "~/.codeium/windsurf/mcp_config.json",
            "Windows": "~/.codeium/windsurf/mcp_config.json",
        },
        has_hook=True,
        notes="Wires a Cascade post-hook in ~/.codeium/windsurf/hooks.json that fires after every agent message.",
    ),
    "augment": ToolConfig(
        name="Augment Code",
        slug="augment",
        config_paths={
            "Linux": "~/.augment/settings.json",
            "Darwin": "~/.augment/settings.json",
            "Windows": "%APPDATA%/augment/settings.json",
        },
        has_hook=True,
        notes="Also adds SessionStart hook for auto-inject.",
    ),
    "antigravity": ToolConfig(
        name="Antigravity (Gemini)",
        slug="antigravity",
        config_paths={
            "Linux": "~/.gemini/antigravity/mcp_config.json",
            "Darwin": "~/.gemini/antigravity/mcp_config.json",
            "Windows": "~/.gemini/antigravity/mcp_config.json",
        },
    ),
    "cline": ToolConfig(
        name="Cline (VS Code)",
        slug="cline",
        config_paths={
            "Linux": "~/.config/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json",
            "Darwin": "~/Library/Application Support/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json",
            "Windows": "%APPDATA%/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json",
        },
        has_hook=True,
        notes="Writes global ~/.clinerules so Cline auto-reads DevMemory instructions on every session.",
    ),
    "kilo": ToolConfig(
        name="Kilo Code",
        slug="kilo",
        config_paths={
            "Linux": "~/.config/kilo/kilo.jsonc",
            "Darwin": "~/.config/kilo/kilo.jsonc",
            "Windows": "~/.config/kilo/kilo.jsonc",
        },
        has_hook=True,
        notes="Uses JSONC format. Writes ~/.kilocoderules so Kilo auto-reads DevMemory instructions on every session.",
    ),
}

ALL_TOOL_SLUGS = list(TOOLS.keys())


# ── MCP Entry Builder ─────────────────────────────────────────────────────────


def _build_mcp_entry(api_key: str, host: str | None = None) -> dict:
    """Build the standard devmemory MCP server entry."""
    # Determine the command — use full path on Windows to avoid PATH issues
    devmemory_bin = shutil.which("devmemory")
    if platform.system() == "Windows":
        command = devmemory_bin or "devmemory"
    else:
        command = "devmemory"

    env: dict[str, str] = {"DEVMEMORY_API_KEY": api_key}
    if host:
        env["DEVMEMORY_HOST"] = host

    return {
        "command": command,
        "env": env,
    }


# ── Config File Operations ────────────────────────────────────────────────────


def _resolve_config_path(tool: ToolConfig) -> Path:
    """Resolve the config file path for the current OS."""
    os_name = platform.system()
    template = tool.config_paths.get(os_name)
    if template is None:
        raise RuntimeError(f"{tool.name} is not supported on {os_name}")

    path = template.replace("~", str(Path.home()))
    path = path.replace("%APPDATA%", _appdata())
    return Path(path)


def _read_json_config(path: Path) -> dict:
    """Read a JSON config file, returning empty dict if missing."""
    if not path.exists():
        return {}
    try:
        text = path.read_text(encoding="utf-8")
        # Strip JSONC comments for Kilo Code
        lines = []
        for line in text.splitlines():
            stripped = line.lstrip()
            if stripped.startswith("//"):
                continue
            lines.append(line)
        return json.loads("\n".join(lines)) if lines else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _write_json_config(path: Path, data: dict) -> None:
    """Write JSON config, creating parent dirs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _merge_mcp_server(config: dict, mcp_entry: dict) -> dict:
    """Merge devmemory MCP entry into existing config, preserving other servers."""
    if "mcpServers" not in config:
        config["mcpServers"] = {}
    config["mcpServers"]["devmemory"] = mcp_entry
    return config


# ── Augment Hook ───────────────────────────────────────────────────────────────


def _add_augment_hook(config: dict) -> dict:
    """Add devmemory-inject to Augment's SessionStart hook."""
    if "hooks" not in config:
        config["hooks"] = {}
    if "SessionStart" not in config["hooks"]:
        config["hooks"]["SessionStart"] = [{"hooks": []}]

    hook_list = config["hooks"]["SessionStart"][0].get("hooks", [])

    # Check if our hook already exists
    inject_cmd = 'devmemory inject --tool augment 2>/dev/null || true'
    for h in hook_list:
        if h.get("type") == "command" and "devmemory inject" in h.get("command", ""):
            return config  # Already installed

    hook_list.append({
        "type": "command",
        "command": inject_cmd,
    })

    config["hooks"]["SessionStart"][0]["hooks"] = hook_list
    return config


_DEVMEMORY_RULES_CONTENT = """\
# DevMemory — Persistent Dev Memory

You have access to DevMemory MCP tools. Use them proactively throughout every session:

- **SESSION START**: Call `get_context` (or `generate_resume_prompt`) to restore prior context.
- **AFTER EVERY CODE CHANGE**: Call `save_context` with block_type='code' summarising what changed.
- **AFTER EVERY KEY DECISION**: Call `save_context` with block_type='decision'.
- **ON EVERY ERROR**: Call `save_context` with block_type='error'.
- **BEFORE ENDING**: Call `save_context` with block_type='next_step' so work can resume elsewhere.

This ensures context survives when the user switches AI tools or runs out of credits.
Do NOT wait to be asked — save context automatically after every meaningful action.
"""


def _add_cursor_hook() -> Path:
    """Write a global Cursor rules file that instructs it to use DevMemory on every session.

    Cursor reads ``~/.cursor/rules/*.mdc`` globally across all projects when
    ``alwaysApply: true`` is set in the MDC frontmatter.
    """
    rules_dir = Path.home() / ".cursor" / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    path = rules_dir / "devmemory.mdc"
    content = (
        "---\n"
        "description: DevMemory persistent memory instructions — auto-generated by devmemory install.\n"
        "alwaysApply: true\n"
        "---\n"
        + _DEVMEMORY_RULES_CONTENT
    )
    path.write_text(content, encoding="utf-8")
    return path


def _add_windsurf_hook() -> Path:
    """Write DevMemory instructions to Windsurf's global memories directory.

    Windsurf reads files from ``~/.codeium/windsurf/memories/`` at session start,
    making this the equivalent of a SessionStart hook.
    """
    memories_dir = Path.home() / ".codeium" / "windsurf" / "memories"
    memories_dir.mkdir(parents=True, exist_ok=True)
    path = memories_dir / "devmemory_instructions.md"
    path.write_text(_DEVMEMORY_RULES_CONTENT, encoding="utf-8")
    return path


def _add_claude_code_hooks() -> Path:
    """Wire DevMemory hooks into Claude Code's ~/.claude/settings.json.

    Unlike MCP tools (which fire only when the AI decides), Claude Code hooks
    fire at the **OS level** unconditionally:

    * ``Stop``        — Fires every time Claude finishes a turn. Runs
                        ``devmemory inject`` so CLAUDE.md is always refreshed
                        for the next session — even if the AI forgets to save.
    * ``PostToolUse`` — Fires after every Write or Edit tool call. Appends a
                        reminder line to CLAUDE.md prompting the AI to call
                        ``save_context`` before finishing.

    Together these make DevMemory near-automatic for Claude Code users without
    relying on the AI's judgment.
    """
    settings_path = Path.home() / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    config: dict = {}
    if settings_path.exists():
        try:
            config = json.loads(settings_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            config = {}

    if "hooks" not in config:
        config["hooks"] = {}

    # ── Stop hook: refresh CLAUDE.md after every session end ──────────────────
    stop_hooks = config["hooks"].get("Stop", [])
    inject_cmd = "devmemory inject --tool claude 2>/dev/null || true"
    already_has_stop = any(
        "devmemory inject" in h.get("command", "")
        for entry in stop_hooks
        for h in entry.get("hooks", [])
    )
    if not already_has_stop:
        stop_hooks.append({
            "matcher": "",
            "hooks": [{"type": "command", "command": inject_cmd}],
        })
    config["hooks"]["Stop"] = stop_hooks

    # ── PostToolUse hook: nudge after every Write/Edit ─────────────────────────
    post_hooks = config["hooks"].get("PostToolUse", [])
    nudge_cmd = (
        "echo '<!-- devmemory: a file was just edited — "
        "call save_context to persist this change -->' "
        ">> CLAUDE.md 2>/dev/null || true"
    )
    already_has_post = any(
        "devmemory" in h.get("command", "")
        for entry in post_hooks
        for h in entry.get("hooks", [])
    )
    if not already_has_post:
        post_hooks.append({
            "matcher": "Write|Edit",
            "hooks": [{"type": "command", "command": nudge_cmd}],
        })
    config["hooks"]["PostToolUse"] = post_hooks

    settings_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return settings_path


def _add_windsurf_cascade_hook() -> Path:
    """Wire DevMemory into Windsurf's Cascade hooks.json.

    Windsurf's Cascade hooks fire at the OS level — not by AI judgment.
    We add a post-hook that runs ``devmemory inject`` after every agent
    message, ensuring context files are always fresh.
    """
    hooks_path = Path.home() / ".codeium" / "windsurf" / "hooks.json"
    hooks_path.parent.mkdir(parents=True, exist_ok=True)

    config: dict = {}
    if hooks_path.exists():
        try:
            config = json.loads(hooks_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            config = {}

    if "post" not in config:
        config["post"] = []

    inject_cmd = "devmemory inject --tool windsurf 2>/dev/null || true"
    already = any(
        "devmemory inject" in (h.get("command") or h.get("cmd") or "")
        for h in config["post"]
        if isinstance(h, dict)
    )
    if not already:
        config["post"].append({"type": "shell", "command": inject_cmd})

    hooks_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return hooks_path


def _add_cline_hook() -> Path:
    """Write global ~/.clinerules with DevMemory instructions.

    Cline auto-reads ``~/.clinerules`` at every session start — this is
    Cline's equivalent of a SessionStart hook and requires no AI decision.
    """
    path = Path.home() / ".clinerules"
    existing = ""
    if path.exists():
        existing = path.read_text(encoding="utf-8")

    if "devmemory" not in existing.lower():
        separator = "\n" if existing and not existing.endswith("\n") else ""
        path.write_text(existing + separator + _DEVMEMORY_RULES_CONTENT, encoding="utf-8")

    return path


def _add_kilo_hook() -> Path:
    """Write global ~/.kilocoderules with DevMemory instructions.

    Kilo Code auto-reads ``~/.kilocoderules`` at every session — the Kilo
    equivalent of a global SessionStart hook.
    """
    path = Path.home() / ".kilocoderules"
    existing = ""
    if path.exists():
        existing = path.read_text(encoding="utf-8")

    if "devmemory" not in existing.lower():
        separator = "\n" if existing and not existing.endswith("\n") else ""
        path.write_text(existing + separator + _DEVMEMORY_RULES_CONTENT, encoding="utf-8")

    return path


_SHELL_HOOK_BASH = """
# ── DevMemory: auto-inject context when entering a new git project ─────────────
_devmemory_check() {
  local git_root
  git_root=$(git rev-parse --show-toplevel 2>/dev/null)
  if [ -n "$git_root" ] && [ "$git_root" != "$_DEVMEMORY_LAST_ROOT" ]; then
    export _DEVMEMORY_LAST_ROOT="$git_root"
    devmemory inject 2>/dev/null &
  fi
}
PROMPT_COMMAND="${PROMPT_COMMAND:+$PROMPT_COMMAND; }_devmemory_check"
# ─────────────────────────────────────────────────────────────────────────────
"""

_SHELL_HOOK_ZSH = """
# ── DevMemory: auto-inject context when entering a new git project ─────────────
_devmemory_check() {
  local git_root
  git_root=$(git rev-parse --show-toplevel 2>/dev/null)
  if [[ -n "$git_root" && "$git_root" != "$_DEVMEMORY_LAST_ROOT" ]]; then
    export _DEVMEMORY_LAST_ROOT="$git_root"
    devmemory inject 2>/dev/null &
  fi
}
autoload -Uz add-zsh-hook
add-zsh-hook precmd _devmemory_check
# ─────────────────────────────────────────────────────────────────────────────
"""


def _add_shell_rc_hook() -> list[Path]:
    """Inject DevMemory auto-inject into ~/.bashrc and/or ~/.zshrc.

    Uses PROMPT_COMMAND (bash) and precmd hook (zsh) to call
    ``devmemory inject`` whenever the user enters a new git repo —
    regardless of which AI tool they're using.  Runs in the background
    so it never blocks the prompt.

    Returns a list of RC files that were actually modified.
    """
    written: list[Path] = []
    marker = "DevMemory: auto-inject"

    for rc_file, hook_content in [
        (Path.home() / ".bashrc", _SHELL_HOOK_BASH),
        (Path.home() / ".zshrc", _SHELL_HOOK_ZSH),
    ]:
        if not rc_file.exists():
            continue
        existing = rc_file.read_text(encoding="utf-8")
        if marker in existing:
            continue  # Already installed
        rc_file.write_text(existing.rstrip("\n") + "\n" + hook_content, encoding="utf-8")
        written.append(rc_file)

    return written


def _install_git_hooks(cwd: str | None = None) -> list[Path]:
    """Install post-checkout and post-merge git hooks in the given project.

    These hooks fire at the OS/git level — no AI judgment needed — and call
    ``devmemory inject`` after every ``git checkout`` or ``git pull/merge``.
    Works with every AI tool (Cursor, Windsurf, Cline, Kilo, etc.).

    Args:
        cwd: Project directory. Defaults to current working directory.
    """
    import subprocess

    cwd = cwd or os.getcwd()
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=cwd, capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return []
        git_dir = Path(cwd) / result.stdout.strip()
    except Exception:
        return []

    hooks_dir = git_dir / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)

    inject_script = "#!/bin/sh\ndevmemory inject 2>/dev/null || true\n"
    written: list[Path] = []

    for hook_name in ("post-checkout", "post-merge"):
        hook_path = hooks_dir / hook_name
        existing = hook_path.read_text(encoding="utf-8") if hook_path.exists() else ""
        if "devmemory inject" in existing:
            continue
        if existing and not existing.startswith("#!"):
            # Existing non-shell hook — skip to avoid breaking it
            continue
        if existing:
            # Append to existing shell hook
            hook_path.write_text(existing.rstrip("\n") + "\ndevmemory inject 2>/dev/null || true\n", encoding="utf-8")
        else:
            hook_path.write_text(inject_script, encoding="utf-8")
        if platform.system() != "Windows":
            hook_path.chmod(0o755)
        written.append(hook_path)

    return written


# ── API Key Storage ────────────────────────────────────────────────────────────


def save_api_key(api_key: str) -> Path:
    """Store the API key in ~/.devmemory/api_key with restrictive permissions."""
    dm_dir = Path.home() / ".devmemory"
    dm_dir.mkdir(parents=True, exist_ok=True)

    key_file = dm_dir / "api_key"
    key_file.write_text(api_key.strip() + "\n", encoding="utf-8")

    if platform.system() != "Windows":
        key_file.chmod(0o600)

    return key_file


def load_api_key() -> str | None:
    """Load API key from env var or ~/.devmemory/api_key."""
    key = os.environ.get("DEVMEMORY_API_KEY")
    if key:
        return key.strip()

    key_file = Path.home() / ".devmemory" / "api_key"
    if key_file.exists():
        return key_file.read_text(encoding="utf-8").strip()

    return None


# ── Main Install Logic ─────────────────────────────────────────────────────────


def install_tool(
    tool_slug: str,
    api_key: str,
    host: str | None = None,
    dry_run: bool = False,
) -> tuple[bool, str]:
    """Install DevMemory for a specific tool.

    Returns (success, message).
    """
    tool = TOOLS.get(tool_slug)
    if tool is None:
        valid = ", ".join(sorted(TOOLS.keys()))
        return False, f"Unknown tool '{tool_slug}'. Supported: {valid}"

    config_path = _resolve_config_path(tool)
    mcp_entry = _build_mcp_entry(api_key, host=host)

    if dry_run:
        snippet = json.dumps({"mcpServers": {"devmemory": mcp_entry}}, indent=2)
        return True, f"Would write to {config_path}:\n{snippet}"

    # Read existing config
    config = _read_json_config(config_path)

    # Merge MCP entry
    config = _merge_mcp_server(config, mcp_entry)

    # Add Augment hook if applicable
    if tool.has_hook and tool.slug == "augment":
        config = _add_augment_hook(config)

    # Write back
    _write_json_config(config_path, config)

    # Save API key globally
    key_path = save_api_key(api_key)

    lines = [
        f"✅ {tool.name}: DevMemory MCP installed",
        f"   Config: {config_path}",
        f"   API key saved: {key_path}",
    ]

    if tool.has_hook and tool.slug == "augment":
        lines.append("   SessionStart hook: added (auto-inject on startup)")

    if tool.has_hook and tool.slug == "cursor":
        hook_path = _add_cursor_hook()
        lines.append(f"   Global rules hook: written to {hook_path}")
        lines.append("   Cursor will load DevMemory instructions on every session automatically.")

    if tool.has_hook and tool.slug == "windsurf":
        # Global memories (rules-based)
        mem_path = _add_windsurf_hook()
        lines.append(f"   Global memories hook: written to {mem_path}")
        # Cascade OS-level post-hook
        cascade_path = _add_windsurf_cascade_hook()
        lines.append(f"   Cascade post-hook: written to {cascade_path} (fires after every agent message).")

    if tool.has_hook and tool.slug == "claude-code":
        hook_path = _add_claude_code_hooks()
        lines.append(f"   OS-level hooks: written to {hook_path}")
        lines.append("   Stop hook: refreshes CLAUDE.md after every session (unconditional, not AI-driven).")
        lines.append("   PostToolUse hook: nudges save_context after every Write/Edit.")

    if tool.has_hook and tool.slug == "cline":
        cline_path = _add_cline_hook()
        lines.append(f"   Global .clinerules: written to {cline_path} (auto-read every session).")

    if tool.has_hook and tool.slug == "kilo":
        kilo_path = _add_kilo_hook()
        lines.append(f"   Global .kilocoderules: written to {kilo_path} (auto-read every session).")

    # Universal: shell RC hook (works for ALL tools regardless of native support)
    rc_files = _add_shell_rc_hook()
    if rc_files:
        for rc in rc_files:
            lines.append(f"   Shell hook: added to {rc} (auto-injects on git repo entry for any tool).")
        lines.append("   Run: source ~/.bashrc  (or restart your terminal) to activate.")

    # Universal: git hooks for project-level automation
    git_hook_paths = _install_git_hooks()
    if git_hook_paths:
        lines.append(f"   Git hooks: installed post-checkout + post-merge in {git_hook_paths[0].parent}")

    if tool.notes:
        lines.append(f"   💡 {tool.notes}")

    return True, "\n".join(lines)


def install_all(api_key: str, host: str | None = None) -> str:
    """Install DevMemory for all detected tools."""
    results = []
    for slug in ALL_TOOL_SLUGS:
        tool = TOOLS[slug]
        try:
            config_path = _resolve_config_path(tool)
            # Only install for tools whose config dir already exists
            # (i.e., the tool is actually installed on this machine)
            if config_path.parent.exists() or slug in ("claude-code",):
                ok, msg = install_tool(slug, api_key, host=host)
                results.append(msg)
        except RuntimeError:
            continue

    if not results:
        return "⚠️  No supported AI tools detected. Install a tool first, then run this again."

    return "\n\n".join(results)


# ── CLI Entry Point ────────────────────────────────────────────────────────────


def run_install(args) -> None:
    """Handle the 'devmemory install' subcommand."""
    api_key = args.api_key or load_api_key()
    if not api_key:
        print("❌ API key required. Use --api-key or set DEVMEMORY_API_KEY", file=sys.stderr)
        sys.exit(1)

    host = args.host if hasattr(args, "host") else None

    if args.tool == "all":
        result = install_all(api_key, host=host)
    else:
        ok, result = install_tool(args.tool, api_key, host=host, dry_run=args.dry_run)
        if not ok:
            print(f"❌ {result}", file=sys.stderr)
            sys.exit(1)

    print(result)
    print("\n🎉 Setup complete! Restart your AI tool to activate DevMemory.")
