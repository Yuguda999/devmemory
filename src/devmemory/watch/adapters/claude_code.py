"""Claude Code adapter.

Claude Code (Anthropic's CLI agent) records each session as a JSONL transcript
under ``~/.claude/projects/<slugged-cwd>/<sessionId>.jsonl``. One line per event;
the events we care about are ``type: "user"`` / ``type: "assistant"``, each with
a nested ``message`` (``{role, content}``) and a top-level ``cwd`` / ``gitBranch``.

``content`` is a plain string for user turns and a list of typed blocks
(``text`` / ``tool_use`` / ``thinking``) for assistant turns — we keep only the
human-readable ``text`` blocks. Sidechain events (sub-agent internals) are
skipped so only the main conversation is saved.

Each transcript file is one conversation; its ``id`` is the file path so the
watermark is stable across polls.
"""

from __future__ import annotations

import glob
import json
from collections.abc import Iterator
from pathlib import Path

from devmemory.watch.adapters.base import Adapter
from devmemory.watch.models import Conversation, Message

_ROLES = ("user", "assistant")


def _projects_dir() -> Path:
    return Path.home() / ".claude" / "projects"


def _content_text(content) -> str:
    """Pull human-readable text out of a Claude message ``content`` field.

    User turns are plain strings; assistant turns are lists of typed blocks —
    we keep only ``text`` blocks (dropping tool_use / tool_result / thinking).
    """
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text" or ("text" in block and "type" not in block):
                    parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(p for p in parts if p).strip()
    return ""


def _message_from_line(obj: dict) -> Message | None:
    """Extract a user/assistant Message from one transcript line, if any."""
    if obj.get("type") not in _ROLES:
        return None
    if obj.get("isSidechain"):
        return None  # sub-agent internal turn, not the main conversation
    msg = obj.get("message")
    if not isinstance(msg, dict):
        return None
    role = msg.get("role")
    if role not in _ROLES:
        return None
    text = _content_text(msg.get("content"))
    if not text:
        return None
    return Message(role=role, text=text)


class ClaudeCodeAdapter(Adapter):
    name = "claude-code"

    def __init__(self, projects_dir: Path | None = None) -> None:
        # Explicit dir for tests; otherwise the real store.
        self._dir = projects_dir or _projects_dir()

    def _files(self) -> list[str]:
        return sorted(glob.glob(str(self._dir / "*" / "*.jsonl")))

    def available(self) -> bool:
        return self._dir.is_dir() and bool(self._files())

    def conversations(self) -> Iterator[Conversation]:
        for file_path in self._files():
            conv = self._build(file_path)
            if conv is not None and conv.messages:
                yield conv

    def _build(self, file_path: str) -> Conversation | None:
        messages: list[Message] = []
        cwds: list[str] = []
        branch: str | None = None
        try:
            with open(file_path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except ValueError:
                        continue
                    if not isinstance(obj, dict):
                        continue
                    cwd = obj.get("cwd")
                    if isinstance(cwd, str) and cwd and cwd not in cwds:
                        cwds.append(cwd)
                    if branch is None and isinstance(obj.get("gitBranch"), str):
                        branch = obj["gitBranch"] or None
                    msg = _message_from_line(obj)
                    if msg is not None:
                        messages.append(msg)
        except OSError:
            return None

        title = self._title(messages) or Path(file_path).stem[:120]
        return Conversation(
            tool=self.name,
            id=file_path,
            title=title,
            messages=messages,
            paths=cwds,
        )

    @staticmethod
    def _title(messages: list[Message]) -> str | None:
        """First user line makes a decent conversation title."""
        for msg in messages:
            if msg.role == "user" and msg.text:
                return msg.text.splitlines()[0][:120]
        return None
