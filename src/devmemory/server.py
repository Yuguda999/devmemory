"""DevMemory server entry point.

Starts the FastAPI REST API server. The MCP server will be added in Phase 2.
"""

from __future__ import annotations

import uvicorn

from devmemory.api.app import create_app
from devmemory.config import settings


def run() -> None:
    """Start the DevMemory server."""
    app = create_app()
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    run()
