#!/usr/bin/env python3
"""Merge legacy git-remote-slug projects into their folder-name equivalents.

Project identity switched from the git *remote* slug (``owner-repo``) to the
project **folder name**. Projects created under the old scheme are stranded:
new sessions now land on the folder-name project, so one repo's history ends up
split across two projects (e.g. ``yuguda999-devmemory`` + ``devmemory``).

This folds each legacy project into its folder-name project:
  * sessions are reassigned to the target project (context blocks follow —
    they reference the session, not the project);
  * the emptied legacy project is deleted.

MAPPING (the server cannot see your local folders): a project WITH a
``remote_url`` is assumed to live in a folder named like the repo — i.e. the
last path segment of the remote (minus ``.git``), slugified. True for a normal
clone. Projects without a ``remote_url`` are already folder-name-style and are
left untouched.

  * If a folder-name project already exists → MERGE legacy into it.
  * Otherwise → RENAME the legacy project's slug/name in place.

DRY-RUN by default. Pass --apply to write. Scope with --user <id> (default: all
users). Reads DEVMEMORY_DATABASE_URL like the app — run it where the DB is
reachable (e.g. on the Render service, or with the external DB URL exported).

    python scripts/merge_projects.py                # preview
    python scripts/merge_projects.py --apply        # execute
    python scripts/merge_projects.py --user <uid> --apply
"""

from __future__ import annotations

import argparse
import asyncio
import re

from sqlalchemy import delete, func, select, update

from devmemory.db.engine import close_db, get_db_session
from devmemory.models.context import ContextBlock
from devmemory.models.project import Project
from devmemory.models.session import Session


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9-]", "-", name.lower().strip())
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug or "unnamed"


def _repo_basename(remote_url: str) -> str:
    """Last path segment of a git remote, minus a trailing .git and slashes."""
    cleaned = remote_url.strip().rstrip("/")
    if cleaned.endswith(".git"):
        cleaned = cleaned[:-4]
    # Handle both git@host:owner/repo and https://host/owner/repo forms.
    tail = re.split(r"[/:]", cleaned)[-1]
    return tail or "unnamed"


async def _counts(session, project_id: str) -> tuple[int, int]:
    n_sessions = await session.scalar(
        select(func.count()).select_from(Session).where(Session.project_id == project_id)
    )
    n_blocks = await session.scalar(
        select(func.count())
        .select_from(ContextBlock)
        .join(Session, ContextBlock.session_id == Session.id)
        .where(Session.project_id == project_id)
    )
    return int(n_sessions or 0), int(n_blocks or 0)


async def run(apply: bool, user_filter: str | None) -> None:
    async with get_db_session() as session:
        q = select(Project)
        if user_filter:
            q = q.where(Project.user_id == user_filter)
        projects = list((await session.execute(q)).scalars().all())

        # Group by user; slug → project for target lookup.
        by_user: dict[str, dict[str, Project]] = {}
        for p in projects:
            by_user.setdefault(p.user_id, {})[p.slug] = p

        planned_merges = 0
        planned_renames = 0

        for user_id, slug_map in by_user.items():
            print(f"\nUser {user_id}:")
            # Legacy = has a remote_url whose folder-name slug differs from its slug.
            legacy = []
            for p in list(slug_map.values()):
                if not p.remote_url:
                    continue
                repo = _repo_basename(p.remote_url)
                new_slug = _slugify(repo)
                if new_slug != p.slug:
                    legacy.append((p, new_slug, repo))

            if not legacy:
                print("  (nothing to merge — all projects already folder-name-style)")
                continue

            for p, new_slug, repo in legacy:
                # Capture the slug now: an ORM-enabled UPDATE syncs p.slug in the
                # identity map immediately, so reading it after the execute would
                # already return the new value.
                old_slug = p.slug
                n_sess, n_blk = await _counts(session, p.id)
                target = slug_map.get(new_slug)
                if target is not None and target.id != p.id:
                    print(
                        f"  MERGE  {old_slug!r} → {new_slug!r}  "
                        f"(move {n_sess} session(s), {n_blk} block(s); delete legacy)"
                    )
                    planned_merges += 1
                    if apply:
                        await session.execute(
                            update(Session)
                            .where(Session.project_id == p.id)
                            .values(project_id=target.id)
                        )
                        await session.execute(delete(Project).where(Project.id == p.id))
                        del slug_map[old_slug]
                else:
                    print(
                        f"  RENAME {old_slug!r} → {new_slug!r} (name {repo!r}; "
                        f"{n_sess} session(s), {n_blk} block(s) kept in place)"
                    )
                    planned_renames += 1
                    if apply:
                        await session.execute(
                            update(Project)
                            .where(Project.id == p.id)
                            .values(slug=new_slug, name=repo, remote_url=None)
                        )
                        del slug_map[old_slug]
                        slug_map[new_slug] = p

        print(
            f"\n{'APPLIED' if apply else 'DRY-RUN'}: "
            f"{planned_merges} merge(s), {planned_renames} rename(s)."
        )
        if not apply and (planned_merges or planned_renames):
            print("Re-run with --apply to execute.")

    await close_db()


def main() -> None:
    ap = argparse.ArgumentParser(description="Merge legacy remote-slug projects into folder-name ones.")
    ap.add_argument("--apply", action="store_true", help="Write changes (default: dry-run).")
    ap.add_argument("--user", default=None, help="Limit to one user_id (default: all users).")
    args = ap.parse_args()
    asyncio.run(run(apply=args.apply, user_filter=args.user))


if __name__ == "__main__":
    main()
