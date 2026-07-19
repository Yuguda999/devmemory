"""Shared value types for the watch daemon."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Message:
    """One message in a tool conversation."""

    role: str  # "user" | "assistant"
    text: str


@dataclass
class Conversation:
    """A single conversation pulled from a tool's local store.

    ``id`` must be stable across polls for the same conversation so the daemon
    can track a watermark. ``paths`` are absolute file/folder paths the
    conversation touched — used to resolve which project it belongs to.
    """

    tool: str  # adapter name, e.g. "cursor"
    id: str  # stable per-conversation id within the tool
    title: str
    messages: list[Message] = field(default_factory=list)
    paths: list[str] = field(default_factory=list)
    #: Explicit git remote URL, if the tool records one (e.g. Codex). Preferred
    #: over path-based resolution because it slugs identically to the server.
    remote_url: str | None = None

    def key(self) -> str:
        """Namespaced watermark key: ``<tool>:<id>``."""
        return f"{self.tool}:{self.id}"
