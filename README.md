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
# Node — nothing to install (recommended, no Python needed):
npx -y @commanderzero/devmemory@latest install --tool cursor --api-key dm_key_YOUR_KEY --host https://your-backend

# Python — pipx (or uv) manages an isolated environment for you:
pipx install devmemory-ai       # or: uv tool install devmemory-ai

devmemory          # starts MCP server (stdio, for AI tools)
devmemory --rest   # starts REST API (HTTP, for dashboards)
```

> **Don't use plain `pip install` on modern Linux.** On Debian/Ubuntu (PEP 668)
> a system `pip install devmemory-ai` errors with "externally-managed-environment"
> unless you're inside a virtual environment. Use **npx**, **pipx**, or **uv tool
> install** above — they need no venv. The PyPI package is `devmemory-ai`; it
> installs the `devmemory` command.

### Ephemeral runner vs. permanent command

Each ecosystem has two forms. A **runner** downloads and runs once, leaving no
command behind. An **installer** puts a persistent `devmemory` on your PATH so
`devmemory start`, `devmemory stop`, etc. work with no prefix.

| | Node | Python |
|---|---|---|
| **Runner** (ephemeral, no leftover command) | `npx @commanderzero/devmemory …` | `uvx --from devmemory-ai devmemory …` |
| **Installer** (permanent `devmemory` on PATH) | `npm install -g @commanderzero/devmemory` | `pipx install devmemory-ai` / `uv tool install devmemory-ai` |

So if you set up with **`npx`** and then `devmemory start` says *command not found*
(or `bad interpreter`), that's expected — `npx` never installed a command. Either
keep prefixing (`npx -y @commanderzero/devmemory@latest start`) **or** install it
once permanently:

```bash
npm install -g @commanderzero/devmemory   # Node: bare `devmemory` now works
```

Both clients share the same `~/.devmemory/config.json`, so a permanent command set
up either way drives the same backend the `install` step configured.

### Requirements & platform support

The DevMemory client runs on **Linux, macOS, and Windows** — it needs only a
runtime, no compiler or system libraries. Pick whichever runtime you already have:

| To use… | You need | Notes |
|---|---|---|
| `npx @commanderzero/devmemory …` (Node runner) | **Node ≥ 18** | No install; runs from cache each time. |
| `npm install -g @commanderzero/devmemory` (Node, permanent) | **Node ≥ 18** + npm | Global bin must be on PATH (usually is). Some Linux setups need `npm config set prefix ~/.local` or a PATH tweak; avoid `sudo` by using a user prefix. |
| `uvx --from devmemory-ai devmemory …` (Python runner) | **Python 3.10+** + uv | No install; runs ephemerally. |
| `pipx install devmemory-ai` / `uv tool install devmemory-ai` (Python, permanent) | **Python 3.10+** | Puts `devmemory` on PATH in an isolated env. |
| MCP working inside your AI tool | Node **or** Python reachable by the tool | `devmemory install` writes an absolute/`npx` command so the tool can launch it without your shell's PATH. |

**Platform notes**

- **Windows:** all four install methods work. The npm global bin is `%AppData%\npm`
  (normally on PATH); there is no `~/.local/bin`. Use PowerShell/CMD paths, not `~`.
- **`command not found` after a global install** is a PATH issue, not a broken
  install — ensure the runtime's global bin dir is on PATH (`npm bin -g`, or
  `python -m site --user-base`+`/bin`).
- **`bad interpreter`** only happens to a *Python* `devmemory` shim whose
  interpreter was deleted/moved (see [Troubleshooting](#troubleshooting)). The
  `npx` path has no interpreter shim and cannot hit this.
- **Most portable one-liner for any machine:** `npx -y @commanderzero/devmemory@latest install --tool <name> --api-key <key> --host <url>`, then restart the tool. A permanent CLI (`npm i -g`) is optional convenience.

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

**Custom config dir / multiple profiles.** If you run Claude Code with
`CLAUDE_CONFIG_DIR` set, its config lives at `<dir>/.claude.json` (not
`~/.claude.json`). `devmemory install` auto-detects the env var and writes to the
right place. To set up several profiles in one run, pass comma-separated dirs:

```bash
devmemory install --tool claude-code --api-key dm_key_YOUR_KEY \
  --config-dir ~/.claude-work,~/.claude-personal
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

