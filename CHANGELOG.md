# Changelog

All notable changes to DevMemory are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
DevMemory uses [Semantic Versioning](https://semver.org/).

---

## [0.3.1] — 2026-07-12

### Changed
- **Auto-save is now ON by default for every project — no per-project attach.**
  Previously a strict opt-in gate meant a turn was persisted only for the single
  project attached with `devmemory start` (or the `continue_here` MCP tool); every
  other project's Stop hook logged `skip: project not active` and saved nothing.
  DevMemory now saves the current project on every turn automatically — matching
  how MemPalace weaves memories on each Stop — with two opt-outs:
  - per-project: `devmemory stop` (adds the slug to `~/.devmemory/paused.json`)
  - globally: set `DEVMEMORY_AUTOSAVE=off`

  `devmemory start` now un-pauses a project and restores its context; `devmemory
  stop` pauses only the current project (others keep saving); `devmemory status`
  reports the auto-save state and the paused list. The watch daemon no longer
  requires an active marker to run.

---

## [0.3.0] — 2026-07-11

### Fixed
- **Claude Code installs now honor `CLAUDE_CONFIG_DIR`.** The installer wrote the
  MCP server entry to `~/.claude.json` and the hooks to `~/.claude/settings.json`
  unconditionally. Users who run Claude Code with `CLAUDE_CONFIG_DIR` set have
  their config at `<dir>/.claude.json` and `<dir>/settings.json`, so DevMemory
  wrote to files Claude never reads — the MCP server and hooks silently never
  loaded. Both the Python and npm installers now resolve the correct location.
  Default installs (env var unset) are unchanged.

### Added
- **`devmemory mcp` subcommand** — explicit verb to start the MCP stdio server.
  The installer now launches the server as `devmemory mcp` so the Python and npm
  channels use an identical command; bare `devmemory` still starts the server for
  backward compatibility with existing configs.
- **`devmemory install --config-dir <dir[,dir…]>`** — target one or more specific
  Claude Code profile directories in a single run (overrides `CLAUDE_CONFIG_DIR`).
  Comma-separated `CLAUDE_CONFIG_DIR` is also honored: each listed profile gets
  its own install of the MCP server and hooks.

---

## [0.2.0] — 2026-07-11

### Added
- **Attach model** — auto-save is now opt-in and scoped to one project at a time.
  New CLI: `devmemory start` (attach current project, restore context, begin
  saving), `devmemory continue` (re-attach the active project in a new tool),
  `devmemory stop`, `devmemory status`. Backed by a single marker
  `~/.devmemory/active.json` consulted by both the watch daemon and the hooks.
- **`continue_here` MCP tool** — attaches the current project and returns its
  resume prompt in one call (trigger it by saying "continue"/"resume").
- **npm/Node client parity** — `start`/`continue`/`stop`/`status` now work from
  the Node client too (`npx @commanderzero/devmemory start`). It reads/writes the
  same `~/.devmemory/config.json` + `active.json` as the Python client, so a
  session attached from either is honored by both. The watch daemon stays
  Python-only; the Node client prints how to run it.
- **Global config** — `~/.devmemory/config.json` persists `{host, api_key}` so
  `start`/`continue`/`inject` reach the right backend without re-passing flags.
  Written by `install`/`start`/`continue`; resolution order is
  explicit flag → env → config → default.
- **New public site** — bold-gradient landing page (`/`) and docs page (`/docs`),
  a self-contained design system (`css/site.css`), and no external CDNs.
- **Dashboard reskin** — SPA restyled onto the shared indigo design system.

### Changed
- Auto-save is now strictly opt-in: nothing is saved until a project is attached
  (was: the watch daemon/hooks saved every resolved project).
- Serving layout: `/` → landing, `/docs` → docs page, `/app` → dashboard SPA.
  FastAPI's OpenAPI docs moved to `/api-docs` and `/api-redoc`.
- `inject`/hooks no longer fall back to hardcoded `localhost:8765` — they resolve
  the backend from the persisted config.
- Install docs reordered to lead with no-venv paths (npx → pipx → uv → pip).

---

## [0.1.0] — 2026-05-28

### Added

#### Phase 1 — Core Foundation
- SQLAlchemy async models: `User`, `ApiKey`, `Subscription`, `Project`, `Session`, `ContextBlock`
- Alembic migrations with `aiosqlite` (SQLite default) and `asyncpg` (PostgreSQL optional)
- JWT authentication (`/auth/register`, `/auth/login`)
- API key management (`POST /auth/api-keys`, `GET /auth/api-keys`, `DELETE /auth/api-keys/{id}`)
- Git project resolver — auto-detects project slug and name from `git remote get-url origin`
- FastAPI REST application with CORS and health check endpoint

#### Phase 2 — MCP Server
- `FastMCP` server wired to stdio transport (standard for `uvx`-invoked servers)
- Seven MCP tools: `save_context`, `get_context`, `start_session`, `end_session`, `list_sessions`, `generate_resume_prompt`, `list_projects`
- API key auth for MCP tools via `DEVMEMORY_API_KEY` env var or explicit `api_key` argument
- Resume prompt generator with semantic block ordering (goals → decisions → code → errors → next steps → notes) and per-tool preambles (Claude, Cursor, Windsurf)
- CLI dispatcher: `devmemory` (MCP stdio) and `devmemory --rest` (HTTP)

#### Phase 3 — Billing & Quota Enforcement
- `billing/quota.py` — `TierQuota` dataclass and `QuotaExceededError`
- Tier limits: Free (3 projects / 10 sessions / 500 blocks), Pro (25 / 100 / 5 000), Team (unlimited)
- Quota gates in `save_context` (project + session + block), `start_session` (project + session)
- `get_usage_summary()` — returns `{tier, limits, usage}` for dashboards
- `list_projects_tool` now includes `quota` metadata in its response

#### Phase 4 — REST API Polish
- `GET /projects` — list all projects
- `GET /sessions`, `GET /sessions/{id}`, `PATCH /sessions/{id}` — session management
- `GET /sessions/{id}/blocks` — context block listing per session
- `DELETE /context-blocks/{id}` — context block deletion
- `GET /billing/status` — tier, limits, and current usage
- Full Pydantic v2 response schemas for all endpoints
- Interactive OpenAPI docs at `/docs` and `/redoc`

#### Phase 5 — Publication & CI
- `pyproject.toml` — production metadata (Beta status, project URLs, `Typing :: Typed` classifier)
- `README.md` — full documentation with MCP config for Claude Desktop, Cursor, and Windsurf
- `.github/workflows/ci.yml` — test on Python 3.10/3.11/3.12, lint with Ruff, build distribution

### Test Coverage
- 208 tests, all passing (no external services required)

[0.1.0]: https://github.com/Yuguda999/devmemory/releases/tag/v0.1.0
