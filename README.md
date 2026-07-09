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
# Install globally so the `devmemory` command is on your PATH.
# The PyPI package is `devmemory-ai`; it installs the `devmemory` command.
pip install devmemory-ai       # or: uv tool install devmemory-ai  /  pipx install devmemory-ai

devmemory          # starts MCP server (stdio, for AI tools)
devmemory --rest   # starts REST API (HTTP, for dashboards)
```

> **Prefer Node? No Python required.** Connect any tool via npm:
> ```bash
> npx -y @commanderzero/devmemory install --tool cursor --api-key dm_key_YOUR_KEY --host https://your-backend
> ```
> Same tools, same backend — it just runs the MCP client on Node instead.

> **Install it for real — don't rely on `uvx` in MCP configs.** AI tools
> launch the MCP server with their own environment, not your shell's PATH. A bare
> `devmemory` (or `uvx`) only resolves if it happens to be on that PATH, which
> causes intermittent "failed to connect" errors. The `devmemory install` command
> below avoids this by writing the **absolute path** to the binary into the config.

### Connect from Claude Code (recommended)

Let DevMemory write the config for you — this resolves the absolute path automatically:

```bash
devmemory install --tool claude-code --api-key dm_key_YOUR_KEY
```

Then restart Claude Code (or run `/mcp` → reconnect in an active session). Verify with:

```bash
claude mcp list   # devmemory should show ✔ Connected
```

### Connect from Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "devmemory": {
      "command": "uvx",
      "args": ["--from", "devmemory-ai", "devmemory"],
      "env": {
        "DEVMEMORY_API_KEY": "dm_key_your_key_here"
      }
    }
  }
}
```

### Connect from Cursor

Add to `~/.cursor/mcp.json`:

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

**Configuring manually?** Use the **absolute path** to the binary, not a bare
`devmemory` — the tool's launch environment usually has a different PATH than your
shell. Find it with `which devmemory` (macOS/Linux) or `where devmemory` (Windows):

```json
{
  "command": "/full/path/to/devmemory",
  "env": { "DEVMEMORY_API_KEY": "dm_key_YOUR_KEY_HERE" }
}
```

On Windows you can alternatively wrap with cmd: `"command": "cmd", "args": ["/c", "devmemory"]`.

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
- 🤖 **Deterministic Auto-Save** — saves your work with **no reliance on the model** calling a tool (see below)

---

## Auto-Save — how context actually gets saved

The whole point of DevMemory is that when your credits run out **mid-work**, the
next tool can continue. That only works if your context was saved *before* the
credits died — so saving must not depend on the AI remembering to do it.

DevMemory saves deterministically, two ways:

1. **Claude Code — Stop hook.** `install --tool claude-code` wires an OS-level
   `SessionStart` + `Stop` hook. Every turn is snapshotted from the transcript
   automatically. No `save_context` call needed. Restores on the next session.

2. **Tools without a transcript hook (Cursor, Cline, Kilo, Codex) — the watch daemon.**
   These tools don't hand a transcript to a shell hook, but they *do* persist
   conversations locally. `devmemory watch` is a background daemon that tails
   those stores and pushes new turns to DevMemory — again, with zero model
   cooperation. `install` sets it up as a systemd/launchd service automatically.

Check what's supported and detected on your machine:

```bash
devmemory watch --list
```

### Tool support matrix

| Tool | Auto-save mechanism | Status |
|---|---|---|
| **Claude Code** | `Stop` hook (reads transcript) | ✅ deterministic |
| **Cursor** | `watch` daemon (SQLite store) | ✅ verified |
| **Cline / Kilo** | `watch` daemon (JSON task history) | ✅ supported |
| **Codex** | `watch` daemon (`state_*.sqlite` + rollout JSONL) | ✅ supported |
| _any JSONL tool_ | `watch` generic adapter (`~/.devmemory/watch_adapters.json`) | ✅ config-driven |
| **Windsurf** | restore via hook; auto-save pending | ⏳ pending |
| **Antigravity** | conversations are opaque protobuf — not parseable yet | ❌ unsupported |

> DevMemory does **not** fake support. Tools it can't yet auto-save are listed
> honestly above and by `watch --list`, rather than shipped as adapters that
> silently capture nothing.

### Adding an unlisted tool (generic adapter)

If your tool logs conversations as JSONL, add it without code —
`~/.devmemory/watch_adapters.json`:

```json
{
  "adapters": [
    {
      "name": "my-tool",
      "glob": "~/.mytool/sessions/**/*.jsonl",
      "role_field": "role",
      "text_field": "content",
      "user_values": ["user"],
      "assistant_values": ["assistant", "model"]
    }
  ]
}
```

`role_field`/`text_field` accept dotted paths (e.g. `payload.role`).

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
| `devmemory watch` | Background daemon: auto-save Cursor/Cline/Kilo/Codex conversations |
| `devmemory watch --list` | Show per-tool auto-save support + which stores are present |
| `devmemory watch --install-service` | Install watch as a systemd/launchd background service |

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

> **Always run your local code with `uv run`** (or an editable install — see below).
> `uvx --from devmemory-ai devmemory` and `pip install devmemory-ai` download the
> **published PyPI release**, which may be older than your checkout.

#### Using a plain `venv` instead of `uv`

If you prefer `python -m venv`:

```bash
python -m venv venv
source venv/bin/activate        # do this in every new terminal
pip install -e .                # editable: links the command to your source
```

After `pip install -e .`, the `devmemory` command runs your local code and
picks up edits without reinstalling.

### Troubleshooting

- **`devmemory: command not found`** — the command isn't on your PATH. Either you
  used `uvx` (which never installs a persistent command) or your venv isn't active.
  Run `source venv/bin/activate`, then `pip install -e .`.
- **`No such option: --rest`** — you're running an old published build, not your
  source. Reinstall from your checkout: `pip install -e .` (or use `uv run devmemory --rest`).
  Verify with `pip show devmemory` — it should list an `Editable project location`
  pointing at this repo.

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
