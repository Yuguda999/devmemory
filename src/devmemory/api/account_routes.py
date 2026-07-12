"""REST API routes for the authenticated user's account and settings."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from devmemory.api.schemas import (
    ChangePasswordRequest,
    MeResponse,
    MessageResponse,
    NotificationPrefsRequest,
    NotificationPrefsResponse,
    UpdateProfileRequest,
)
from devmemory.auth.hashing import verify_password
from devmemory.auth.middleware import AuthContext, require_jwt_user
from devmemory.db.engine import get_db_session
from devmemory.db.repository import (
    get_user_by_id,
    set_notification_prefs,
    update_user_password,
    update_user_profile,
)
from devmemory.mailer import service as mail

router = APIRouter(prefix="/account", tags=["account"])


# ── Profile ────────────────────────────────────────────────────


@router.get("/me", response_model=MeResponse, summary="Get the current account")
async def get_me(auth: AuthContext = Depends(require_jwt_user)) -> MeResponse:
    """Return the authenticated user's profile and settings."""
    async with get_db_session() as session:
        user = await get_user_by_id(session, auth.user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        return MeResponse(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            email_verified=user.email_verified,
            tier=auth.tier.value,
            notification_prefs=user.notification_prefs,
            created_at=user.created_at,
        )


@router.patch("/profile", response_model=MeResponse, summary="Update profile")
async def update_profile(
    body: UpdateProfileRequest,
    auth: AuthContext = Depends(require_jwt_user),
) -> MeResponse:
    """Update the user's editable profile fields (display name)."""
    async with get_db_session() as session:
        user = await update_user_profile(session, auth.user_id, body.display_name)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        return MeResponse(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            email_verified=user.email_verified,
            tier=auth.tier.value,
            notification_prefs=user.notification_prefs,
            created_at=user.created_at,
        )


# ── Password ───────────────────────────────────────────────────


@router.post(
    "/change-password",
    response_model=MessageResponse,
    summary="Change password",
    responses={400: {"description": "Current password is incorrect"}},
)
async def change_password(
    body: ChangePasswordRequest,
    background: BackgroundTasks,
    auth: AuthContext = Depends(require_jwt_user),
) -> MessageResponse:
    """Change the user's password after verifying the current one."""
    async with get_db_session() as session:
        user = await get_user_by_id(session, auth.user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        if not verify_password(body.current_password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect",
            )

        email = user.email
        display_name = user.display_name
        await update_user_password(session, user.id, body.new_password)

    # Security-critical — always notify.
    background.add_task(mail.send_password_changed_email, email, display_name)
    return MessageResponse(message="Password changed successfully.")


# ── Notification preferences ───────────────────────────────────


@router.get(
    "/notifications",
    response_model=NotificationPrefsResponse,
    summary="Get notification preferences",
)
async def get_notifications(
    auth: AuthContext = Depends(require_jwt_user),
) -> NotificationPrefsResponse:
    """Return the user's notification preferences."""
    async with get_db_session() as session:
        user = await get_user_by_id(session, auth.user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        prefs = user.notification_prefs
    return NotificationPrefsResponse(
        security_alerts=prefs["security_alerts"],
        account_events=prefs["account_events"],
    )


@router.patch(
    "/notifications",
    response_model=NotificationPrefsResponse,
    summary="Update notification preferences",
)
async def update_notifications(
    body: NotificationPrefsRequest,
    auth: AuthContext = Depends(require_jwt_user),
) -> NotificationPrefsResponse:
    """Toggle optional notification categories. Omitted fields are unchanged."""
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    async with get_db_session() as session:
        user = await set_notification_prefs(session, auth.user_id, updates)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        prefs = user.notification_prefs
    return NotificationPrefsResponse(
        security_alerts=prefs["security_alerts"],
        account_events=prefs["account_events"],
    )
