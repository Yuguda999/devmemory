"""Git-based project resolver.

Resolves a working directory to a project identity by reading git metadata.
Priority: explicit project name → git remote URL → git root dir name → cwd basename.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProjectInfo:
    """Resolved project identity."""

    slug: str
    name: str
    remote_url: str | None = None


# ── Public API ─────────────────────────────────────────────────


async def resolve_project_slug(
    cwd: str,
    explicit_project: str | None = None,
) -> ProjectInfo:
    """Resolve a working directory to a project identity.

    Identity is the **project folder name** — simple and stable within a machine
    (you always open the same folder). We deliberately do NOT slug off the git
    remote: remote lookup is flaky (git missing/timeout, subdir cwd, pre-remote
    history), and a single flaky miss forked one repo into two projects
    (``owner-repo`` vs ``repo``). Folder name has no such failure mode.

    Resolution priority:
        1. Explicit project name (if provided by the agent).
        2. Git repository root directory name (walks up from cwd).
        3. Working directory basename (if not inside a git repo at all).

    Args:
        cwd: The working directory path passed by the AI tool.
        explicit_project: Optional explicit project name override.

    Returns:
        A :class:`ProjectInfo` with the resolved slug and display name.
    """
    # 1. Explicit override — use it directly.
    if explicit_project:
        slug = _slugify_name(explicit_project)
        return ProjectInfo(slug=slug, name=explicit_project)

    cwd_path = Path(cwd).resolve()

    # 2. Git root folder name (so a subdir still maps to the repo, not the subdir).
    git_root = _find_git_root(cwd_path)
    dir_name = (git_root.name if git_root is not None else cwd_path.name) or "unnamed"
    return ProjectInfo(slug=_slugify_name(dir_name), name=dir_name)


# ── URL Slugification ─────────────────────────────────────────


def slugify_remote_url(url: str) -> str:
    """Convert a git remote URL to a URL-safe project slug.

    Handles multiple URL formats:
        - HTTPS: ``https://github.com/user/repo.git`` → ``user-repo``
        - SSH:   ``git@github.com:user/repo.git``     → ``user-repo``
        - Plain: ``github.com/user/repo``              → ``user-repo``

    The slug is ``owner-repo`` with special characters stripped and
    normalised to lowercase.
    """
    cleaned = url.strip()

    # Strip trailing .git
    if cleaned.endswith(".git"):
        cleaned = cleaned[:-4]

    # Strip trailing /
    cleaned = cleaned.rstrip("/")

    # SSH format: git@host:owner/repo
    ssh_match = re.match(r"^[\w.-]+@[\w.-]+:(.+)$", cleaned)
    if ssh_match:
        path_part = ssh_match.group(1)
        return _slugify_path_segments(path_part)

    # HTTPS / plain: https://host/owner/repo or host/owner/repo
    # Remove protocol
    cleaned = re.sub(r"^https?://", "", cleaned)

    # Remove host (everything before the first /)
    parts = cleaned.split("/", 1)
    # parts[1] is the path after the host; a bare host with no path uses parts[0].
    path_part = parts[1] if len(parts) == 2 else parts[0]

    return _slugify_path_segments(path_part)


# ── Internal Helpers ──────────────────────────────────────────


def _find_git_root(path: Path) -> Path | None:
    """Walk up from *path* looking for a ``.git`` directory.

    Returns the directory containing ``.git``, or ``None`` if we reach
    the filesystem root without finding one.
    """
    current = path if path.is_dir() else path.parent
    while True:
        if (current / ".git").exists():
            return current
        parent = current.parent
        if parent == current:
            # Reached filesystem root
            return None
        current = parent


async def _get_remote_url(git_root: Path) -> str | None:
    """Run ``git remote get-url origin`` in *git_root* and return the result.

    Returns ``None`` if the command fails (no remote configured, git not
    installed, etc.).
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            "remote",
            "get-url",
            "origin",
            cwd=str(git_root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
        if proc.returncode == 0 and stdout:
            return stdout.decode().strip()
    except (FileNotFoundError, asyncio.TimeoutError, OSError):
        # git not installed, or something went wrong
        pass
    return None


def _slugify_path_segments(path: str) -> str:
    """Turn ``owner/repo`` path segments into ``owner-repo`` slug."""
    # Take at most the last 2 segments (owner + repo)
    segments = [s for s in path.split("/") if s]
    if len(segments) >= 2:
        raw = f"{segments[-2]}-{segments[-1]}"
    elif segments:
        raw = segments[0]
    else:
        return "unnamed"
    return _slugify_name(raw)


def _slugify_name(name: str) -> str:
    """Convert an arbitrary name to a URL-safe slug.

    Lowercases, replaces non-alphanumeric characters (except hyphens)
    with hyphens, and collapses consecutive hyphens.
    """
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9-]", "-", slug)
    slug = re.sub(r"-{2,}", "-", slug)
    slug = slug.strip("-")
    return slug or "unnamed"
