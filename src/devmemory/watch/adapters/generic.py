"""Config-driven generic adapter for JSONL conversation stores.

Lets a user add support for ANY tool that logs conversations as JSONL — one
message (or a nested message) per line — without writing code. Point it at a
glob and describe where the role and text live.

Config lives at ``~/.devmemory/watch_adapters.json``::

    {
      "adapters": [
        {
          "name": "gemini-cli",
          "glob": "~/.gemini/tmp/**/chat-*.jsonl",
          "role_field": "role",
          "text_field": "content",
          "user_values": ["user"],
          "assistant_values": ["model", "assistant"],
          "cwd_field": "cwd"
        }
      ]
    }

``role_field`` / ``text_field`` / ``cwd_field`` support dotted paths
(``payload.role``). Each matching file is one conversation; its ``id`` is the
file path so the watermark is stable.
"""

from __future__ import annotations

import glob
import json
from collections.abc import Iterator
from pathlib import Path

from devmemory.watch.adapters.base import Adapter
from devmemory.watch.models import Conversation, Message

_CONFIG_PATH = Path.home() / ".devmemory" / "watch_adapters.json"


def _dig(obj, dotted: str):
    """Follow a dotted path through nested dicts; return None if absent."""
    cur = obj
    for part in dotted.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _as_text(value) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts = []
        for block in value:
            if isinstance(block, dict) and "text" in block:
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(p for p in parts if p).strip()
    return ""


class GenericJsonlAdapter(Adapter):
    def __init__(self, spec: dict) -> None:
        self.name = spec.get("name") or "generic"
        self._glob = str(spec.get("glob", "")).replace("~", str(Path.home()))
        self._role_field = spec.get("role_field", "role")
        self._text_field = spec.get("text_field", "content")
        self._cwd_field = spec.get("cwd_field")
        self._user_values = {v.lower() for v in spec.get("user_values", ["user"])}
        self._assistant_values = {
            v.lower() for v in spec.get("assistant_values", ["assistant", "model"])
        }

    def _files(self) -> list[str]:
        if not self._glob:
            return []
        return sorted(glob.glob(self._glob, recursive=True))

    def available(self) -> bool:
        return bool(self._files())

    def _role(self, raw) -> str | None:
        if not isinstance(raw, str):
            return None
        low = raw.lower()
        if low in self._user_values:
            return "user"
        if low in self._assistant_values:
            return "assistant"
        return None

    def conversations(self) -> Iterator[Conversation]:
        for file_path in self._files():
            conv = self._build(file_path)
            if conv is not None and conv.messages:
                yield conv

    def _build(self, file_path: str) -> Conversation | None:
        messages: list[Message] = []
        paths: list[str] = []
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
                    role = self._role(_dig(obj, self._role_field))
                    if role is None:
                        continue
                    text = _as_text(_dig(obj, self._text_field))
                    if not text:
                        continue
                    if self._cwd_field:
                        cwd = _dig(obj, self._cwd_field)
                        if isinstance(cwd, str) and cwd:
                            paths.append(cwd)
                    messages.append(Message(role=role, text=text))
        except OSError:
            return None
        return Conversation(
            tool=self.name,
            id=file_path,
            title=Path(file_path).stem[:120],
            messages=messages,
            paths=paths,
        )


def load_specs(config_path: Path | None = None) -> list[dict]:
    path = config_path or _CONFIG_PATH
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    specs = data.get("adapters") if isinstance(data, dict) else None
    return [s for s in specs if isinstance(s, dict)] if isinstance(specs, list) else []


def generic_adapters(config_path: Path | None = None) -> list[GenericJsonlAdapter]:
    return [GenericJsonlAdapter(spec) for spec in load_specs(config_path)]
