"""On-demand sync — scan local tool stores once and push new turns.

This is the daemon's poll loop reduced to a single pass, callable synchronously
from anywhere (MCP tools, CLI). It's how DevMemory captures conversations WITHOUT
a persistent background process: every tool already calls ``continue_here`` at
session start, and that call triggers one scoped sync of the local disk stores.

The daemon (``devmemory watch``) remains an optional opt-in for users who want
near-real-time push instead of capture-on-next-attach.
"""

from __future__ import annotations

from devmemory.watch.adapters import available_adapters
from devmemory.watch.client import Client, api_key
from devmemory.watch.daemon import poll_once
from devmemory.watch.state import WatchState


def sync_now(scope_slug: str | None = None, key: str | None = None) -> int:
    """Run ONE scan of every local tool store and push new turns to the backend.

    Args:
        scope_slug: If given, only conversations resolving to this project are
                    saved; every other project's watermark is left untouched, so
                    a later call (scoped or not) still captures them. On-demand
                    callers pass the project they just attached to.
        key:        API key. Falls back to DEVMEMORY_API_KEY / ~/.devmemory/api_key.

    Returns the number of blocks saved. Never raises — a failed sync must never
    break the caller (e.g. a restore). Returns 0 when there's no key, no adapter,
    or anything goes wrong mid-scan.
    """
    key = key or api_key()
    if not key:
        return 0
    adapters = available_adapters()
    if not adapters:
        return 0

    state = WatchState()
    client = Client(key)
    try:
        return poll_once(adapters, state, client, scope_slug=scope_slug)
    except Exception:  # noqa: BLE001 — on-demand sync is strictly best-effort
        return 0
    finally:
        client.close()
