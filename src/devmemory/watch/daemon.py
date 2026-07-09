"""The watch poll loop.

Every ``interval`` seconds: ask each available adapter for its conversations,
diff each against the saved watermark, and push new turns to the DevMemory API.
State is persisted after every conversation so a crash never loses more than the
turn in flight (and never re-saves an old one).
"""

from __future__ import annotations

import sys
import time

from devmemory.watch.adapters import Adapter, available_adapters
from devmemory.watch.client import Client, api_key
from devmemory.watch.models import Conversation, Message
from devmemory.watch.project import resolve_project
from devmemory.watch.state import WatchState

USER_CAP = 1500
ASSISTANT_CAP = 3000
DEFAULT_INTERVAL = 30


def _exchanges(messages: list[Message]) -> list[str]:
    """Group an ordered message list into 'User asked / Assistant response' blocks.

    Consecutive same-role messages are concatenated. Each assistant turn closes
    one block together with the user text that preceded it.
    """
    blocks: list[str] = []
    pending_user: list[str] = []
    pending_assistant: list[str] = []

    def flush() -> None:
        if not pending_assistant and not pending_user:
            return
        user = "\n".join(pending_user).strip()[:USER_CAP]
        assistant = "\n".join(pending_assistant).strip()[:ASSISTANT_CAP]
        parts = []
        if user:
            parts.append(f"User asked:\n{user}")
        if assistant:
            parts.append(f"Assistant response:\n{assistant}")
        if parts:
            blocks.append("\n\n".join(parts))
        pending_user.clear()
        pending_assistant.clear()

    for msg in messages:
        if msg.role == "assistant":
            pending_assistant.append(msg.text)
        else:  # user turn — a new user turn after an assistant reply starts a new block
            if pending_assistant:
                flush()
            pending_user.append(msg.text)
    flush()
    return blocks


def _log(msg: str) -> None:
    print(f"[devmemory watch] {msg}", file=sys.stderr, flush=True)


def _process(conv: Conversation, state: WatchState, client: Client) -> int:
    """Save new turns of one conversation. Returns number of blocks saved."""
    already = state.saved_count(conv.key())
    if len(conv.messages) <= already:
        return 0

    new_messages = conv.messages[already:]
    blocks = _exchanges(new_messages)
    if not blocks:
        # Consumed messages produced no saveable block (e.g. all empty) — still
        # advance the watermark so we don't re-scan them forever.
        state.record(conv.key(), len(conv.messages), state.session_id(conv.key()))
        return 0

    project = resolve_project(conv.paths, fallback_name=conv.title, remote_url=conv.remote_url)
    if project is None:
        return 0

    session_id = state.session_id(conv.key())
    saved = 0
    for block in blocks:
        content = f"[{conv.tool}] {conv.title}\n\n{block}"
        try:
            session_id = client.save_block(project, content, session_id=session_id) or session_id
            saved += 1
        except Exception as exc:  # network/backend/quota — stop this conv, keep watermark honest
            _log(f"save failed for {conv.key()}: {exc}")
            break

    # Advance watermark only by the messages whose blocks we actually saved.
    # Simplest correct rule: if every block saved, consume all; else leave the
    # unsaved tail for the next poll.
    if saved == len(blocks):
        state.record(conv.key(), len(conv.messages), session_id)
    else:
        state.record(conv.key(), already, session_id)
    state.save()
    return saved


def poll_once(adapters: list[Adapter], state: WatchState, client: Client) -> int:
    total = 0
    for adapter in adapters:
        try:
            convs = list(adapter.conversations())
        except Exception as exc:
            _log(f"adapter {adapter.name} failed: {exc}")
            continue
        for conv in convs:
            try:
                total += _process(conv, state, client)
            except Exception as exc:
                _log(f"error processing {conv.key()}: {exc}")
    return total


def run(interval: int = DEFAULT_INTERVAL, once: bool = False) -> int:
    key = api_key()
    if not key:
        _log("no API key. Set DEVMEMORY_API_KEY or run `devmemory install`.")
        return 1

    adapters = available_adapters()
    if not adapters:
        _log("no supported tool stores found on this machine (Cursor/Cline/Kilo).")
        return 1

    _log(f"watching: {', '.join(a.name for a in adapters)} (interval {interval}s)")
    state = WatchState()
    client = Client(key)
    try:
        while True:
            saved = poll_once(adapters, state, client)
            if saved:
                _log(f"saved {saved} new block(s)")
            if once:
                break
            time.sleep(interval)
    except KeyboardInterrupt:
        _log("stopped")
    finally:
        client.close()
    return 0
