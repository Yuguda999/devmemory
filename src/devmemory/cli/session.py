"""``devmemory start | continue | stop | status`` — the attach model.

One global marker (``~/.devmemory/active.json``) names the single project
auto-save is attached to. Both the watch daemon and the deterministic hooks
consult it, so nothing is saved until the user attaches:

- ``start``    — attach the current tool to a project (resolved from the working
                 dir), restore its saved context, and begin saving. Runs until
                 stopped — long idle gaps are fine.
- ``continue`` — re-attach the already-active project to a new tool, restore its
                 context there, and resume saving from that tool.
- ``stop``     — detach (clear the marker) and stop the watch daemon.
- ``status``   — show the active session and daemon state.

The marker + gate live in :mod:`devmemory.hooks._common` (shared with the hooks).
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from devmemory.cli.inject import run_inject
from devmemory.hooks._common import (
    clear_active,
    read_active,
    read_paused,
    resolve_project,
    write_active,
    write_config,
    write_paused,
)
from devmemory.hooks._common import (
    host as resolve_host,
)

PID_FILE = Path.home() / ".devmemory" / "watch.pid"
DAEMON_LOG = Path.home() / ".devmemory" / "watch.log"


# ── Watch-daemon process management ─────────────────────────────────────────────


def _daemon_running() -> int | None:
    """Return the daemon PID if a live one is recorded, else None."""
    try:
        pid = int(PID_FILE.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    try:
        os.kill(pid, 0)
    except OSError:
        return None
    return pid


def _spawn_daemon() -> int | None:
    """Start the watch daemon detached, if not already running. Returns its PID."""
    existing = _daemon_running()
    if existing:
        return existing
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    logf = open(DAEMON_LOG, "a", encoding="utf-8")  # noqa: SIM115 — kept open for the child
    proc = subprocess.Popen(
        [sys.executable, "-m", "devmemory.server", "watch"],
        stdin=subprocess.DEVNULL,
        stdout=logf,
        stderr=logf,
        start_new_session=True,
        env=os.environ.copy(),
    )
    PID_FILE.write_text(str(proc.pid) + "\n", encoding="utf-8")
    return proc.pid


def _stop_daemon() -> bool:
    """Stop the recorded daemon. Returns True if one was running."""
    pid = _daemon_running()
    PID_FILE.unlink(missing_ok=True)
    if pid is None:
        return False
    with contextlib.suppress(OSError):
        os.kill(pid, signal.SIGTERM)
    return True


# ── Restore ─────────────────────────────────────────────────────────────────────


def _restore(cwd: str, tool: str) -> None:
    """Load the project's saved context into this tool (best-effort, never raises)."""
    ns = SimpleNamespace(cwd=cwd, tool=tool, host=None, api_key=None)
    try:
        run_inject(ns)
    except SystemExit:
        pass  # run_inject exits 0 on soft failures (no key / no context / unreachable)
    except Exception as exc:  # noqa: BLE001 — restore must never break attach
        print(f"⚠️  restore skipped: {exc}", file=sys.stderr)


# ── Subcommands ──────────────────────────────────────────────────────────────────


def _persist_conn(args) -> None:
    """Persist --host / --api-key to the global config if given."""
    write_config(host=getattr(args, "host", None), api_key=getattr(args, "api_key", None))


