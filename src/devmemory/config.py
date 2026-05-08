"""Application configuration loaded from environment variables."""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class DeploymentMode(str, Enum):
    """Server deployment mode."""

    SAAS = "saas"
    SELF_HOSTED = "self-hosted"


class Settings(BaseSettings):
    """DevMemory configuration.

    Values are loaded from environment variables prefixed with ``DEVMEMORY_``.
    A ``.env`` file in the project root is also read automatically.
    """

    model_config = SettingsConfigDict(
        env_prefix="DEVMEMORY_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── Deployment ──────────────────────────────────────────────
    deployment_mode: DeploymentMode = DeploymentMode.SELF_HOSTED

    # ── Database ────────────────────────────────────────────────
    database_url: str = "sqlite+aiosqlite:///./devmemory.db"

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
