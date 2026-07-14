"""Resolve which project a tool conversation belongs to.

A conversation carries absolute file/folder paths it touched. We pick the most
likely project directory from them, walk up to the nearest git root, and derive
the SAME slug the REST server derives from a git remote — so blocks saved by the
watcher land on the same project as blocks saved by the MCP client or hooks.

Mirrors ``devmemory.resolver.git_resolver`` / the hooks' ``_common.py`` slug
logic, kept sync and dependency-free for the daemon.
"""

from __future__ import annotations

import re
import subprocess
from collections import Counter
from pathlib import Path

# Paths under these dirs are tooling noise, not the user's project.
_NOISE = ("/.cursor", "/.config", "/.vscode", "/.codeium", "/node_modules", "/.git/")


def _slugify_name(name: str) -> str:
    slug = re.sub(r"[^a-z0-9-]", "-", name.lower().strip())
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
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
    ssh = re.match(r"^[\w.-]+@[\w.-]+:(.+)$", cleaned)
    if ssh:
        return _slugify_path_segments(ssh.group(1))
    cleaned = re.sub(r"^https?://", "", cleaned)
    parts = cleaned.split("/", 1)
    return _slugify_path_segments(parts[1] if len(parts) == 2 else parts[0])


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


def _clean(paths: list[str]) -> list[str]:
    out = []
    for p in paths:
        if p.startswith("file://"):
            p = p[len("file://") :]
        if not p.startswith("/"):
            continue
        if any(n in p for n in _NOISE):
            continue
        out.append(p)
    return out


def _pick_dir(paths: list[str]) -> Path | None:
    """Choose the most representative project directory from touched paths."""
    cleaned = _clean(paths)
    if not cleaned:
        return None
    # Prefer the git root shared by the most paths.
    roots: Counter[str] = Counter()
    for p in cleaned:
        root = _find_git_root(Path(p))
        if root is not None:
            roots[str(root)] += 1
    if roots:
        return Path(roots.most_common(1)[0][0])
    # No git root: use the most common existing directory.
    dirs = Counter(str(Path(p) if Path(p).is_dir() else Path(p).parent) for p in cleaned)
    return Path(dirs.most_common(1)[0][0])


def resolve_project(
    paths: list[str], fallback_name: str, remote_url: str | None = None
) -> dict | None:
    """Return ``{'slug','name','remote_url'}`` for the conversation, or None.

    Identity is the **project folder name** — the git root dir of the paths the
    conversation touched, else that dir's name. Git-remote slugging was dropped
    (flaky lookups forked one repo into two projects). ``remote_url`` is accepted
    for compatibility but no longer drives the slug.

    None means "couldn't tie this conversation to a real directory" — the daemon
    then skips it rather than filing it under a bogus project.
    """
    directory = _pick_dir(paths)
    if directory is None:
        # Last resort: derive a project from the conversation title so the work
        # is still captured, namespaced so it's obvious it's untethered.
        name = fallback_name.strip() or "untitled"
        return {"slug": f"cursor-{_slugify_name(name)}", "name": name, "remote_url": None}

    git_root = _find_git_root(directory)
    dir_name = git_root.name if git_root is not None else directory.name
    return {"slug": _slugify_name(dir_name), "name": dir_name, "remote_url": None}
