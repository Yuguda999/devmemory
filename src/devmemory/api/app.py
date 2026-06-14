"""FastAPI application factory with lifespan management."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from devmemory.config import settings
from devmemory.db.engine import close_db, init_db

_STATIC_DIR = Path(__file__).parent / "static"
_INDEX_HTML = _STATIC_DIR / "index.html"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: initialize DB on startup, close on shutdown."""
    await init_db()
    yield
    await close_db()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        A configured FastAPI instance with all routers mounted.
    """
    app = FastAPI(
        title="DevMemory",
        description=(
            "Universal Dev Memory — A persistent MCP server for cross-tool coding context. "
            "Store, structure, and serve coding context so any AI tool can continue seamlessly."
        ),
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # ── CORS ───────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.is_self_hosted else [
            "https://devmemory.io",
            "http://localhost:3000",
            "http://localhost:8765",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routes ─────────────────────────────────────────────────
    from devmemory.api.auth_routes import router as auth_router
    from devmemory.api.billing_routes import router as billing_router
    from devmemory.api.context_routes import router as context_router
    from devmemory.api.project_routes import router as project_router
    from devmemory.api.session_routes import router as session_router

    app.include_router(auth_router)
    app.include_router(project_router)
    app.include_router(session_router)
    app.include_router(billing_router)
    app.include_router(context_router)

    # ── Health Check ───────────────────────────────────────────
    @app.get("/health", tags=["system"], summary="Health check")
    async def health() -> dict[str, str | bool]:
        return {
            "status": "ok",
            "version": "0.1.0",
            "self_hosted": settings.is_self_hosted,
            "deployment_mode": settings.deployment_mode,
        }

    # ── Static Files + SPA ─────────────────────────────────────
    if _STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

        @app.get("/", include_in_schema=False)
        async def serve_spa() -> FileResponse:
            return FileResponse(str(_INDEX_HTML))

    return app
