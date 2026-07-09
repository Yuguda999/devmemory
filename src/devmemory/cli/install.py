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
        notes="MCP-only: save/restore runs through the MCP tools; no CLAUDE.md file hooks.",
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
        has_hook=True,
        notes="Wires PostInvocation + Stop agent hooks (~/.gemini/antigravity-cli/hooks.json) for deterministic auto-save.",
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


def _build_mcp_entry(api_key: str, client: str | None = None, host: str | None = None) -> dict:
    """Build the standard devmemory MCP server entry.

    Args:
        api_key: The DevMemory API key to embed.
        client:  Tool slug recorded as ``DEVMEMORY_CLIENT`` so the MCP heartbeat
                 can attribute connections to the right tool in the dashboard.
        host:    Optional REST host override.
    """
    # Always prefer the absolute path to the installed binary. AI tools launch
    # the MCP server with their own PATH (not the user's interactive shell PATH),
    # so a bare "devmemory" only resolves when it happens to be on that PATH —
    # producing intermittent "failed to connect" errors. Resolving the full path
    # at install time makes the config work regardless of how the tool is launched.
    command = shutil.which("devmemory") or "devmemory"

    env: dict[str, str] = {"DEVMEMORY_API_KEY": api_key}
    if client:
        env["DEVMEMORY_CLIENT"] = client
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
    inject_cmd = "devmemory inject --tool augment 2>/dev/null || true"
    for h in hook_list:
        if h.get("type") == "command" and "devmemory inject" in h.get("command", ""):
            return config  # Already installed

    hook_list.append(
        {
            "type": "command",
            "command": inject_cmd,
        }
    )

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
        "---\n" + _DEVMEMORY_RULES_CONTENT
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


# ── Transcript-based hooks (OS-level, no AI judgment) ───────────────────────────

# Tools without a per-turn transcript hook — they need the watch daemon.
_WATCH_TOOLS = {"cursor", "cline", "kilo"}


def _package_hooks_dir() -> Path:
    """Directory holding the shipped hook scripts (src/devmemory/hooks)."""
    return Path(__file__).resolve().parent.parent / "hooks"


def _copy_hook_scripts() -> Path:
    """Copy ALL shipped hook scripts into ~/.devmemory/hooks/ and return the dir.

    Always overwrites so an upgrade picks up fixes. Scripts are stdlib-only and
    run under the tool's own ``python3``, so they don't depend on the installed
    devmemory package. One copy serves every tool's hook (Claude Code, Windsurf,
    Antigravity) since they share ``_common.py``.
    """
    src = _package_hooks_dir()
    dst = Path.home() / ".devmemory" / "hooks"
    dst.mkdir(parents=True, exist_ok=True)
    for s in src.glob("*.py"):
        if s.name == "__init__.py":
            continue
        shutil.copyfile(s, dst / s.name)
    return dst


def _add_claude_code_hooks(hooks_dir: Path) -> Path:
    """Merge DevMemory SessionStart + Stop hooks into ~/.claude/settings.json.

    Idempotent and non-destructive: preserves any existing hooks (other tools',
    user's own) and only adds a DevMemory command if one isn't already present.

    - SessionStart → session_start.py injects restored context on startup.
    - Stop         → stop_save.py snapshots each turn (runs regardless of whether
                     the model called save_context, so nothing is ever lost).
    """
    settings_path = Path.home() / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    config: dict = {}
    if settings_path.exists():
        try:
            config = json.loads(settings_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            config = {}

    hooks = config.setdefault("hooks", {})

    def _already(event: str, marker: str) -> bool:
        for group in hooks.get(event, []):
            if not isinstance(group, dict):
                continue
            for h in group.get("hooks", []):
                if marker in (h.get("command") or ""):
                    return True
        return False

    if not _already("SessionStart", "session_start.py"):
        hooks.setdefault("SessionStart", []).append(
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": f'python3 "{hooks_dir / "session_start.py"}"',
                        "timeout": 15,
                        "statusMessage": "DevMemory: restoring context",
                    }
                ]
            }
        )

    if not _already("Stop", "stop_save.py"):
        hooks.setdefault("Stop", []).append(
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": f'python3 "{hooks_dir / "stop_save.py"}"',
                        "timeout": 20,
                        "async": True,
                        "statusMessage": "DevMemory: saving turn",
                    }
                ]
            }
        )

    settings_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return settings_path


