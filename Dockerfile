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
# --extra postgres pulls in asyncpg so the image can talk to managed Postgres.
# LICENSE is required because pyproject sets license-files = ["LICENSE"];
# the build backend globs for it when building the wheel.
COPY pyproject.toml uv.lock README.md LICENSE ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev --extra postgres

# Install the project itself (--no-editable copies it into the venv so the
# runtime stage needs only /opt/venv, not the source tree).
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable --extra postgres

# ── Runtime ──────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Non-root user for the running service.
RUN useradd --create-home --uid 10001 app

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    # Self-host default; hosted deploys override with a Postgres URL.
    DEVMEMORY_DATABASE_URL="sqlite+aiosqlite:////data/devmemory.db" \
    DEVMEMORY_HOST=0.0.0.0 \
    DEVMEMORY_PORT=8765

COPY --from=builder /opt/venv /opt/venv

# Writable data dir for the SQLite database (mount a volume here in self-host).
RUN mkdir -p /data && chown app:app /data
VOLUME ["/data"]

WORKDIR /home/app

# Alembic config + migrations + entrypoint (needed to migrate on boot).
COPY --chown=app:app alembic.ini ./alembic.ini
COPY --chown=app:app alembic ./alembic
COPY --chown=app:app docker-entrypoint.sh ./docker-entrypoint.sh
RUN chmod +x ./docker-entrypoint.sh

USER app

EXPOSE 8765

# Container-native healthcheck against the REST /health endpoint. Reads the
# active port ($PORT on managed platforms, else DEVMEMORY_PORT).
HEALTHCHECK --interval=30s --timeout=3s --start-period=15s --retries=3 \
    CMD python -c "import os,urllib.request,sys; p=os.environ.get('PORT') or os.environ.get('DEVMEMORY_PORT','8765'); sys.exit(0 if urllib.request.urlopen(f'http://127.0.0.1:{p}/health').status==200 else 1)"

# Migrate, then start the REST API (honours $PORT). Override for other commands.
ENTRYPOINT ["./docker-entrypoint.sh"]
