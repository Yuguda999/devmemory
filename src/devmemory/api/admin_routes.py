"""Superadmin REST routes — platform stats, user management, payments.

Every endpoint requires ``require_admin`` (an authenticated user whose DB
``is_admin`` flag is set, or whose email is in ``DEVMEMORY_ADMIN_EMAILS``).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from devmemory.api.schemas import (
    AdminInvoiceList,
    AdminInvoiceRow,
    AdminStatsResponse,
    AdminUpdateUserRequest,
    AdminUserList,
    AdminUserRow,
)
from devmemory.auth.middleware import AuthContext, require_admin
from devmemory.db.engine import get_db_session
from devmemory.db.repository import (
    admin_update_user,
    list_invoices_admin,
    list_users_admin,
    platform_stats,
)
from devmemory.models.subscription import SubscriptionTier

router = APIRouter(prefix="/admin", tags=["admin"])

_VALID_TIERS = {t.value for t in SubscriptionTier}


@router.get("/stats", response_model=AdminStatsResponse, summary="Platform overview stats")
async def admin_stats(auth: AuthContext = Depends(require_admin)) -> AdminStatsResponse:
    async with get_db_session() as db:
        return AdminStatsResponse(**await platform_stats(db))


@router.get("/users", response_model=AdminUserList, summary="List all users")
async def admin_users(
    search: str | None = Query(None, description="Filter by email substring"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    auth: AuthContext = Depends(require_admin),
) -> AdminUserList:
    async with get_db_session() as db:
        users, proj, sess, total = await list_users_admin(db, search, limit, offset)
        rows = [
            AdminUserRow(
                id=u.id,
                email=u.email,
                display_name=u.display_name,
                tier=(u.subscription.tier if u.subscription else SubscriptionTier.FREE.value),
                is_active=u.is_active,
                is_admin=u.is_admin,
                email_verified=u.email_verified,
                projects=proj.get(u.id, 0),
                sessions=sess.get(u.id, 0),
                created_at=u.created_at,
            )
            for u in users
        ]
    return AdminUserList(users=rows, total=total)


@router.patch("/users/{user_id}", response_model=AdminUserRow, summary="Update a user")
async def admin_patch_user(
    user_id: str,
    body: AdminUpdateUserRequest,
    auth: AuthContext = Depends(require_admin),
) -> AdminUserRow:
    if body.tier is not None and body.tier not in _VALID_TIERS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Invalid tier '{body.tier}'. Must be one of: {', '.join(sorted(_VALID_TIERS))}",
        )
    # Guard: an admin cannot revoke their own admin/active status and lock
    # themselves out mid-request.
    if user_id == auth.user_id and (body.is_admin is False or body.is_active is False):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot remove your own admin or active status.",
        )

    async with get_db_session() as db:
        user = await admin_update_user(
            db,
            user_id,
            tier=body.tier,
            is_active=body.is_active,
            is_admin=body.is_admin,
        )
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        return AdminUserRow(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            tier=(user.subscription.tier if user.subscription else SubscriptionTier.FREE.value),
            is_active=user.is_active,
            is_admin=user.is_admin,
            email_verified=user.email_verified,
            projects=0,
            sessions=0,
            created_at=user.created_at,
        )


@router.get("/invoices", response_model=AdminInvoiceList, summary="List all payments")
async def admin_invoices(
    status_filter: str | None = Query(None, alias="status", description="pending|paid|expired"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    auth: AuthContext = Depends(require_admin),
) -> AdminInvoiceList:
    async with get_db_session() as db:
        rows, total = await list_invoices_admin(db, status_filter, limit, offset)
        invoices = [
            AdminInvoiceRow(
                id=inv.id,
                user_email=email,
                tier=inv.tier,
                status=inv.status,
                amount_ada=inv.amount_ada,
                network=inv.network,
                tx_hash=inv.tx_hash,
                created_at=inv.created_at,
            )
            for inv, email in rows
        ]
    return AdminInvoiceList(invoices=invoices, total=total)
