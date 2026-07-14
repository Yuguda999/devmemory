"""Pydantic schemas for REST API request/response validation."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

# ── Auth: Register ─────────────────────────────────────────────


class RegisterRequest(BaseModel):
    """User registration request."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=100)


class RegisterResponse(BaseModel):
    """User registration response."""

    id: str
    email: str
    display_name: str
    tier: str
    created_at: datetime


# ── Auth: Login ────────────────────────────────────────────────


class LoginRequest(BaseModel):
    """User login request."""

    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    """Login response containing JWT token."""

    access_token: str
    token_type: str = "bearer"
    user_id: str
    email: str
    display_name: str = ""
    email_verified: bool = True


# ── Account: profile, password, email, notifications ───────────


class MeResponse(BaseModel):
    """The authenticated user's account profile."""

    id: str
    email: str
    display_name: str
    email_verified: bool
    tier: str
    notification_prefs: dict[str, bool]
    created_at: datetime


class UpdateProfileRequest(BaseModel):
    """Editable profile fields."""

    display_name: str = Field(min_length=1, max_length=100)


class ChangePasswordRequest(BaseModel):
    """Change password while logged in."""

    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8, max_length=128)


class NotificationPrefsRequest(BaseModel):
    """Toggle optional email notification categories."""

    security_alerts: bool | None = None
    account_events: bool | None = None


class NotificationPrefsResponse(BaseModel):
    """Current notification preferences."""

    security_alerts: bool
    account_events: bool


# ── Auth: password reset + verification ────────────────────────


class ForgotPasswordRequest(BaseModel):
    """Start the password-reset flow for an email address."""

    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """Complete a password reset using an emailed token."""

    token: str = Field(min_length=1)
    new_password: str = Field(min_length=8, max_length=128)


class VerifyEmailRequest(BaseModel):
    """Confirm an email address using an emailed token."""

    token: str = Field(min_length=1)


class ResendVerificationRequest(BaseModel):
    """Re-send a verification email to an unverified address."""

    email: EmailStr


# ── API Keys ───────────────────────────────────────────────────


class CreateApiKeyRequest(BaseModel):
    """Request to create a new API key."""

    name: str = Field(min_length=1, max_length=64, description="A friendly name for this key")


class ApiKeyCreatedResponse(BaseModel):
    """Response after creating an API key. Contains the raw key (shown once)."""

    id: str
    name: str
    prefix: str
    key: str = Field(description="Full API key — save this now, it won't be shown again")
    created_at: datetime


class ApiKeyListItem(BaseModel):
    """An API key in the list view (no raw key, just metadata)."""

    id: str
    name: str
    prefix: str
    revoked: bool
    last_used_at: datetime | None
    created_at: datetime


class ApiKeyListResponse(BaseModel):
    """List of API keys for the authenticated user."""

    keys: list[ApiKeyListItem]
    count: int


# ── Generic ────────────────────────────────────────────────────


class MessageResponse(BaseModel):
    """Generic message response."""

    message: str


class ErrorResponse(BaseModel):
    """Error response body."""

    detail: str


# ── Projects ───────────────────────────────────────────────────


class ProjectResponse(BaseModel):
    """A single project."""

    id: str
    slug: str
    name: str
    remote_url: str | None
    created_at: datetime
    updated_at: datetime


class ProjectListResponse(BaseModel):
    """Paginated list of projects."""

    projects: list[ProjectResponse]
    count: int


# ── Sessions ───────────────────────────────────────────────────


class SessionResponse(BaseModel):
    """A single session."""

    id: str
    project_id: str
    title: str
    status: str
    tool_source: str
    created_at: datetime
    updated_at: datetime


class SessionListResponse(BaseModel):
    """List of sessions."""

    sessions: list[SessionResponse]
    count: int


class UpdateSessionRequest(BaseModel):
    """Partial update for a session: title and/or status."""

    title: str | None = Field(default=None, min_length=1, max_length=500)
    status: str | None = Field(
        default=None,
        description="One of: active, paused, completed, archived",
    )


# ── Context Blocks ─────────────────────────────────────────────


class ContextBlockResponse(BaseModel):
    """A single context block."""

    id: str
    session_id: str
    block_type: str
    content: str
    priority: int
    meta_json: str | None
    created_at: datetime
    updated_at: datetime | None


