"""REST API routes for project management."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from devmemory.api.schemas import ProjectListResponse, ProjectResponse
from devmemory.auth.middleware import AuthContext, require_jwt_user
from devmemory.db.engine import get_db_session
from devmemory.db.repository import list_projects

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get(
    "",
    response_model=ProjectListResponse,
    summary="List all projects",
)
async def list_projects_endpoint(
    auth: AuthContext = Depends(require_jwt_user),
) -> ProjectListResponse:
    """List all projects for the authenticated user.

    Projects are created automatically by the MCP ``save_context`` and
    ``start_session`` tools when a new git repository is first encountered.
    """
    async with get_db_session() as session:
        projects = await list_projects(session, auth.user_id)

    return ProjectListResponse(
        projects=[
            ProjectResponse(
                id=str(p.id),
                slug=p.slug,
                name=p.name,
                remote_url=p.remote_url,
                created_at=p.created_at,
                updated_at=p.updated_at,
            )
            for p in projects
        ],
        count=len(projects),
    )
