"""Application configuration loaded from environment variables."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _normalize_asyncpg_url(url: str) -> str:
    """Rewrite libpq query params into asyncpg-compatible ones.

    Managed Postgres providers (Neon, Supabase) hand out URLs ending in
    ``?sslmode=require&channel_binding=require``. asyncpg rejects ``sslmode``
    and ``channel_binding`` as connect params, but SQLAlchemy's asyncpg dialect
    honours ``?ssl=require`` (verified). So translate ``sslmode`` → ``ssl`` and
    drop ``channel_binding``. The result works uniformly for both the app engine
    and Alembic, which each build their own engine from this URL.
    """
    parts = urlsplit(url)
    if not parts.query:
        return url
    out: list[tuple[str, str]] = []
    for k, v in parse_qsl(parts.query, keep_blank_values=True):
        kl = k.lower()
        if kl == "channel_binding":
            continue
        out.append(("ssl", v) if kl == "sslmode" else (k, v))
    return urlunsplit(parts._replace(query=urlencode(out)))


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

    # Public base URL used to build links in outbound emails (verification,
    # password reset). Must be the address a user's browser can reach — NOT
    # ``0.0.0.0``. Override in SaaS, e.g. ``https://app.devmemory.io``.
    app_base_url: str = "http://localhost:8765"

    # ── Email ───────────────────────────────────────────────────
    # Email is OPTIONAL and has two backends, auto-selected in this order:
    #   1. SendGrid HTTP API  — if ``sendgrid_api_key`` is set (works on hosts
    #      that block outbound SMTP, e.g. Render — it uses HTTPS/443).
    #   2. SMTP               — if ``smtp_host`` is set.
    #   3. Neither            — emails are logged, not sent, and verification is
    #      not enforced (see ``email_enabled`` / ``enforce_email_verification``).
    # ``smtp_from_email`` / ``smtp_from_name`` are the From identity for BOTH
    # backends (for SendGrid single-sender, ``smtp_from_email`` must equal the
    # verified sender address).
    smtp_from_email: str = "no-reply@devmemory.io"
    smtp_from_name: str = "DevMemory"

    # SendGrid HTTP API
    sendgrid_api_key: str | None = None

    # SMTP
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_use_tls: bool = True   # STARTTLS on connect (port 587)
    smtp_use_ssl: bool = False  # implicit TLS (port 465); mutually exclusive with STARTTLS

    # Token lifetimes
    email_verification_expiry_hours: int = 24
    password_reset_expiry_minutes: int = 30

    # ── Cardano payments (SaaS only) ────────────────────────────
    # Payments are taken in ADA on Cardano, detected via Blockfrost (a hosted
    # Cardano API — no node to run). Flow: create an invoice with a unique
    # expected amount, the user sends ADA to ``cardano_receive_address`` from
    # any wallet, and the server polls Blockfrost to confirm the exact amount
    # arrived. Leave ``blockfrost_project_id`` unset to disable payments.
    blockfrost_project_id: str | None = None
    # Network the wallet + Blockfrost project belong to. Build/test on ``preprod``
    # (free faucet ADA), flip to ``mainnet`` for real payments.
    blockfrost_network: str = "preprod"  # preprod | preview | mainnet
    # Your wallet's ACCOUNT public key (CIP-5 ``acct_xvk1...``, exported once from
    # Lace/Eternl). The server derives a fresh receiving address per invoice from
    # it, so each payment is a clean round amount to a unique address — no odd
    # amounts, and every address still belongs to your wallet.
    cardano_account_xpub: str | None = None
    # One-time upgrade prices, in whole ADA, per tier (round numbers on purpose).
    cardano_price_pro_ada: float = 10.0
    cardano_price_team_ada: float = 30.0
    # How long an unpaid invoice stays valid, how many days an upgrade lasts, and
    # how often the background poller checks pending invoices for payment.
    cardano_invoice_expiry_minutes: int = 30
    cardano_subscription_days: int = 30
    cardano_poll_interval_seconds: int = 30
    # DEV ONLY: allow the /billing/invoice/{id}/simulate-paid endpoint so the
    # upgrade flow can be tested without a real on-chain payment. Never enable in
    # production.
    cardano_allow_test_payments: bool = False

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
        # Force the async driver. Managed providers (Neon, Supabase, Heroku)
        # hand out `postgresql://` or `postgres://`, which SQLAlchemy maps to the
        # sync psycopg2 driver (not installed) — so paste-as-is would crash. We
        # only ship asyncpg, so rewrite any bare/psycopg2 Postgres scheme to it.
        for bare in ("postgresql+psycopg2://", "postgresql://", "postgres://"):
            if value.startswith(bare):
                value = "postgresql+asyncpg://" + value[len(bare) :]
                break
        if value.startswith("postgresql+asyncpg://"):
            return _normalize_asyncpg_url(value)
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
    def blockfrost_base_url(self) -> str:
        """Return the Blockfrost API base URL for the configured network."""
        net = (self.blockfrost_network or "preprod").lower().strip()
        return {
            "mainnet": "https://cardano-mainnet.blockfrost.io/api/v0",
            "preprod": "https://cardano-preprod.blockfrost.io/api/v0",
            "preview": "https://cardano-preview.blockfrost.io/api/v0",
        }.get(net, "https://cardano-preprod.blockfrost.io/api/v0")

    @property
    def payments_enabled(self) -> bool:
        """Return True when Cardano payments are fully configured."""
        return bool(self.blockfrost_project_id) and bool(self.cardano_account_xpub)

    @property
    def database_is_sqlite(self) -> bool:
        """Return True when the configured database is SQLite."""
        return self.database_url.startswith("sqlite")

    @property
    def email_enabled(self) -> bool:
        """Return True when any email backend (SendGrid or SMTP) is configured."""
        return bool(self.sendgrid_api_key) or bool(self.smtp_host)

    @property
    def enforce_email_verification(self) -> bool:
        """Block unverified logins only in SaaS mode with email actually wired.

        Enforcing verification without a way to deliver the email would lock new
        users out, so it is gated on both conditions.
        """
        return self.is_saas and self.email_enabled


def get_project_root() -> Path:
    """Return the project root directory."""
    return Path(__file__).resolve().parent.parent.parent


# Singleton settings instance — import this everywhere.
settings = Settings()