class ContextBlockListResponse(BaseModel):
    """List of context blocks for a session."""

    blocks: list[ContextBlockResponse]
    count: int


# ── Client / MCP API (API-key authenticated) ──────────────────
#
# Project resolution (git remote → slug/name) happens CLIENT-SIDE, because the
# hosted server never has access to the caller's working directory. The client
# resolves the project locally and passes the identifiers here.


class ProjectRef(BaseModel):
    """Client-resolved project identifiers sent with write requests."""

    slug: str = Field(
        min_length=1,
        max_length=255,
        description="URL-safe project id (git-remote or dir derived)",
    )
    name: str | None = Field(default=None, max_length=255)
    remote_url: str | None = Field(default=None, max_length=1024)


class SaveContextRequest(BaseModel):
    """Save a single typed context block (mirrors the save_context tool)."""

    project: ProjectRef
    block_type: str = Field(
        description="One of: goal, decision, code, error, next_step, note, task"
    )
    content: str = Field(min_length=1)
    session_id: str | None = None
    priority: int = Field(default=5, ge=1, le=10)


class SaveContextResponse(BaseModel):
    ok: bool = True
    block_id: str
    session_id: str
    project_slug: str
    block_type: str


class TaskItem(BaseModel):
    title: str = Field(min_length=1)
    description: str | None = None
    priority: int = Field(default=5, ge=1, le=10)


class SaveTasksRequest(BaseModel):
    """Save a batch of tasks as 'task' blocks (mirrors the save_tasks tool)."""

    project: ProjectRef
    tasks: list[TaskItem] = Field(min_length=1)
    session_id: str | None = None


class SaveTasksResponse(BaseModel):
    ok: bool = True
    session_id: str
    project_slug: str
    task_ids: list[str]


class UpdateTaskStatusRequest(BaseModel):
    status: str = Field(description="One of: pending, in_progress, done, skipped")


class TaskStatusResponse(BaseModel):
    ok: bool = True
    block_id: str
    status: str


class StartSessionRequest(BaseModel):
    """Begin a new session (mirrors the start_session tool)."""

    project: ProjectRef
    title: str = Field(min_length=1, max_length=500)
    tool_source: str = "unknown"


class StartSessionResponse(BaseModel):
    ok: bool = True
    session_id: str
    project_id: str
    project_slug: str
    project_name: str
    project_created: bool


class GetContextResponse(BaseModel):
    """Blocks for a project's latest active session or an explicit session."""

    ok: bool = True
    session_id: str | None
    session_title: str | None = None
    blocks: list[ContextBlockResponse]
    count: int


class ResumePromptResponse(BaseModel):
    ok: bool = True
    session_id: str
    target_tool: str
    block_count: int
    prompt: str


# ── Tool Connections ───────────────────────────────────────────


class ToolConnectionResponse(BaseModel):
    """A connected AI tool and its derived live status."""

    client: str
    client_version: str | None
    status: str = Field(description="One of: connected, idle, offline")
    last_seen_at: datetime
    first_seen_at: datetime


class ToolConnectionListResponse(BaseModel):
    """List of tool connections for the authenticated user."""

    connections: list[ToolConnectionResponse]
    count: int


# ── Billing ────────────────────────────────────────────────────


class BillingLimits(BaseModel):
    """Quota limits for the user's current tier."""

    max_projects: int | None = Field(description="None means unlimited")
    max_sessions_per_project: int | None
    max_blocks_per_session: int | None


class BillingUsage(BaseModel):
    """Current usage counts."""

    projects: int
    total_sessions: int


class BillingStatusResponse(BaseModel):
    """Billing tier and usage summary."""

    tier: str
    limits: BillingLimits
    usage: BillingUsage


# ── Cardano payments ───────────────────────────────────────────


class UpgradeRequest(BaseModel):
    """Request to upgrade to a paid tier via a Cardano payment."""

    tier: str = Field(description="Target tier: 'pro' or 'team'")


class InvoiceResponse(BaseModel):
    """A Cardano payment invoice the user pays to upgrade."""

    invoice_id: str
    tier: str
    status: str  # pending | paid | expired
    network: str
    pay_to_address: str
    amount_lovelace: int
    amount_ada: float
    expires_at: str
    tx_hash: str | None = None
