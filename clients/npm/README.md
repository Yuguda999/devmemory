# devmemory

Persistent, cross-tool coding memory for AI agents — the Node/npx client for
[DevMemory](https://github.com/Yuguda999/devmemory). It's a thin MCP server that
saves and restores your coding context (goals, decisions, code, errors, next
steps) through a DevMemory backend, so you can switch between Claude Code,
Cursor, Windsurf, etc. without losing state.

No Python required.

## Quick start

Point your tools at your DevMemory backend (get an API key from its dashboard):

```bash
npx --yes @commanderzero/devmemory install --tool cursor \
  --api-key dm_key_your_key \
  --host https://your-devmemory.onrender.com
```

> Published as **`@commanderzero/devmemory`** on npm (the bare `devmemory` name is
> blocked by npm as too similar to an existing package). The CLI command it
> installs is still `devmemory`.

Use `--all` to configure every detected tool, or `--tool <name>` for one of:
`claude-code`, `cursor`, `windsurf`, `claude-desktop`, `antigravity`, `cline`,
`kilo`. Restart the tool afterward.

That writes an MCP entry that launches the server via `npx`:

```json
{
  "mcpServers": {
    "devmemory": {
      "command": "npx",
      "args": ["-y", "@commanderzero/devmemory", "mcp"],
      "env": {
        "DEVMEMORY_API_KEY": "dm_key_your_key",
        "DEVMEMORY_HOST": "https://your-devmemory.onrender.com"
      }
    }
  }
}
```

## Commands

| Command | What it does |
|---------|--------------|
| `devmemory` / `devmemory mcp` | Start the MCP stdio server (what AI tools launch) |
| `devmemory install --tool <name>\|--all --api-key <key> [--host <url>]` | Write the MCP config for a tool |
| `devmemory inject [--cwd <dir>] [--host <url>] [--api-key <key>]` | Write the latest resume prompt to `CLAUDE.md` |

## Environment

- `DEVMEMORY_HOST` — backend URL (default `http://localhost:8765`)
- `DEVMEMORY_API_KEY` — API key (fallback when `--api-key` / the tool arg is omitted)

## Tools exposed to the agent

`save_context`, `save_tasks`, `update_task`, `get_context`, `start_session`,
`end_session`, `list_sessions_tool`, `generate_resume_prompt`,
`list_projects_tool` — identical to the Python client, all backed by the
DevMemory REST API.

MIT © Yuguda Kolo
