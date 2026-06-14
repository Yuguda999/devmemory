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
        notes="Also supports: claude mcp add devmemory ...",
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
    ),
    "windsurf": ToolConfig(
        name="Windsurf",
        slug="windsurf",
        config_paths={
            "Linux": "~/.codeium/windsurf/mcp_config.json",
            "Darwin": "~/.codeium/windsurf/mcp_config.json",
            "Windows": "~/.codeium/windsurf/mcp_config.json",
        },
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
    ),
    "kilo": ToolConfig(
        name="Kilo Code",
        slug="kilo",
        config_paths={
            "Linux": "~/.config/kilo/kilo.jsonc",
            "Darwin": "~/.config/kilo/kilo.jsonc",
            "Windows": "~/.config/kilo/kilo.jsonc",
        },
        notes="Uses JSONC format (comments allowed).",
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
    if tool.has_hook:
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

    if tool.has_hook:
        lines.append("   SessionStart hook: added (auto-inject on startup)")

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
