"""Application configuration loaded from environment variables."""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DeploymentMode(str, Enum):
    """Server deployment mode."""

    SAAS = "saas"
    SELF_HOSTED = "self-hosted"


def _default_database_url() -> str:
    """Return the default SQLite URL, anchored to a single absolute location.

    The MCP server is launched by each AI tool with that tool's *working
    directory* (usually the open project). A relative SQLite path like
    ``./devmemory.db`` therefore resolves to a **different file per project** —
    so context saved from one project is invisible to the dashboard and to
    every other project, and auth fails against the empty per-project DB.

    Anchoring to ``~/.devmemory/devmemory.db`` guarantees the MCP server (any
    CWD), the REST/dashboard server, and ``devmemory inject`` all share one DB.
    Override with the ``DEVMEMORY_DATABASE_URL`` env var (e.g. Postgres in SaaS).
    """
    db_dir = Path.home() / ".devmemory"
    db_dir.mkdir(parents=True, exist_ok=True)
    return f"sqlite+aiosqlite:///{db_dir / 'devmemory.db'}"


class Settings(BaseSettings):
    """DevMemory configuration.

    Values are loaded from environment variables prefixed with ``DEVMEMORY_``.
    A ``.env`` file in the project root is also read automatically.
    """

    # Load a project-local ``.env`` first (dev convenience) then the global
    # ``~/.devmemory/.env`` which OVERRIDES it. The global file is the single
    # source of truth so the MCP server (launched with each AI tool's working
    # directory) and the REST/dashboard server always resolve the SAME database
    # and deployment mode — regardless of what CWD they happen to run in.
    # Real environment variables still win over both files.
    model_config = SettingsConfigDict(
        env_prefix="DEVMEMORY_",
        env_file=(".env", str(Path.home() / ".devmemory" / ".env")),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Deployment ──────────────────────────────────────────────
    deployment_mode: DeploymentMode = DeploymentMode.SELF_HOSTED

    # ── Database ────────────────────────────────────────────────
    database_url: str = ""  # resolved in the validator below

    # ── Auth ────────────────────────────────────────────────────
    secret_key: str = "change-me-to-a-random-secret-key"
    jwt_expiry_hours: int = 24
    jwt_algorithm: str = "HS256"

    # ── Server ──────────────────────────────────────────────────
    host: str = "0.0.0.0"
    port: int = 8765
    log_level: str = "INFO"

    # ── Stripe (SaaS only) ──────────────────────────────────────
    stripe_secret_key: str | None = None
    stripe_webhook_secret: str | None = None
    stripe_price_pro: str | None = None
    stripe_price_team: str | None = None

    @field_validator("database_url", mode="before")
    @classmethod
    def _resolve_database_url(cls, value: str | None) -> str:
        """Fill in the default and anchor any relative SQLite path to absolute.

        Guards against the split-brain-per-project bug even if someone sets a
        relative ``DEVMEMORY_DATABASE_URL`` like ``sqlite:///./devmemory.db``.
        """
        if not value:
            return _default_database_url()
        # Anchor relative SQLite paths under ~/.devmemory so the DB never
        # depends on the process's working directory (which is the whole bug).
        for prefix in ("sqlite+aiosqlite:///", "sqlite:///"):
            if value.startswith(prefix):
                path_part = value[len(prefix) :]
                # 4th slash = already absolute (sqlite:////abs/path); leave it.
                if path_part and not path_part.startswith("/") and not path_part.startswith("~"):
                    rel = path_part.lstrip("./")
                    anchored = (Path.home() / ".devmemory" / rel).expanduser()
                    anchored.parent.mkdir(parents=True, exist_ok=True)
                    return f"{prefix}{anchored}"
        return value

    @property
    def is_saas(self) -> bool:
        """Return True when running in SaaS mode."""
        return self.deployment_mode == DeploymentMode.SAAS

    @property
    def is_self_hosted(self) -> bool:
        """Return True when running in self-hosted mode."""
        return self.deployment_mode == DeploymentMode.SELF_HOSTED

    @property
    def database_is_sqlite(self) -> bool:
        """Return True when the configured database is SQLite."""
        return self.database_url.startswith("sqlite")


def get_project_root() -> Path:
    """Return the project root directory."""
    return Path(__file__).resolve().parent.parent.parent


# Singleton settings instance — import this everywhere.
settings = Settings()
