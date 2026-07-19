"""Cline / Kilo Code adapter.

Cline (VS Code extension ``saoudrizwan.claude-dev``) stores each task as a
folder under ``globalStorage/<ext-id>/tasks/<taskId>/`` containing
``api_conversation_history.json`` — a list of Anthropic-format messages
(``{"role": "user"|"assistant", "content": str | [blocks]}``).

Kilo Code is a Cline/Roo fork with the same on-disk shape, only a different
extension id — so it's just this adapter pointed at a different directory.

The user's working directory is embedded in Cline's ``environment_details``
blocks as ``# Current Working Directory (/abs/path) Files``; we scrape it to
resolve the project.
"""

from __future__ import annotations

import json
import platform
import re
from collections.abc import Iterator
from pathlib import Path

from devmemory.watch.adapters.base import Adapter
from devmemory.watch.models import Conversation, Message

# VS Code global-storage roots per OS. Cursor-hosted Cline would differ, but the
# common install is stock VS Code.
_CODE_USER = {
    "Linux": "~/.config/Code/User/globalStorage",
    "Darwin": "~/Library/Application Support/Code/User/globalStorage",
    "Windows": "~/AppData/Roaming/Code/User/globalStorage",
}

_CWD_RE = re.compile(r"Current Working Directory \(([^)]+)\)")


def _storage_root() -> Path:
    template = _CODE_USER.get(platform.system(), _CODE_USER["Linux"])
    return Path(template.replace("~", str(Path.home())))


def _content_text(content) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(p for p in parts if p).strip()
    return ""


class ClineAdapter(Adapter):
    name = "cline"
    # Extension id whose tasks/ dir we read.
    ext_id = "saoudrizwan.claude-dev"

    def __init__(self, tasks_dir: Path | None = None) -> None:
        self._tasks_dir = tasks_dir or (_storage_root() / self.ext_id / "tasks")

    def available(self) -> bool:
        return self._tasks_dir.is_dir()

    def conversations(self) -> Iterator[Conversation]:
        if not self._tasks_dir.is_dir():
            return
        for task_dir in sorted(self._tasks_dir.iterdir()):
            hist = task_dir / "api_conversation_history.json"
            if not hist.is_file():
                continue
            conv = self._build(task_dir.name, hist)
            if conv is not None and conv.messages:
                yield conv

    def _build(self, task_id: str, hist: Path) -> Conversation | None:
        try:
            raw = json.loads(hist.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(raw, list):
            return None

        messages: list[Message] = []
        paths: list[str] = []
        title = ""
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            role = entry.get("role")
            if role not in ("user", "assistant"):
                continue
            text = _content_text(entry.get("content"))
            if not text:
                continue
            for m in _CWD_RE.findall(text):
                paths.append(m.strip())
            # Cline pads user turns with big environment_details blocks; strip
            # them so saved content is just the human/assistant prose.
            clean = re.split(r"<environment_details>", text, maxsplit=1)[0].strip()
            if not clean:
                continue
            if role == "user" and not title:
                title = clean[:120]
            messages.append(Message(role=role, text=clean))

        return Conversation(
            tool=self.name,
            id=task_id,
            title=title or f"{self.name} task {task_id}",
            messages=messages,
            paths=paths,
        )


class KiloAdapter(ClineAdapter):
    name = "kilo"
    ext_id = "kilocode.kilo-code"
