"""Context injection routes — API-key authenticated endpoints for tool hooks.

These endpoints are designed to be called by shell scripts and git hooks,
NOT by the browser UI.  They accept API keys instead of JWT tokens so that
devmemory-inject scripts work without a browser session.

Endpoints
---------
GET /context/resume   — Return the resume prompt for the latest active session
                        in the project at ``cwd``.  Used by the
                        ``devmemory-inject`` shell script to auto-populate
                        CLAUDE.md, .augment/rules/, etc.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from devmemory.auth.middleware import AuthContext, require_api_key_user
from devmemory.db.engine import get_db_session
from devmemory.db.repository import (
    get_context_blocks,
    get_or_create_project,
    list_sessions,
)
from devmemory.resolver.git_resolver import resolve_project_slug
from devmemory.tools.resume import generate_resume_prompt

router = APIRouter(prefix="/context", tags=["context"])


@router.get(
    "/resume",
    summary="Get resume prompt for the current project",
    response_model=None,
)
async def get_resume_prompt(
    cwd: str = Query(..., description="Absolute path to the project working directory"),
    target_tool: str = Query(
        default="generic",
        description="Target tool preamble: claude, cursor, windsurf, augment, or generic",
    ),
    auth: AuthContext = Depends(require_api_key_user),
) -> dict:
    """Return a resume prompt for the latest active session in the project at ``cwd``.

    Designed to be called by the ``devmemory-inject`` shell script on tool
    startup.  Returns the full prompt text plus metadata so the script can
    write it to CLAUDE.md, .augment/rules/devmemory.md, etc.

    Authentication: ``X-API-Key: dm_key_...`` header.
    """
    async with get_db_session() as db:
        # Resolve the project from the git remote in cwd
        proj_info = await resolve_project_slug(cwd)
        proj, _ = await get_or_create_project(
            db, auth.user_id, proj_info.slug, name=proj_info.name
        )

        # Find the latest active session
        sessions = await list_sessions(
            db, auth.user_id, project_id=str(proj.id), status="active", limit=1
        )

        if not sessions:
            return {
                "ok": True,
                "has_context": False,
                "project": proj_info.name,
                "session_id": None,
                "prompt": None,
                "message": f"No active session found for project '{proj_info.name}'. Start one with devmemory start_session.",
            }

        dev_session = sessions[0]
        blocks = await get_context_blocks(
            db,
            session_id=str(dev_session.id),
            user_id=auth.user_id,
            limit=200,
        )

    if not blocks:
        return {
            "ok": True,
            "has_context": False,
            "project": proj_info.name,
            "session_id": str(dev_session.id),
            "prompt": None,
            "message": "Active session exists but has no context blocks yet.",
        }

    prompt = generate_resume_prompt(
        project_name=proj_info.name,
        session_title=dev_session.title,
        blocks=blocks,
        target_tool=target_tool,
        session_id=str(dev_session.id),
    )

    return {
        "ok": True,
        "has_context": True,
        "project": proj_info.name,
        "session_id": str(dev_session.id),
        "session_title": dev_session.title,
        "block_count": len(blocks),
        "prompt": prompt,
    }
