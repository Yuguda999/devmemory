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
    updated_at: datetime


class ContextBlockListResponse(BaseModel):
    """List of context blocks for a session."""

    blocks: list[ContextBlockResponse]
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