def _add_windsurf_transcript_hook(hooks_dir: Path) -> Path:
    """Wire windsurf_save.py into Windsurf's post_cascade_response_with_transcript.

    That hook fires after every Cascade response and writes the full conversation
    to a JSONL file, handing us its path on stdin — so we capture each turn
    deterministically without touching Windsurf's encrypted conversation store.
    Idempotent; preserves any other hooks in the file.
    """
    hooks_path = Path.home() / ".codeium" / "windsurf" / "hooks.json"
    hooks_path.parent.mkdir(parents=True, exist_ok=True)

    config: dict = {}
    if hooks_path.exists():
        try:
            config = json.loads(hooks_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            config = {}

    hooks = config.setdefault("hooks", {})
    event = hooks.setdefault("post_cascade_response_with_transcript", [])
    marker = "windsurf_save.py"
    if not any(marker in (h.get("command") or "") for h in event if isinstance(h, dict)):
        event.append(
            {
                "command": f'python3 "{hooks_dir / "windsurf_save.py"}"',
                "show_output": False,
            }
        )

    hooks_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return hooks_path


def _add_antigravity_hook(hooks_dir: Path) -> Path:
    """Wire antigravity_save.py into Antigravity's agent hooks.

    Uses ``PostInvocation`` (after each agent invocation) + ``Stop`` so a turn is
    captured even if the session ends abruptly. Antigravity pipes a HookInput
    JSON (with a plaintext ``transcript_path``) to the command on stdin.
    Idempotent; preserves other hook groups.
    """
    hooks_path = Path.home() / ".gemini" / "antigravity-cli" / "hooks.json"
    hooks_path.parent.mkdir(parents=True, exist_ok=True)

    config: dict = {}
    if hooks_path.exists():
        try:
            config = json.loads(hooks_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            config = {}

    group = config.setdefault("devmemory-save", {})
    command = f'python3 "{hooks_dir / "antigravity_save.py"}"'
    for event in ("PostInvocation", "Stop"):
        entries = group.setdefault(event, [])
        already = any(
            command in (h.get("command") or "")
            for entry in entries
            if isinstance(entry, dict)
            for h in entry.get("hooks", [])
        )
        if not already:
            entries.append({"hooks": [{"type": "command", "command": command, "timeout": 20}]})

    hooks_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return hooks_path


# ── API Key Storage ────────────────────────────────────────────────────────────


def ensure_global_env() -> Path | None:
    """Write DevMemory's DB + deployment config to ``~/.devmemory/.env``.

    This is the single source of truth read by BOTH the MCP server (which each
    AI tool launches with *its own* working directory) and the REST/dashboard
    server. Anchoring config to a fixed absolute path is what stops the MCP
    server from silently falling back to a per-project SQLite file — the bug
    where ``save_context`` looks like it worked but nothing reaches the
    dashboard because the key only exists in the REST server's database.

    Idempotent: if the file already defines ``DEVMEMORY_DATABASE_URL`` we leave
    it untouched so a hand-edited config is never clobbered.
    """
    from devmemory.config import settings

    env_path = Path.home() / ".devmemory" / ".env"
    env_path.parent.mkdir(parents=True, exist_ok=True)

    existing = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    if "DEVMEMORY_DATABASE_URL" in existing:
        return None  # already configured — respect it

    block = (
        "# DevMemory global runtime config (single source of truth) — written by\n"
        "# `devmemory install`. Read by the MCP server (any working directory) and\n"
        "# the REST/dashboard server so they always resolve the SAME database.\n"
        f"DEVMEMORY_DEPLOYMENT_MODE={settings.deployment_mode.value}\n"
        f"DEVMEMORY_DATABASE_URL={settings.database_url}\n"
    )
    sep = "" if not existing or existing.endswith("\n") else "\n"
    env_path.write_text(existing + sep + block, encoding="utf-8")
    return env_path


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
    mcp_entry = _build_mcp_entry(api_key, client=tool.slug, host=host)

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

    # Pin DB/deployment config to a fixed path so the MCP server (launched with
    # each tool's own CWD) and the REST server always share one database.
    global_env_path = ensure_global_env()

    lines = [
        f"✅ {tool.name}: DevMemory MCP installed",
        f"   Config: {config_path}",
        f"   API key saved: {key_path}",
    ]
    if global_env_path:
        lines.append(f"   Global runtime config: {global_env_path} (shared DB for MCP + dashboard)")

    if tool.has_hook and tool.slug == "augment":
        lines.append("   SessionStart hook: added (auto-inject on startup)")

    if tool.has_hook and tool.slug == "cursor":
        hook_path = _add_cursor_hook()
        lines.append(f"   Global rules hook: written to {hook_path}")
        lines.append("   Cursor will load DevMemory instructions on every session automatically.")

    if tool.has_hook and tool.slug == "windsurf":
        # Restore: global memories (rules-based).
        mem_path = _add_windsurf_hook()
        lines.append(f"   Global memories hook: written to {mem_path}")
        # Save: post_cascade_response_with_transcript hook → reads the JSONL
        # transcript Windsurf writes per response and POSTs the turn (no reliance
        # on the model, no need to read Windsurf's encrypted conversation store).
        hooks_dir = _copy_hook_scripts()
        cascade_path = _add_windsurf_transcript_hook(hooks_dir)
        lines.append(f"   Cascade transcript hook: wired into {cascade_path}")
        lines.append("   Each Cascade turn is saved automatically — no manual save_context needed.")

    if tool.has_hook and tool.slug == "claude-code":
        # OS-level hooks (no AI judgment) drive save/restore. These do NOT touch
        # CLAUDE.md — the old CLAUDE.md hooks spammed the file on every edit and
        # clobbered it on Stop. Instead: SessionStart injects context via
        # hookSpecificOutput.additionalContext, and Stop POSTs each turn to the
        # API so nothing is lost even when the model never calls save_context.
        hooks_dir = _copy_hook_scripts()
        settings_path = _add_claude_code_hooks(hooks_dir)
        lines.append(f"   Hook scripts: {hooks_dir}")
        lines.append(f"   SessionStart + Stop hooks: wired into {settings_path}")
        lines.append(
            "   Context saves/restores automatically every turn — no manual save_context needed."
        )

    if tool.has_hook and tool.slug == "cline":
        cline_path = _add_cline_hook()
        lines.append(f"   Global .clinerules: written to {cline_path} (auto-read every session).")

    if tool.has_hook and tool.slug == "kilo":
        kilo_path = _add_kilo_hook()
        lines.append(f"   Global .kilocoderules: written to {kilo_path} (auto-read every session).")

    if tool.has_hook and tool.slug == "antigravity":
        # Agent hooks (PostInvocation + Stop) hand us a plaintext transcript_path
        # on stdin, so we capture each turn without touching the encrypted .pb
        # conversation store.
        hooks_dir = _copy_hook_scripts()
        ag_path = _add_antigravity_hook(hooks_dir)
        lines.append(f"   Agent hooks: wired into {ag_path}")
        lines.append("   Each turn is saved automatically — no manual save_context needed.")

    # Tools with no per-turn transcript hook rely on the watch daemon to
    # auto-save. Installing it once starts a background service that covers
    # every supported local store (Cursor/Cline/Kilo/Codex + generic).
    if tool.slug in _WATCH_TOOLS:
        from devmemory.watch.service import install_service

        ok, msg = install_service(host=host)
        lines.append(f"   Auto-save daemon: {msg}" if ok else f"   ⚠️  watch service: {msg}")

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
