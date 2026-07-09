"""Claude Code hook scripts shipped with DevMemory.

These are standalone, stdlib-only scripts (not imported as modules) that
``devmemory install --tool claude-code`` copies into ``~/.devmemory/hooks/`` and
wires into ``~/.claude/settings.json``:

- ``session_start.py`` — SessionStart: inject restored context for the project.
- ``stop_save.py``      — Stop: snapshot each turn so nothing is lost even if the
  model never calls ``save_context``.
- ``_common.py``        — shared helpers (project slug resolution, HTTP, logging).

They run under the tool's own Python (``python3 <path>``), so they must not
import anything from the installed ``devmemory`` package.
"""