def _print_save_notice(tool: str, pid: int | None) -> None:
    """Print an HONEST auto-save status for the attached tool.

    The daemon can only save tools with a tailable local store (or a tool-fired
    hook). MCP/rules tools (Antigravity, Claude Desktop) save only when the agent
    calls save_context/continue_here in-chat — saying "Auto-save is ON" for them
    would be a lie, and lying about what persists is exactly what DevMemory won't do.
    """
    from devmemory.watch.capabilities import save_mode

    mode = save_mode(tool)
    running = f"   Watch daemon running (pid {pid})." if pid else "   Watch daemon already running."
    if mode == "auto":
        print(f"{running} Auto-save is ON for this project only.")
    elif mode == "mcp":
        print(running)
        print(
            f"   ⚠️  {tool} has no tailable store or hook — the daemon can't auto-save it.\n"
            "   Saving happens in chat via DevMemory's MCP tools (save_context /\n"
            "   continue_here), driven by the rules file `devmemory install` wrote."
        )
    else:  # unknown tool (no --tool passed)
        print(f"{running} Auto-save is ON for store/hook tools")
        print("   (Claude Code, Cursor, Cline, Kilo, Codex, Windsurf).")
        print("   Antigravity / Claude Desktop / Augment save in chat via MCP tools instead.")
        print("   Pass --tool <name> for exact per-tool guidance.")


def run_start(args) -> None:
    _persist_conn(args)
    cwd = getattr(args, "cwd", None) or os.getcwd()
    tool = getattr(args, "tool", None) or "unknown"
    proj = resolve_project(cwd)
    # Auto-save is ON for every project by default now, so `start` mainly (a)
    # un-pauses this project if it was paused, (b) restores its context into the
    # tool, and (c) makes sure the watch daemon is up for store-based tools.
    paused = read_paused()
    if proj["slug"] in paused:
        paused.discard(proj["slug"])
        write_paused(paused)
        print(f"▶️  Auto-save resumed for '{proj['name']}' ({proj['slug']}).")
    else:
        print(f"▶️  DevMemory active for '{proj['name']}' ({proj['slug']}) via {tool}.")
    write_active(proj, tool)  # restore target + status metadata (not a save gate)
    print(f"   Backend: {resolve_host()}")
    _restore(cwd, tool)
    pid = _spawn_daemon()
    _print_save_notice(tool, pid)
    print("   Pause saving for this project with: devmemory stop")


def run_continue(args) -> None:
    _persist_conn(args)
    active = read_active()
    if active is None:
        print("❌ No active session. Run `devmemory start` in a project first.", file=sys.stderr)
        sys.exit(1)
    cwd = getattr(args, "cwd", None) or os.getcwd()
    tool = getattr(args, "tool", None) or "unknown"
    proj = {
        "slug": active["slug"],
        "name": active["name"],
        "remote_url": active.get("remote_url"),
    }
    marker = write_active(proj, tool)
    print(f"⏩ Continuing '{marker['name']}' ({marker['slug']}) in {tool}.")
    _restore(cwd, tool)
    pid = _spawn_daemon()
    _print_save_notice(tool, pid)


def run_stop(args) -> None:
    # Auto-save is global-on, so `stop` pauses THIS project only — other
    # projects keep saving and the daemon keeps running for them.
    cwd = getattr(args, "cwd", None) or os.getcwd()
    proj = resolve_project(cwd)
    paused = read_paused()
    paused.add(proj["slug"])
    write_paused(paused)
    active = read_active()
    if active and active.get("slug") == proj["slug"]:
        clear_active()
    print(f"⏹️  Auto-save paused for '{proj['name']}' ({proj['slug']}).")
    print("   Other projects still saving. Resume with: devmemory start")
    print("   Disable auto-save everywhere with: DEVMEMORY_AUTOSAVE=off")


def run_status(args) -> None:
    disabled = os.environ.get("DEVMEMORY_AUTOSAVE", "").strip().lower() in {"off", "0", "false", "no"}
    paused = read_paused()
    pid = _daemon_running()
    daemon = f"running (pid {pid})" if pid else "not running"
    print("DevMemory auto-save:")
    print(f"  auto-save : {'OFF (DEVMEMORY_AUTOSAVE)' if disabled else 'ON for every project'}")
    print(f"  paused    : {', '.join(sorted(paused)) if paused else '(none)'}")
    print(f"  backend   : {resolve_host()}")
    print(f"  daemon    : {daemon}")
    active = read_active()
    if active:
        print(f"  last tool : {active.get('tool', 'unknown')} — {active['name']} ({active['slug']})")
