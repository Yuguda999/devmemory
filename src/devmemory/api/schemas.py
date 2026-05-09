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
