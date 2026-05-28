"""FastAPI application factory with lifespan management."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from devmemory.config import settings
from devmemory.db.engine import close_db, init_db


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
    from devmemory.api.project_routes import router as project_router
    from devmemory.api.session_routes import router as session_router

    app.include_router(auth_router)
    app.include_router(project_router)
    app.include_router(session_router)
    app.include_router(billing_router)

    # ── Health Check ───────────────────────────────────────────
    @app.get("/health", tags=["system"], summary="Health check")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": "0.1.0"}

    return app
