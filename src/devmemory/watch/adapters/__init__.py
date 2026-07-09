"""Adapter registry."""

from __future__ import annotations

from devmemory.watch.adapters.base import Adapter
from devmemory.watch.adapters.cline import ClineAdapter, KiloAdapter
from devmemory.watch.adapters.codex import CodexAdapter
from devmemory.watch.adapters.cursor import CursorAdapter
from devmemory.watch.adapters.generic import generic_adapters

# All known adapters. The daemon instantiates each and skips the ones whose
# store isn't present (``available() == False``).
ALL_ADAPTERS: list[type[Adapter]] = [CursorAdapter, ClineAdapter, KiloAdapter, CodexAdapter]


def available_adapters() -> list[Adapter]:
    adapters: list[Adapter] = []
    for cls in ALL_ADAPTERS:
        try:
            inst = cls()
        except Exception:
            continue
        if inst.available():
            adapters.append(inst)
    # User-defined generic adapters (from ~/.devmemory/watch_adapters.json).
    for inst in generic_adapters():
        if inst.available():
            adapters.append(inst)
    return adapters


__all__ = [
    "Adapter",
    "CursorAdapter",
    "ClineAdapter",
    "KiloAdapter",
    "CodexAdapter",
    "available_adapters",
    "generic_adapters",
]
