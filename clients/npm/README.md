# @commanderzero/devmemory

Persistent, cross-tool coding memory for AI agents — the Node/npx client for
[DevMemory](https://github.com/Yuguda999/devmemory). It's a thin MCP server that
saves and restores your coding context (goals, decisions, code, errors, next
steps) through a DevMemory backend, so you can switch between Claude Code,
Cursor, Windsurf, etc. without losing state.

**No Python required.** Runs on Linux, macOS, and Windows — needs only **Node ≥ 18**.

> Published as **`@commanderzero/devmemory`** (the bare `devmemory` name is blocked
> by npm as too similar to an existing package). The CLI command it installs is
> still `devmemory`.

## Quick start

Point your tools at your DevMemory backend (get an API key from its dashboard):

```bash
npx -y @commanderzero/devmemory@latest install --tool cursor \
  --api-key dm_key_your_key \
  --host https://your-devmemory.onrender.com
```

Use `--all` to configure every detected tool, or `--tool <name>` for one of:
`claude-code`, `cursor`, `windsurf`, `claude-desktop`, `antigravity`, `cline`,
`kilo`. Restart the tool afterward.

> **Always pin `@latest`.** A bare `npx @commanderzero/devmemory` can reuse an
> older copy from the npx cache — pinning forces a fresh fetch so you never run a
> build that predates a flag.

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

## Runner vs. permanent command

`npx` is a **runner**: it downloads and runs once, leaving no `devmemory` command
behind. Great for `install`, but afterward `devmemory start` will say
*command not found*. For a permanent `devmemory` on your PATH, install it once:

```bash
npm install -g @commanderzero/devmemory
```

Then `devmemory start`, `devmemory stop`, etc. work with no prefix. If you'd
rather not install globally, keep prefixing: `npx -y @commanderzero/devmemory@latest start`.

## Commands

| Command | What it does |
|---------|--------------|
| `devmemory` / `devmemory mcp` | Start the MCP stdio server (what AI tools launch) |
| `devmemory install --tool <name>\|--all --api-key <key> [--host <url>]` | Write the MCP config for a tool |
| `devmemory install --tool claude-code --config-dir <dir[,dir…]>` | Target specific Claude Code profile dirs (auto-detects `CLAUDE_CONFIG_DIR`) |
| `devmemory start` | Attach the current project, restore its context, begin saving |
| `devmemory continue` | Re-attach the active project in a new tool and restore context |
| `devmemory stop` / `devmemory status` | Detach / show the active session |
| `devmemory inject [--cwd <dir>] [--host <url>] [--api-key <key>]` | Write the latest resume prompt to `CLAUDE.md` |

## Multiple Claude Code profiles (`--config-dir`)

Claude Code reads `$CLAUDE_CONFIG_DIR/.claude.json` when that env var is set.
Install into several profiles at once with a **comma-separated list, no spaces**:

```bash
npx -y @commanderzero/devmemory@latest install --tool claude-code \
  --api-key dm_key_your_key --host https://your-backend \
  --config-dir ~/.claudeAcme,~/.claudeBeta,~/.claude
```

> **Commas only — no spaces.** `~/a,~/b`, not `~/a, ~/b`. A space makes your shell
> split the list into separate arguments and the client errors with
> `Unknown option '--config-dir'`. `--config-dir` requires **≥ 0.3.3**.

## Environment

- `DEVMEMORY_HOST` — backend URL (default `http://localhost:8765`)
- `DEVMEMORY_API_KEY` — API key (fallback when `--api-key` / the tool arg is omitted)
- `CLAUDE_CONFIG_DIR` — Claude Code only: when set, `install --tool claude-code` writes to `<dir>/.claude.json` instead of `~/.claude.json`. Comma-separated for multiple profiles.

## Troubleshooting

- **`devmemory: command not found`** — you ran `install` via `npx` (a runner — it
  leaves no command behind), or a global install's bin dir isn't on your PATH.
  Fix: `npm install -g @commanderzero/devmemory`, then ensure its bin dir is on
  PATH. On Linux the npm global prefix is often the root-owned `/usr/local`, so a
  plain `npm install -g` needs `sudo`. Avoid `sudo` by using a user prefix once:
  ```bash
  npm config set prefix ~/.local          # ~/.local/bin is usually already on PATH
  npm install -g @commanderzero/devmemory
  ```
- **`bad interpreter: .../python3: No such file or directory`** — that's a *Python*
  `devmemory` shim whose interpreter was deleted/moved. It does not affect this
  Node client (there is no interpreter shim). Use the `npx`/`npm` commands here, or
  delete the dead shim (`rm ~/.local/bin/devmemory`) and reinstall.
- **`Unknown option '--config-dir'`** — either a space in the comma list (see
  above) or a stale npx cache serving a build older than 0.3.3. Pin `@latest`.
- **`Invalid or revoked API key` (but the key works on the dashboard)** — a stale
  `~/.devmemory/api_key` file is shadowing it. Key resolution order is
  `--api-key` → `DEVMEMORY_API_KEY` → `~/.devmemory/api_key` → `~/.devmemory/config.json`,
  so an old key in the file beats a fresh `install`. Re-run `install` (v0.3.5+ keeps
  both files in sync) or delete the stale file: `rm ~/.devmemory/api_key`.

## Tools exposed to the agent

`save_context`, `save_tasks`, `update_task`, `get_context`, `start_session`,
`end_session`, `list_sessions_tool`, `generate_resume_prompt`,
`list_projects_tool` — identical to the Python client, all backed by the
DevMemory REST API.

MIT © Yuguda Kolo
