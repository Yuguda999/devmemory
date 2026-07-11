"""Shared helpers for DevMemory Claude Code hooks.

No third-party deps — stdlib only. Mirrors devmemory's own
``resolve_project_slug`` so blocks saved by the Stop hook and context loaded by
the SessionStart hook resolve to the SAME project the REST server derives from
``cwd``. Never raises to the caller: hooks must not break tool startup/shutdown.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path

DEFAULT_HOST = "https://devmemory.onrender.com"

# One global config so every command (start/continue/inject/watch/install) knows
# the backend URL + key without re-passing flags or setting env vars. Resolution
# order is always: explicit arg → env var → this file → built-in default.
CONFIG_PATH = Path.home() / ".devmemory" / "config.json"


def read_config() -> dict:
    """Return the persisted config, or {} if none / unreadable."""
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def write_config(**kv) -> dict:
    """Merge the given keys into the config file (None values ignored)."""
    cfg = read_config()
    cfg.update({k: v for k, v in kv.items() if v is not None})
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    tmp.replace(CONFIG_PATH)
    return cfg


def host() -> str:
    """Resolve backend URL: env → config.json → default."""
    h = os.environ.get("DEVMEMORY_HOST") or read_config().get("host") or DEFAULT_HOST
    return h.rstrip("/")


def api_key() -> str | None:
    """Resolve API key: env → ~/.devmemory/api_key → config.json."""
    key = os.environ.get("DEVMEMORY_API_KEY")
    if key:
        return key.strip()
    key_file = Path.home() / ".devmemory" / "api_key"
    try:
        file_key = key_file.read_text(encoding="utf-8").strip()
        if file_key:
            return file_key
    except OSError:
        pass
    return read_config().get("api_key") or None


# ── Active-session marker ──────────────────────────────────────────────────────
#
# One global marker names the single project auto-save is currently attached to.
# Both the watch daemon and the deterministic hooks consult it, so auto-save is
# strictly opt-in: nothing is saved until the user runs ``devmemory start``.
# ``devmemory continue`` re-points the marker at a new tool (same project);
# ``devmemory stop`` clears it. Kept here (stdlib-only, copied alongside the
# hooks) so hook scripts and the daemon share one implementation.

ACTIVE_PATH = Path.home() / ".devmemory" / "active.json"


def read_active() -> dict | None:
    """Return the active-session marker, or None if no session is active."""
    try:
        data = json.loads(ACTIVE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and data.get("slug") else None


def write_active(project: dict, tool: str) -> dict:
    """Point the active session at ``project``, attached to ``tool``.

    Preserves ``started_at`` when the same project is already active, so a
    ``continue`` to a new tool keeps the original session start time.
    """
    import datetime

    current = read_active()
    if current and current.get("slug") == project.get("slug"):
        started = current.get("started_at")
    else:
        started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    marker = {
        "slug": project.get("slug"),
        "name": project.get("name"),
        "remote_url": project.get("remote_url"),
        "tool": tool,
        "started_at": started,
    }
    ACTIVE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = ACTIVE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(marker, indent=2) + "\n", encoding="utf-8")
    tmp.replace(ACTIVE_PATH)
    return marker


def set_active_tool(tool: str) -> dict | None:
    """Re-point the current active session at ``tool``. No-op if none active."""
    current = read_active()
    if current is None:
        return None
    return write_active(current, tool)


def clear_active() -> None:
    import contextlib

    with contextlib.suppress(OSError):
        ACTIVE_PATH.unlink()


def should_save(slug: str) -> bool:
    """Strict opt-in gate: only save when ``slug`` is the active project.

    No active marker → False (nothing is saved until ``devmemory start``).
    """
    active = read_active()
    return bool(active and active.get("slug") == slug)


# ── Project slug resolution (ported from devmemory.resolver.git_resolver) ──────


def _slugify_name(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9-]", "-", slug)
    slug = re.sub(r"-{2,}", "-", slug)
    slug = slug.strip("-")
    return slug or "unnamed"


def _slugify_path_segments(path: str) -> str:
    segments = [s for s in path.split("/") if s]
    if len(segments) >= 2:
        raw = f"{segments[-2]}-{segments[-1]}"
    elif segments:
        raw = segments[0]
    else:
        return "unnamed"
    return _slugify_name(raw)


def slugify_remote_url(url: str) -> str:
    cleaned = url.strip()
    if cleaned.endswith(".git"):
        cleaned = cleaned[:-4]
    cleaned = cleaned.rstrip("/")
    ssh_match = re.match(r"^[\w.-]+@[\w.-]+:(.+)$", cleaned)
    if ssh_match:
        return _slugify_path_segments(ssh_match.group(1))
    cleaned = re.sub(r"^https?://", "", cleaned)
    parts = cleaned.split("/", 1)
    path_part = parts[1] if len(parts) == 2 else parts[0]
    return _slugify_path_segments(path_part)


def _find_git_root(path: Path) -> Path | None:
    current = path if path.is_dir() else path.parent
    while True:
        if (current / ".git").exists():
            return current
        parent = current.parent
        if parent == current:
            return None
        current = parent


def _git_remote(git_root: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=str(git_root),
            capture_output=True,
            timeout=5,
            text=True,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def resolve_project(cwd: str) -> dict:
    """Return {'slug','name','remote_url'} matching the server's resolution."""
    cwd_path = Path(cwd).resolve()
    git_root = _find_git_root(cwd_path)
    if git_root is not None:
        remote = _git_remote(git_root)
        if remote:
            slug = slugify_remote_url(remote)
            name = slug.split("-", 1)[-1] if "-" in slug else slug
            return {"slug": slug, "name": name, "remote_url": remote}
        dir_name = git_root.name
        return {"slug": _slugify_name(dir_name), "name": dir_name, "remote_url": None}
    dir_name = cwd_path.name or "unnamed"
    return {"slug": _slugify_name(dir_name), "name": dir_name, "remote_url": None}


# ── HTTP ───────────────────────────────────────────────────────────────────────


def http_get(path: str, params: dict, key: str, timeout: int = 8):
    url = f"{host()}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"X-API-Key": key})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def http_post(path: str, payload: dict, key: str, timeout: int = 8):
    url = f"{host()}{path}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"X-API-Key": key, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def read_stdin_json() -> dict:
    import sys

    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except (ValueError, OSError):
        return {}


LOG_FILE = Path.home() / ".devmemory" / "hooks" / "hook.log"


def log(hook_name: str, detail: dict) -> None:
    """Best-effort breadcrumb so silent hook failures are debuggable. Never raises."""
    import datetime

    try:
        entry = {
            "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "hook": hook_name,
            **detail,
        }
        with open(LOG_FILE, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
    except Exception:
        pass