DevMemory saves three ways:

1. **Tools with a transcript hook (Claude Code, Windsurf) — direct hooks.**
   These tools fire an OS-level hook after each turn and hand it a *plaintext*
   conversation transcript. `install` wires a small script into that hook which
   POSTs the turn — no `save_context` call, no reading the tool's (often
   encrypted) conversation store. Claude Code uses `Stop`; Windsurf uses
   `post_cascade_response_with_transcript`.

2. **Store-tailing tools (Cursor, Cline, Kilo, Codex, Claude Code) — the watch daemon.**
   These persist conversations locally. `devmemory watch` is a background daemon
   that tails those stores and pushes new turns — again, zero model cooperation.
   `install` sets it up as a systemd/launchd service automatically. Claude Code is
   covered here too (reading `~/.claude/projects/**/*.jsonl`) so the `devmemory
   start` attach model saves it even when the Stop hook isn't wired.

3. **Tools with no verified hook (Antigravity, Claude Desktop) — MCP tools + rules.**
   These IDEs expose no per-turn transcript hook an installer can reliably wire
   (Antigravity's documented hooks are SDK decorators for SDK-built agents, not
   the IDE). So `install` writes an always-on global rules file (e.g.
   `~/.gemini/GEMINI.md`) that drives save/restore through the DevMemory MCP
   tools. Agent-driven, not deterministic — but honest.

**Attaching works the same everywhere.** However a tool saves, you pick the
project the same way: either run `devmemory start` in the folder, or — in *any*
MCP-connected tool — just say **"continue"** (or "start on this project"). The
agent calls `continue_here` for the folder you have open, which attaches that
project and restores its context. The project is resolved from the open folder's
git remote or name; to target a different one, tell the agent its name.

### Prompts to paste

No commands to memorise — say one of these to your AI tool and it drives
DevMemory through the MCP tools for the project folder you have open:

- **Continue / attach** — *"Use DevMemory: continue where we left off on this project. Attach this folder and load my saved context before we start."*
- **Save progress now** — *"Save our progress to DevMemory now — the current goal, the key decisions we made, and the next steps to pick up later."*
- **Check what's saved** — *"What has DevMemory saved for this project so far? Load the latest context and summarise it."*
- **Switch project** — *"Attach DevMemory to the project named `PROJECT_NAME` and load its saved context."*

These are also copy-buttoned in the dashboard **Setup** page and the **docs**.

Check what's supported and detected on your machine:

```bash
devmemory watch --list
```

### Tool support matrix

| Tool | Auto-save mechanism | Status |
|---|---|---|
| **Claude Code** | `Stop` hook (transcript) | ✅ deterministic |
| **Windsurf** | `post_cascade_response_with_transcript` hook (transcript JSONL) + `global_rules.md` restore | ✅ deterministic |
| **Antigravity** | MCP tools + `~/.gemini/GEMINI.md` global rules | ✅ agent-driven (MCP) |
| **Cursor** | `watch` daemon (SQLite store) | ✅ verified |
| **Cline / Kilo** | `watch` daemon (JSON task history) | ✅ supported |
| **Codex** | `watch` daemon (`state_*.sqlite` + rollout JSONL) | ✅ supported |
| _any JSONL tool_ | `watch` generic adapter (`~/.devmemory/watch_adapters.json`) | ✅ config-driven |

