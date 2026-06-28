# syntax=docker/dockerfile:1.7

# ── Builder ──────────────────────────────────────────────────────────────────
# Install dependencies + the project into an isolated venv using uv.
FROM python:3.12-slim AS builder

# uv: fast, reproducible installs (uses uv.lock).
COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /app

# Install dependencies first (cached layer — only re-runs when lockfile changes).
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# Install the project itself (source rarely shares a layer with deps).
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ── Runtime ──────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Non-root user for the running service.
RUN useradd --create-home --uid 10001 app

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    # Persist the SQLite DB on a mounted volume by default.
    DEVMEMORY_DATABASE_URL="sqlite+aiosqlite:////data/devmemory.db" \
    DEVMEMORY_HOST=0.0.0.0 \
    DEVMEMORY_PORT=8765

COPY --from=builder /opt/venv /opt/venv

# Writable data dir for the SQLite database (mount a volume here in prod).
RUN mkdir -p /data && chown app:app /data
VOLUME ["/data"]

USER app
WORKDIR /home/app

EXPOSE 8765

# Container-native healthcheck against the REST /health endpoint.
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8765/health').status==200 else 1)"

# Start the REST API server (HTTP). For the MCP stdio server, override the CMD.
CMD ["devmemory", "--rest"]
