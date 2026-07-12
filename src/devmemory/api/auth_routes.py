"""REST API routes for user authentication and API key management."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError

from devmemory.api.schemas import (
    ApiKeyCreatedResponse,
    ApiKeyListItem,
    ApiKeyListResponse,
    CreateApiKeyRequest,
    ForgotPasswordRequest,
    LoginRequest,
    LoginResponse,
    MessageResponse,
    RegisterRequest,
    RegisterResponse,
    ResendVerificationRequest,
    ResetPasswordRequest,
    VerifyEmailRequest,
)
from devmemory.auth.hashing import generate_api_key, verify_password
from devmemory.auth.jwt_utils import create_access_token
from devmemory.auth.middleware import AuthContext, require_jwt_user
from devmemory.config import settings
from devmemory.db.engine import get_db_session
from devmemory.db.repository import (
    consume_email_token,
    create_api_key_record,
    create_email_token,
    create_user,
    get_user_by_email,
    get_user_by_id,
    get_valid_email_token,
    list_api_keys,
    mark_email_verified,
    revoke_api_key,
    update_user_password,
)
from devmemory.mailer import service as mail
from devmemory.models import EmailTokenPurpose

router = APIRouter(prefix="/auth", tags=["auth"])


def _verify_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(
        hours=settings.email_verification_expiry_hours
    )


def _reset_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(
        minutes=settings.password_reset_expiry_minutes
    )

_GUEST_EMAIL = "admin@localhost"
_GUEST_PASSWORD = "self-hosted-local-instance"
_GUEST_NAME = "Local Admin"


# ── Self-Hosted Guest Token ────────────────────────────────────


@router.post(
    "/guest-token",
    response_model=LoginResponse,
    summary="Get a guest token (self-hosted mode only)",
    responses={403: {"description": "Only available in self-hosted mode"}},
)
async def guest_token() -> LoginResponse:
    """Return a JWT for the local admin user without requiring credentials.

    Only available when ``DEVMEMORY_DEPLOYMENT_MODE=self-hosted``.
    The local admin account is created automatically on first call.
    """
    if not settings.is_self_hosted:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Guest token is only available in self-hosted mode",
        )

    async with get_db_session() as session:
        user = await get_user_by_email(session, _GUEST_EMAIL)
        if user is None:
            try:
                user = await create_user(
                    session=session,
                    email=_GUEST_EMAIL,
                    password=_GUEST_PASSWORD,
                    display_name=_GUEST_NAME,
                    email_verified=True,
                )
            except Exception:
                # Race condition — fetch again
                user = await get_user_by_email(session, _GUEST_EMAIL)

    token = create_access_token(user_id=user.id, email=user.email)
    return LoginResponse(
        access_token=token,
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        email_verified=user.email_verified,
    )


# ── Registration ───────────────────────────────────────────────


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
    responses={409: {"description": "Email already registered"}},
)
async def register(body: RegisterRequest, background: BackgroundTasks) -> RegisterResponse:
    """Create a new user account with a free-tier subscription.

    When email verification is enforced (SaaS + SMTP configured), the account is
    created unverified and a verification email is sent; the user must confirm
    before logging in. Otherwise the account is auto-verified.
    """
    # Auto-verify unless verification is both applicable and deliverable.
    auto_verified = not settings.enforce_email_verification

    async with get_db_session() as session:
        # Check for existing user
        existing = await get_user_by_email(session, body.email)
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email already exists",
            )

        try:
            user = await create_user(
                session=session,
                email=body.email,
                password=body.password,
                display_name=body.display_name,
                email_verified=auto_verified,
            )
        except IntegrityError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email already exists",
            ) from exc

        display_name = user.display_name
        email = user.email
        prefs = user.notification_prefs
        created_at = user.created_at

        if auto_verified:
            # No verification step — welcome immediately (account event).
            if prefs.get("account_events"):
                background.add_task(mail.send_welcome_email, email, display_name)
        else:
            raw_token = await create_email_token(
                session=session,
                user_id=user.id,
                purpose=EmailTokenPurpose.VERIFY_EMAIL.value,
                expires_at=_verify_expiry(),
            )
            background.add_task(
                mail.send_verification_email, email, display_name, raw_token
            )

        return RegisterResponse(
            id=user.id,
            email=email,
            display_name=display_name,
            tier="free",
            created_at=created_at,
        )


# ── Login ──────────────────────────────────────────────────────


@router.post(
    "/login",
    response_model=LoginResponse,
    summary="Log in with email and password",
    responses={401: {"description": "Invalid credentials"}},
)
async def login(body: LoginRequest, background: BackgroundTasks) -> LoginResponse:
    """Authenticate a user and return a JWT access token.

    Use this token in the ``Authorization: Bearer <token>`` header
    for subsequent API calls.
    """
    async with get_db_session() as session:
        user = await get_user_by_email(session, body.email)

        if user is None or not verify_password(body.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is deactivated",
            )

        if settings.enforce_email_verification and not user.email_verified:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Please verify your email before signing in. Check your inbox "
                "or request a new verification link.",
            )

        # Read fields inside the session before it closes.
        user_id = user.id
        email = user.email
        display_name = user.display_name
        email_verified = user.email_verified
        send_login_alert = bool(user.notification_prefs.get("security_alerts"))

    token = create_access_token(user_id=user_id, email=email)

    if send_login_alert:
        when = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        background.add_task(mail.send_new_login_email, email, display_name, when)

    return LoginResponse(
        access_token=token,
        user_id=user_id,
        email=email,
        display_name=display_name,
        email_verified=email_verified,
    )


# ── Email Verification ─────────────────────────────────────────


@router.post(
    "/verify-email",
    response_model=MessageResponse,
    summary="Confirm an email address with a token",
    responses={400: {"description": "Invalid or expired token"}},
)
async def verify_email(body: VerifyEmailRequest, background: BackgroundTasks) -> MessageResponse:
    """Confirm a signup email using the token from a verification link."""
    async with get_db_session() as session:
        token = await get_valid_email_token(
            session, body.token, EmailTokenPurpose.VERIFY_EMAIL.value
        )
        if token is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This verification link is invalid or has expired.",
            )

        user = await get_user_by_id(session, token.user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This verification link is invalid or has expired.",
            )

        email = user.email
        display_name = user.display_name
        account_events = bool(user.notification_prefs.get("account_events"))

        await consume_email_token(session, token)
        await mark_email_verified(session, user.id)
        if account_events:
            background.add_task(mail.send_welcome_email, email, display_name)

    return MessageResponse(message="Your email has been verified. You can now sign in.")


@router.post(
    "/resend-verification",
    response_model=MessageResponse,
    summary="Resend a verification email",
)
async def resend_verification(
    body: ResendVerificationRequest, background: BackgroundTasks
) -> MessageResponse:
    """Send a fresh verification link to an unverified account.

    Always returns success to avoid leaking which emails are registered.
    """
    async with get_db_session() as session:
        user = await get_user_by_email(session, body.email)
        if user is not None and not user.email_verified:
            email = user.email
            display_name = user.display_name
            raw_token = await create_email_token(
                session=session,
                user_id=user.id,
                purpose=EmailTokenPurpose.VERIFY_EMAIL.value,
                expires_at=_verify_expiry(),
            )
            background.add_task(
                mail.send_verification_email, email, display_name, raw_token
            )

    return MessageResponse(
        message="If that account exists and is unverified, a verification email is on its way."
    )


# ── Password Reset ─────────────────────────────────────────────


@router.post(
    "/forgot-password",
    response_model=MessageResponse,
    summary="Start a password reset",
)
async def forgot_password(
    body: ForgotPasswordRequest, background: BackgroundTasks
) -> MessageResponse:
    """Email a password-reset link.

    Always returns success to avoid leaking which emails are registered.
    """
    async with get_db_session() as session:
        user = await get_user_by_email(session, body.email)
        if user is not None and user.is_active:
            email = user.email
            display_name = user.display_name
            raw_token = await create_email_token(
                session=session,
                user_id=user.id,
                purpose=EmailTokenPurpose.RESET_PASSWORD.value,
                expires_at=_reset_expiry(),
            )
            background.add_task(
                mail.send_password_reset_email, email, display_name, raw_token
            )

    return MessageResponse(
        message="If an account with that email exists, a reset link is on its way."
    )


@router.post(
    "/reset-password",
    response_model=MessageResponse,
    summary="Complete a password reset with a token",
    responses={400: {"description": "Invalid or expired token"}},
)
async def reset_password(
    body: ResetPasswordRequest, background: BackgroundTasks
) -> MessageResponse:
    """Set a new password using the token from a reset link."""
    async with get_db_session() as session:
        token = await get_valid_email_token(
            session, body.token, EmailTokenPurpose.RESET_PASSWORD.value
        )
        if token is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This reset link is invalid or has expired.",
            )

        user = await get_user_by_id(session, token.user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This reset link is invalid or has expired.",
            )

        email = user.email
        display_name = user.display_name

        await consume_email_token(session, token)
        await update_user_password(session, user.id, body.new_password)

    # Password change is security-critical — always notify.
    background.add_task(mail.send_password_changed_email, email, display_name)

    return MessageResponse(message="Your password has been reset. You can now sign in.")


# ── API Key Management ────────────────────────────────────────


@router.post(
    "/api-keys",
    response_model=ApiKeyCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new API key",
)
async def create_key(
    body: CreateApiKeyRequest,
    auth: AuthContext = Depends(require_jwt_user),
) -> ApiKeyCreatedResponse:
    """Generate a new API key for programmatic access.

    The raw key is returned **only once** in this response.
    Store it securely — you cannot retrieve it again.
    """
    raw_key, prefix = generate_api_key()

    async with get_db_session() as session:
        record = await create_api_key_record(
            session=session,
            user_id=auth.user_id,
            raw_key=raw_key,
            prefix=prefix,
            name=body.name,
        )

        return ApiKeyCreatedResponse(
            id=record.id,
            name=record.name,
            prefix=record.prefix,
            key=raw_key,
            created_at=record.created_at,
        )


@router.get(
    "/api-keys",
    response_model=ApiKeyListResponse,
    summary="List all API keys",
)
async def list_keys(
    auth: AuthContext = Depends(require_jwt_user),
) -> ApiKeyListResponse:
    """List all non-revoked API keys for the authenticated user.

    The raw key values are **not** returned — only metadata.
    """
    async with get_db_session() as session:
        keys = await list_api_keys(session, auth.user_id)

    items = [
        ApiKeyListItem(
            id=k.id,
            name=k.name,
            prefix=k.prefix,
            revoked=k.revoked,
            last_used_at=k.last_used_at,
            created_at=k.created_at,
        )
        for k in keys
    ]

    return ApiKeyListResponse(keys=items, count=len(items))


@router.delete(
    "/api-keys/{key_id}",
    response_model=MessageResponse,
    summary="Revoke an API key",
    responses={404: {"description": "API key not found"}},
)
async def revoke_key(
    key_id: str,
    auth: AuthContext = Depends(require_jwt_user),
) -> MessageResponse:
    """Revoke an API key. This action cannot be undone.

    The key will immediately stop working for authentication.
    """
    async with get_db_session() as session:
        revoked = await revoke_api_key(session, key_id, auth.user_id)

    if not revoked:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found or already revoked",
        )

    return MessageResponse(message="API key revoked successfully")
