"""DevMemory server entry point.

CLI usage
---------
``devmemory``              — Start the MCP server (stdio transport, default).
``devmemory --rest``       — Start the REST API server (HTTP).
``devmemory --rest --port 9000``  — REST on a custom port.

MCP transport
-------------
The default ``stdio`` transport is what AI tools expect when launching a
server via ``uvx devmemory`` or ``uv run devmemory``.  The process reads
JSON-RPC messages from stdin and writes responses to stdout.

Authentication
--------------
Set ``DEVMEMORY_API_KEY=dm_key_...`` in the environment (e.g. in Claude
Desktop's ``claude_desktop_config.json``) so tools can authenticate without
passing the key as an explicit argument.
"""

from __future__ import annotations

import argparse
import asyncio


def run_mcp() -> None:
    """Start the MCP server using stdio transport."""
    # Import here to ensure DB lifespan is wired before the MCP loop starts.
    from devmemory.db.engine import init_db
    from devmemory.tools import mcp

    async def _main() -> None:
        await init_db()
        await mcp.run_stdio_async()

    asyncio.run(_main())


def run_rest(host: str | None = None, port: int | None = None) -> None:
    """Start the FastAPI REST server."""
    import uvicorn

    from devmemory.api.app import create_app
    from devmemory.config import settings

    app = create_app()
    uvicorn.run(
        app,
        host=host or settings.host,
        port=port or settings.port,
        log_level=settings.log_level.lower(),
    )


def run() -> None:
    """CLI entry point — dispatches to MCP (default) or REST (--rest flag)."""
    parser = argparse.ArgumentParser(
        prog="devmemory",
        description="DevMemory — Universal Dev Memory for AI coding tools",
    )
    parser.add_argument(
        "--rest",
        action="store_true",
        help="Start the REST API server instead of the MCP stdio server",
    )
    parser.add_argument(
        "--host",
        default=None,
        help="Host for the REST server (overrides DEVMEMORY_HOST)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Port for the REST server (overrides DEVMEMORY_PORT)",
    )
    args = parser.parse_args()

    if args.rest:
        run_rest(host=args.host, port=args.port)
    else:
        run_mcp()


if __name__ == "__main__":
    run()
