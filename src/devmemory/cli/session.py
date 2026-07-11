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
    resolve_project,
    write_active,
    write_config,
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


def run_start(args) -> None:
    _persist_conn(args)
    cwd = getattr(args, "cwd", None) or os.getcwd()
    tool = getattr(args, "tool", None) or "unknown"
    proj = resolve_project(cwd)
    marker = write_active(proj, tool)
    print(f"▶️  DevMemory attached to '{marker['name']}' ({marker['slug']}) via {tool}.")
    print(f"   Backend: {resolve_host()}")
    _restore(cwd, tool)
    pid = _spawn_daemon()
    if pid:
        print(f"   Watch daemon running (pid {pid}). Auto-save is ON for this project only.")
    print("   Switch tools later with: devmemory continue")


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
    if pid:
        print(f"   Watch daemon running (pid {pid}).")


def run_stop(args) -> None:
    active = read_active()
    clear_active()
    stopped = _stop_daemon()
    if active:
        print(f"⏹️  Detached from '{active['name']}' ({active['slug']}). Auto-save OFF.")
    else:
        print("⏹️  No active session.")
    if stopped:
        print("   Watch daemon stopped.")


def run_status(args) -> None:
    active = read_active()
    if active is None:
        print("DevMemory: no active session. Run `devmemory start` to attach.")
        return
    pid = _daemon_running()
    daemon = f"running (pid {pid})" if pid else "not running"
    print("DevMemory active session:")
    print(f"  project : {active['name']} ({active['slug']})")
    print(f"  tool    : {active.get('tool', 'unknown')}")
    print(f"  backend : {resolve_host()}")
    print(f"  since   : {active.get('started_at', '?')}")
    print(f"  daemon  : {daemon}")
