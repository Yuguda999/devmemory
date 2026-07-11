"""DevMemory server entry point.

CLI usage
---------
``devmemory``                                    — Start the MCP server (stdio transport, default).
``devmemory --rest``                             — Start the REST API server (HTTP).
``devmemory --rest --port 9000``                 — REST on a custom port.
``devmemory install --tool cursor --api-key K``  — One-time setup for an AI tool.
``devmemory install --all --api-key K``          — Setup for all detected tools.
``devmemory inject``                             — Auto-load context into tool files.
``devmemory inject --cwd /path --tool claude``   — Inject for a specific project/tool.

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
    """Start the MCP server using stdio transport.

    The MCP server is a thin HTTP client of the REST API (see devmemory.tools);
    it holds no database connection, so there is no DB to initialise here.
    """
    from devmemory.tools import mcp

    asyncio.run(mcp.run_stdio_async())


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
    """CLI entry point — dispatches to MCP (default), REST, install, or inject."""
    from devmemory.cli.install import ALL_TOOL_SLUGS

    parser = argparse.ArgumentParser(
        prog="devmemory",
        description="DevMemory — Universal Dev Memory for AI coding tools",
    )

    # Create subcommands
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # ── devmemory install ──────────────────────────────────────────────────
    install_parser = subparsers.add_parser(
        "install",
        help="Install DevMemory MCP into an AI coding tool",
        description="One-command setup for any AI coding tool.",
    )
    install_parser.add_argument(
        "--tool",
        required=True,
        choices=ALL_TOOL_SLUGS + ["all"],
        help="Which tool to install for, or 'all' for every detected tool",
    )
    install_parser.add_argument(
        "--api-key",
        default=None,
        help="DevMemory API key (or set DEVMEMORY_API_KEY env var)",
    )
    install_parser.add_argument(
        "--host",
        default=None,
        help="DevMemory REST server URL (for SaaS: https://api.devmemory.io)",
    )
    install_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be written without making changes",
    )

    # ── devmemory inject ───────────────────────────────────────────────────
    inject_parser = subparsers.add_parser(
        "inject",
        help="Auto-load DevMemory context into tool files (CLAUDE.md, .augment/rules/)",
        description="Fetch context from the REST API and write to tool-specific files.",
    )
    inject_parser.add_argument(
        "--cwd",
        default=None,
        help="Project directory (defaults to current working directory)",
    )
    inject_parser.add_argument(
        "--tool",
        default="generic",
        help="Target tool for the resume prompt preamble (claude, augment, cursor, etc.)",
    )
    inject_parser.add_argument(
        "--api-key",
        default=None,
        help="DevMemory API key (or set DEVMEMORY_API_KEY env var)",
    )
    inject_parser.add_argument(
        "--host",
        default=None,
        help="DevMemory REST server URL (default: http://localhost:8765)",
    )

    # ── devmemory watch ────────────────────────────────────────────────────
    watch_parser = subparsers.add_parser(
        "watch",
        help="Background daemon: auto-save Cursor/Cline/Kilo conversations",
        description=(
            "Tail local conversation stores of tools that don't pass a transcript "
            "to a hook (Cursor, Cline, Kilo) and push new turns to DevMemory, so "
            "context is saved without the model calling save_context."
        ),
    )
    watch_parser.add_argument(
        "--interval",
        type=int,
        default=30,
        help="Seconds between polls (default: 30)",
    )
    watch_parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single poll and exit (useful for testing / cron)",
    )
    watch_parser.add_argument(
        "--list",
        action="store_true",
        help="Show per-tool support status and which stores are present, then exit",
    )
    watch_parser.add_argument(
        "--install-service",
        action="store_true",
        help="Install + start watch as a background service (systemd/launchd), then exit",
    )

    # ── devmemory start / continue / stop / status ─────────────────────────
    # The attach model: auto-save is scoped to one chosen project at a time.
    for name, help_text in (
        ("start", "Attach this tool to a project, restore its context, begin auto-saving"),
        ("continue", "Re-attach the active project to a new tool and resume auto-saving"),
    ):
        p = subparsers.add_parser(name, help=help_text)
        p.add_argument("--cwd", default=None, help="Project directory (default: current)")
        p.add_argument("--tool", default=None, help="Tool being attached (e.g. cursor, claude)")
        p.add_argument("--host", default=None, help="Backend URL (persisted to config)")
        p.add_argument("--api-key", dest="api_key", default=None, help="API key (persisted)")

    subparsers.add_parser("stop", help="Detach (stop auto-saving) and stop the watch daemon")
    subparsers.add_parser("status", help="Show the active session and watch-daemon state")

    # ── Legacy flags (no subcommand = MCP or REST) ─────────────────────────
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

    if args.command == "install":
        from devmemory.cli.install import run_install

        run_install(args)
    elif args.command == "inject":
        from devmemory.cli.inject import run_inject

        run_inject(args)
    elif args.command == "watch":
        import sys as _sys

        if args.list:
            from devmemory.watch.capabilities import render_status

            print(render_status())
            _sys.exit(0)

        if args.install_service:
            import os as _os

            from devmemory.watch.service import install_service

            ok, msg = install_service(host=_os.environ.get("DEVMEMORY_HOST"))
            print(("✅ " if ok else "❌ ") + msg)
            _sys.exit(0 if ok else 1)

        from devmemory.watch.daemon import run as run_watch

        _sys.exit(run_watch(interval=args.interval, once=args.once))
    elif args.command in ("start", "continue", "stop", "status"):
        from devmemory.cli import session

        {
            "start": session.run_start,
            "continue": session.run_continue,
            "stop": session.run_stop,
            "status": session.run_status,
        }[args.command](args)
    elif args.rest:
        run_rest(host=args.host, port=args.port)
    else:
        run_mcp()


if __name__ == "__main__":
    run()
