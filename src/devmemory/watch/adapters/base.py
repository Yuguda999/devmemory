"""Adapter contract: one per supported tool."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator

from devmemory.watch.models import Conversation


class Adapter(ABC):
    #: Short stable id, e.g. "cursor". Used as the watermark namespace.
    name: str = ""

    @abstractmethod
    def available(self) -> bool:
        """True if this tool's store exists on this machine."""

    @abstractmethod
    def conversations(self) -> Iterator[Conversation]:
        """Yield current conversations (with full message lists).

        Must be safe to call repeatedly. Should never raise for a single bad
        conversation — skip it and continue.
        """
