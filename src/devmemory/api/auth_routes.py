"""REST API routes for user authentication and API key management."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError

from devmemory.api.schemas import (
    ApiKeyCreatedResponse,
    ApiKeyListItem,
    ApiKeyListResponse,
    CreateApiKeyRequest,
    LoginRequest,
    LoginResponse,
    MessageResponse,
    RegisterRequest,
    RegisterResponse,
)
from devmemory.auth.hashing import generate_api_key, verify_password
from devmemory.auth.jwt_utils import create_access_token
from devmemory.auth.middleware import AuthContext, require_jwt_user
from devmemory.db.engine import get_db_session
from devmemory.db.repository import (
    create_api_key_record,
    create_user,
    get_user_by_email,
    list_api_keys,
    revoke_api_key,
)

router = APIRouter(prefix="/auth", tags=["auth"])


# ── Registration ───────────────────────────────────────────────

@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
    responses={409: {"description": "Email already registered"}},
)
async def register(body: RegisterRequest) -> RegisterResponse:
    """Create a new user account with a free-tier subscription.

    The user will receive a free-tier subscription automatically.
    Use the ``/auth/login`` endpoint to get a JWT token.
    """
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
            )
        except IntegrityError:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email already exists",
            )

        return RegisterResponse(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            tier="free",
            created_at=user.created_at,
        )


# ── Login ──────────────────────────────────────────────────────

@router.post(
    "/login",
    response_model=LoginResponse,
    summary="Log in with email and password",
    responses={401: {"description": "Invalid credentials"}},
)
async def login(body: LoginRequest) -> LoginResponse:
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

    token = create_access_token(user_id=user.id, email=user.email)

    return LoginResponse(
        access_token=token,
        user_id=user.id,
        email=user.email,
    )


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
