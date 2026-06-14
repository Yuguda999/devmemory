# DevMemory

**Universal Dev Memory** — A persistent MCP server that stores, structures, and serves coding context so any AI tool can continue seamlessly.

[![PyPI](https://img.shields.io/pypi/v/devmemory)](https://pypi.org/project/devmemory/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://pypi.org/project/devmemory/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CI](https://github.com/Yuguda999/devmemory/actions/workflows/ci.yml/badge.svg)](https://github.com/Yuguda999/devmemory/actions/workflows/ci.yml)

---

## The Problem

Every time you switch AI coding tools — Cursor → Claude → Windsurf — your context dies. You start from scratch, re-explain the goals, paste the same snippets, and lose momentum.

## The Solution

DevMemory is an MCP server that acts as **persistent memory across coding tools**:

```
Cursor saves context  → DevMemory DB → Claude auto-loads context
Claude makes decisions → DevMemory DB → Windsurf continues
Augment credits run low → DevMemory DB → Switch to Antigravity instantly
```

Same project, same memory, zero friction.

---

## 30-Second Quick Start

```bash
# 1. Install
pip install devmemory

# 2. Install for your AI tool (pick one or use --all)
devmemory install --tool cursor --api-key dm_key_YOUR_KEY
devmemory install --tool claude-code --api-key dm_key_YOUR_KEY
devmemory install --all --api-key dm_key_YOUR_KEY

# 3. Restart your tool — done!
```

That's it. DevMemory will automatically save and restore context across tools.

> **Need an API key?** Run `devmemory --rest` → open `http://localhost:8765` → register → create API key.

---

## Supported Tools

| Tool | Install Command | Config File |
|---|---|---|
| **Claude Code** | `devmemory install --tool claude-code` | `~/.claude.json` |
| **Claude Desktop** | `devmemory install --tool claude-desktop` | See [paths below](#config-paths) |
| **Cursor** | `devmemory install --tool cursor` | `~/.cursor/mcp.json` |
| **Windsurf** | `devmemory install --tool windsurf` | `~/.codeium/windsurf/mcp_config.json` |
| **Augment Code** | `devmemory install --tool augment` | `~/.augment/settings.json` |
| **Antigravity** | `devmemory install --tool antigravity` | `~/.gemini/antigravity/mcp_config.json` |
| **Cline** | `devmemory install --tool cline` | See [paths below](#config-paths) |
| **Kilo Code** | `devmemory install --tool kilo` | `~/.config/kilo/kilo.jsonc` |

### Config Paths

<details>
<summary><strong>Claude Desktop</strong></summary>

| OS | Path |
|---|---|
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Linux | `~/.config/Claude/claude_desktop_config.json` |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |
</details>

<details>
<summary><strong>Cline (VS Code)</strong></summary>

| OS | Path |
|---|---|
| macOS | `~/Library/Application Support/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json` |
| Linux | `~/.config/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json` |
| Windows | `%APPDATA%\Code\User\globalStorage\saoudrizwan.claude-dev\settings\cline_mcp_settings.json` |
</details>

---

## How It Works

### 1. AI tools save context automatically

When you code with any tool that has DevMemory connected, it saves structured context blocks — goals, decisions, code, errors, next steps — to the DevMemory database.

### 2. Switch tools, context follows

When you open a different tool on the same project, it reads the saved context and continues where the last tool left off.

### 3. Auto-Sync (Zero Friction)

```
Tool A (Augment) saves context as you code
                    ↓
         DevMemory DB stores everything
                    ↓
 Switch to Tool B (Claude Code / Antigravity)
                    ↓
      Tool B auto-loads context on startup
                    ↓
      Continue exactly where Tool A left off
```

**For Augment**: The install command adds a SessionStart hook that auto-loads context.

**For Claude Code**: Run `devmemory inject` to write context to `CLAUDE.md` (auto-read by Claude).

```bash
# Manual inject (writes CLAUDE.md + .augment/rules/devmemory.md)
devmemory inject --cwd /path/to/project
```

---

## Manual Setup (No CLI)

If you prefer to configure manually, add this to your tool's MCP config file:

```json
{
  "mcpServers": {
    "devmemory": {
      "command": "devmemory",
      "env": {
        "DEVMEMORY_API_KEY": "dm_key_YOUR_KEY_HERE"
      }
    }
  }
}
```

**Windows users**: If `devmemory` isn't on your PATH, use the full path or wrap with cmd:
```json
{
  "command": "cmd",
  "args": ["/c", "devmemory"]
}
```

---

## Features

- 🧩 **Structured Context** — Save typed blocks: goals, decisions, code, errors, next steps, insights, dependencies, blockers
- 🔄 **Resume Prompts** — Generate an optimised "continue here" prompt tuned for each tool
- 🔍 **Auto Project Detection** — Resolves projects from git remote URLs (zero config)
- 🔐 **Multi-user Auth** — JWT + API keys, tiered subscriptions (Free / Pro / Team)
- 📊 **Quota Enforcement** — Tier limits enforced at write time; usage visible via REST API
- 🏠 **Self-Hostable** — Run locally with SQLite; switch to PostgreSQL for production
- 🌐 **Cross-Platform** — Works on Windows, macOS, and Linux
- 📊 **Web Dashboard** — Monitor sessions, projects, and context at `http://localhost:8765`
- ⚡ **Auto-Sync** — SessionStart hooks and inject commands for zero-friction tool switching

---

## MCP Tools

Once connected, your AI tool will have access to these seven tools:

| Tool | What it does |
|---|---|
| `save_context` | Save a typed context block (goal, decision, code, error, next_step, insight, dependency, blocker) |
| `get_context` | Retrieve context blocks for the current session/project |
| `start_session` | Begin a new dev session (auto-detects project from git) |
| `end_session` | Mark a session completed, paused, or archived |
| `list_sessions` | List recent sessions for the current project |
| `generate_resume_prompt` | Build an optimised "continue here" prompt for switching tools |
| `list_projects` | List all known projects for this account |

### Example: Switching from Cursor to Claude

```
# In Cursor — save your work
save_context(block_type="goal", content="Implement OAuth2 login flow", cwd="/my/project")
save_context(block_type="decision", content="Using PKCE flow with refresh tokens", cwd="/my/project")
save_context(block_type="next_step", content="Add /auth/callback endpoint", cwd="/my/project")

# Switch to Claude Code — generate a resume prompt
generate_resume_prompt(session_id="...", target_tool="claude")
# → Structured prompt with goals, decisions, and next steps
# → Claude picks up exactly where Cursor left off
```

---

## CLI Commands

| Command | Description |
|---|---|
| `devmemory` | Start MCP server (stdio, for AI tools) |
| `devmemory --rest` | Start REST API + Web Dashboard |
| `devmemory install --tool <name> --api-key <key>` | One-time setup for an AI tool |
| `devmemory install --all --api-key <key>` | Setup for all detected tools |
| `devmemory inject [--cwd PATH]` | Auto-load context into CLAUDE.md, .augment/rules/ |

---

## REST API

When running with `devmemory --rest`, a full REST API is available:

### Auth

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/auth/register` | Register a new user account |
| `POST` | `/auth/login` | Get a JWT access token |
| `GET` | `/auth/api-keys` | List API keys |
| `POST` | `/auth/api-keys` | Create an API key |
| `DELETE` | `/auth/api-keys/{id}` | Revoke an API key |

### Projects & Sessions

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/projects` | List all projects |
| `GET` | `/sessions` | List sessions (filter by `project_id`, `status`) |
| `GET` | `/sessions/{id}` | Get a single session |
| `PATCH` | `/sessions/{id}` | Update title or status |
| `GET` | `/sessions/{id}/blocks` | List context blocks |
| `DELETE` | `/context-blocks/{id}` | Delete a context block |

### Context

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/context/resume` | Get resume prompt for a project (API key auth) |

### Billing

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/billing/status` | Tier, limits, and current usage |

Interactive docs: **`/docs`** (Swagger) and **`/redoc`** (ReDoc).

---

## Tier Limits

| | Free | Pro | Team |
|---|---|---|---|
| Projects | 3 | 25 | Unlimited |
| Sessions / project | 10 | 100 | Unlimited |
| Blocks / session | 500 | 5 000 | Unlimited |

---

## Development

```bash
# Clone and install dev dependencies
git clone https://github.com/Yuguda999/devmemory.git
cd devmemory
uv sync --extra dev

# Run the test suite
uv run pytest tests/ -v

# Run the REST server locally
uv run devmemory --rest

# Run the MCP server locally (stdio)
uv run devmemory
```

### Environment variables

Copy `.env.example` to `.env` and edit:

```env
DEVMEMORY_DATABASE_URL=sqlite+aiosqlite:///./devmemory.db
DEVMEMORY_SECRET_KEY=your-secret-key-here
DEVMEMORY_HOST=0.0.0.0
DEVMEMORY_PORT=8765
DEVMEMORY_SELF_HOSTED=true   # disables tier limits
```

---

## Architecture

```
AI Tool (Cursor / Claude / Windsurf / Augment / Antigravity / Cline / Kilo)
        │  MCP stdio (JSON-RPC)
        ▼
┌────────────────────────┐
│   DevMemory MCP Server │  ← 7 tools
│   devmemory.tools      │
└───────────┬────────────┘
            │
┌───────────▼────────────┐
│   Auth + Quota Layer   │  ← JWT / API keys / tier enforcement
│   Billing module       │
└───────────┬────────────┘
            │
┌───────────▼────────────┐
│   DB Repository        │  ← SQLAlchemy async, SQLite / PostgreSQL
│   Alembic migrations   │
└────────────────────────┘

Optional: REST API (FastAPI) + Web Dashboard
        ← /auth, /projects, /sessions, /billing, /context/resume
        ← http://localhost:8765 for dashboard

CLI: devmemory install / inject
        ← One-command tool setup
        ← Auto-sync context to CLAUDE.md, .augment/rules/
```

---

## License

MIT — see [LICENSE](LICENSE).