> **Windsurf & Antigravity encrypt conversations on disk.** DevMemory does not
> try to crack that. Windsurf hands its own hook a *plaintext transcript*, so we
> capture each turn deterministically. Antigravity exposes no such hook to an
> installer, so it saves/restores through the MCP tools + a global rules file.
> Honest coverage: `devmemory watch --list` shows the exact mechanism per tool.

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
| `devmemory mcp` | Start MCP server (stdio) — explicit form |
| `devmemory --rest` | Start REST API + Web Dashboard |
| `devmemory install --tool <name> --api-key <key>` | One-time setup for an AI tool |
| `devmemory install --tool claude-code --config-dir <dir[,dir…]>` | Target specific Claude Code profile dirs (auto-detects `CLAUDE_CONFIG_DIR`) |
| `devmemory install --all --api-key <key>` | Setup for all detected tools |
| `devmemory inject [--cwd PATH]` | Auto-load context into CLAUDE.md, .augment/rules/ |
| `devmemory watch` | Background daemon: auto-save Claude Code/Cursor/Cline/Kilo/Codex conversations |
| `devmemory watch --list` | Show per-tool auto-save support + which stores are present |
| `devmemory watch --install-service` | Install watch as a systemd/launchd background service |

### Multiple Claude Code profiles (`--config-dir`)

Claude Code honors the `CLAUDE_CONFIG_DIR` environment variable — set it and
Claude reads `$CLAUDE_CONFIG_DIR/.claude.json` instead of `~/.claude.json`. If
you run several profiles (e.g. per-client or per-org configs), install DevMemory
into each with `--config-dir`, giving a **comma-separated list** of directories:

```bash
npx -y @commanderzero/devmemory@latest install --tool claude-code \
  --api-key dm_key_YOUR_KEY --host https://your-backend \
  --config-dir ~/.claudeAcme,~/.claudeBeta,~/.claude
```

Each directory gets its own `.claude.json` written. With no `--config-dir`, the
command auto-detects `CLAUDE_CONFIG_DIR` (or falls back to `~/.claude.json`).

> **Commas only — no spaces.** Write `~/a,~/b,~/c`, not `~/a, ~/b, ~/c`. A space
> makes your shell split the list into separate arguments, so the client sees a
> stray positional and errors with `Unknown option '--config-dir'`. Quote the
> list (`--config-dir "~/a,~/b"`) if you want to be safe.
>
> **Pin the version to skip stale `npx` cache** — `npx @commanderzero/devmemory@latest …`
> forces a fresh fetch. A bare name can reuse an older cached copy that predates a
> flag. `--config-dir` requires **≥ 0.3.3**.

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

- **`devmemory: command not found`** — no permanent command is on your PATH. Common causes:
  - **You set up with a runner** (`npx` / `uvx`). Those run once and leave no command.
    Install it permanently — `npm install -g @commanderzero/devmemory` (Node) or
    `pipx install devmemory-ai` (Python) — or keep prefixing (`npx -y @commanderzero/devmemory@latest start`).
  - **A global install's bin dir isn't on PATH, or the install needed `sudo`.** On
    many Linux setups npm's global prefix is the root-owned `/usr/local`, so a plain
    `npm install -g …` silently needs elevated permissions. Avoid `sudo` with a
    one-time user prefix (its bin dir is usually already on PATH):
    ```bash
    npm config set prefix ~/.local
    npm install -g @commanderzero/devmemory
    # then confirm: which devmemory
    ```
  - **(Dev only)** your venv isn't active. Run `source venv/bin/activate`, then `pip install -e .`.
- **`No such option: --rest`** — you're running an old published build, not your
  source. Reinstall from your checkout: `pip install -e .` (or use `uv run devmemory --rest`).
  Verify with `pip show devmemory` — it should list an `Editable project location`
  pointing at this repo.
- **`bad interpreter: .../python3: No such file or directory`** — the `devmemory`
  command is a shim whose shebang points at a Python interpreter that has since been
  deleted or moved (common after a `uv`/`pipx` Python upgrade, or when a project
  `.venv` used for a `pip install -e .` is removed). The shim can't launch, so *any*
  `devmemory …` invocation fails before our code runs. Fixes, in order of preference:
  - **Use the Node client** — it has no Python shim and re-fetches itself, so it can't
    dangle: `npx -y @commanderzero/devmemory@latest install --tool <name> --api-key <key> --host <url>`.
  - **Reinstall the Python tool** so the shebang is rebuilt against a live interpreter:
    `uv tool install --reinstall devmemory-ai` (or `pipx reinstall devmemory-ai`).
  - **Remove a dead dev shim** left over from an editable install: `rm ~/.local/bin/devmemory`,
    then reinstall via one of the above.

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
