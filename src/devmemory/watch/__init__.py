"""DevMemory watch — background auto-save for tools that don't expose transcripts.

Claude Code passes a conversation transcript to its Stop hook, so a shell hook
can save every turn with zero model cooperation. Most other tools (Cursor,
Cline, Kilo, …) don't — but they DO persist conversations to a local store on
disk. ``devmemory watch`` is a lightweight polling daemon that tails those
stores and pushes new turns to the DevMemory backend, so cross-tool continuity
no longer depends on the model remembering to call ``save_context``.

Each supported tool has an :class:`~devmemory.watch.adapters.base.Adapter` that
knows how to read that tool's store and yield :class:`~devmemory.watch.models.Conversation`
objects. The daemon diffs them against a watermark and saves only new messages.
"""
