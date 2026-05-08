# DevMemory

**Universal Dev Memory** — A persistent MCP server that stores, structures, and serves coding context so any AI tool can continue seamlessly.

## The Problem

Every time you switch AI coding tools (Cursor → Claude → Windsurf), your context dies. You start from scratch, re-explain everything, and lose momentum.

## The Solution

DevMemory is an MCP server that acts as **persistent memory across coding tools**:

```
Tool A (Cursor) writes context → DevMemory → Tool B (Claude) reads context
```

Same project, same memory, no loss.

## Features

- 🧩 **Structured Context** — Save typed context blocks (goals, decisions, code, errors, next steps)
- 🔄 **Resume Prompts** — Generate optimized prompts to continue work in a different tool
- 🔍 **Auto Project Detection** — Resolves projects from git remote URLs (zero config)
- 🔐 **Multi-user Auth** — API keys with tiered subscriptions (Free / Pro / Team)
- 🏠 **Self-Hostable** — Run locally with Docker, all features unlocked
- ☁️ **SaaS Option** — Hosted version at devmemory.io

## Quick Start

### Self-Hosted (Docker)

```bash
docker-compose up -d
```

### Install via PyPI

```bash
uvx devmemory
```

### Connect from Claude Desktop

Add to your `claude_desktop_config.json`:

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

## Development

```bash
# Clone and install
git clone https://github.com/Yuguda999/devmemory.git
cd devmemory
uv sync --extra dev

# Run tests
pytest tests/ -v

# Run the server
python -m devmemory.server
```

## Architecture

```
AI Tool → MCP Client → DevMemory MCP Server → SQLite/PostgreSQL
                              ↑
                    Auth + Rate Limiting
                    Git Project Resolver
                    Tier Enforcement
```

## License

MIT
