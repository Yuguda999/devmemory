# Changelog

All notable changes to DevMemory are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
DevMemory uses [Semantic Versioning](https://semver.org/).

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
