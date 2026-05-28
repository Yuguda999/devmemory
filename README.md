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
Cursor writes context → DevMemory → Claude reads context
Claude makes decisions → DevMemory → Windsurf continues
```

Same project, same memory, zero setup per tool.

---

## Features

- 🧩 **Structured Context** — Save typed blocks: goals, decisions, code, errors, next steps, notes
- 🔄 **Resume Prompts** — Generate an optimised "continue here" prompt tuned for each tool
- 🔍 **Auto Project Detection** — Resolves projects from git remote URLs (zero config)
- 🔐 **Multi-user Auth** — JWT + API keys, tiered subscriptions (Free / Pro / Team)
- 📊 **Quota Enforcement** — Tier limits enforced at write time; usage visible via REST API
- 🏠 **Self-Hostable** — Run locally with SQLite; switch to PostgreSQL for production
- ☁️ **SaaS Option** — Hosted version at devmemory.io (coming soon)

---

## Quick Start

### Install via PyPI (MCP server)

```bash
# Run directly — no install needed
uvx devmemory

# Or install globally
pip install devmemory
devmemory          # starts MCP server (stdio, for AI tools)
devmemory --rest   # starts REST API (HTTP, for dashboards)
```

### Connect from Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "devmemory": {
      "command": "uvx",
      "args": ["devmemory"],
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
      "command": "uvx",
      "args": ["devmemory"],
      "env": {
        "DEVMEMORY_API_KEY": "dm_key_your_key_here"
      }
    }
  }
}
```

### Connect from Windsurf

Add to `~/.codeium/windsurf/mcp_config.json`:

```json
{
  "mcpServers": {
    "devmemory": {
      "command": "uvx",
      "args": ["devmemory"],
      "env": {
        "DEVMEMORY_API_KEY": "dm_key_your_key_here"
      }
    }
  }
}
```

---

## MCP Tools

Once connected, your AI tool will have access to these seven tools:

| Tool | What it does |
|---|---|
| `save_context` | Save a typed context block (goal, decision, code, error, next_step, note) |
| `get_context` | Retrieve context blocks for the current session/project |
| `start_session` | Begin a new dev session (auto-detects project from git) |
| `end_session` | Mark a session completed, paused, or archived |
| `list_sessions` | List recent sessions for the current project |
| `generate_resume_prompt` | Build an optimised "continue here" prompt for switching tools |
| `list_projects` | List all known projects for this account |

### Example usage (Claude asking DevMemory to save context)

```
save_context(
  block_type="goal",
  content="Implement MCP billing quota enforcement for free/pro/team tiers",
  cwd="/home/user/devmemory",
  priority=8
)
```

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

# Run the test suite (208 tests, ~30s)
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
AI Tool (Cursor / Claude / Windsurf)
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

Optional: REST API (FastAPI)
        ← /auth, /projects, /sessions, /billing
```

---

## License

MIT — see [LICENSE](LICENSE).
