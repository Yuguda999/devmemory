"""Unit tests for Phase 4 REST API routes.

Uses FastAPI TestClient with mocked DB and auth dependencies so no real
database is required.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from devmemory.api.app import create_app
from devmemory.auth.middleware import (
    AuthContext,
    require_admin,
    require_jwt_user,
    require_user,
)
from devmemory.models.subscription import SubscriptionTier

# ── Fixtures ───────────────────────────────────────────────────────────────────


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class _Project:
    id: str = "proj-1"
    slug: str = "user-myproject"
    name: str = "myproject"
    remote_url: str | None = "https://github.com/user/myproject"
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)


@dataclass
class _Session:
    id: str = "sess-1"
    project_id: str = "proj-1"
    title: str = "Test session"
    status: str = "active"
    tool_source: str = "claude"
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)
    context_blocks: list = field(default_factory=list)
    project: Any = field(default_factory=_Project)


@dataclass
class _Block:
    id: str = "block-1"
    session_id: str = "sess-1"
    block_type: str = "goal"
    content: str = "Implement the API layer"
    priority: int = 5
    meta_json: str | None = None
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)


_FAKE_AUTH = AuthContext(
    user_id="user-uuid",
    email="dev@example.com",
    tier=SubscriptionTier.FREE,
)

_USAGE_SUMMARY = {
    "tier": "free",
    "limits": {"max_projects": 3, "max_sessions_per_project": 10, "max_blocks_per_session": 500},
    "usage": {"projects": 1, "total_sessions": 2},
}


@pytest.fixture()
def client():
    """Return a TestClient with JWT auth dependency overridden."""
    app = create_app()
    app.dependency_overrides[require_jwt_user] = lambda: _FAKE_AUTH
    app.dependency_overrides[require_user] = lambda: _FAKE_AUTH
    return TestClient(app, raise_server_exceptions=True)


# ── /projects ──────────────────────────────────────────────────────────────────


class TestProjectRoutes:
    def test_list_projects_returns_200(self, client):
        projects = [_Project(id="p1", slug="a", name="A"), _Project(id="p2", slug="b", name="B")]

        with patch(
            "devmemory.api.project_routes.list_projects",
            AsyncMock(return_value=projects),
        ):
            response = client.get("/projects")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2
        assert data["projects"][0]["slug"] == "a"
        assert data["projects"][1]["id"] == "p2"

    def test_list_projects_empty(self, client):
        with patch(
            "devmemory.api.project_routes.list_projects",
            AsyncMock(return_value=[]),
        ):
            response = client.get("/projects")

        assert response.status_code == 200
        assert response.json() == {"projects": [], "count": 0}


# ── /sessions ──────────────────────────────────────────────────────────────────


class TestSessionRoutes:
    def test_list_sessions_returns_200(self, client):
        sessions = [_Session(id="s1"), _Session(id="s2", title="Other")]

        with patch(
            "devmemory.api.session_routes.list_sessions",
            AsyncMock(return_value=sessions),
        ):
            response = client.get("/sessions")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2
        assert data["sessions"][0]["id"] == "s1"

    def test_list_sessions_filter_by_project(self, client):
        with patch(
            "devmemory.api.session_routes.list_sessions",
            AsyncMock(return_value=[_Session()]),
        ) as mock_list:
            response = client.get("/sessions?project_id=proj-1&status=active")

        assert response.status_code == 200
        call_kwargs = mock_list.call_args.kwargs
        assert call_kwargs["project_id"] == "proj-1"
        assert call_kwargs["status"] == "active"

    def test_list_sessions_invalid_status_returns_422(self, client):
        response = client.get("/sessions?status=invalid_status")
        assert response.status_code == 422

    def test_get_session_returns_200(self, client):
        with patch(
            "devmemory.api.session_routes.get_session",
            AsyncMock(return_value=_Session()),
        ):
            response = client.get("/sessions/sess-1")

        assert response.status_code == 200
        assert response.json()["id"] == "sess-1"
        assert response.json()["title"] == "Test session"

    def test_get_session_not_found_returns_404(self, client):
        with patch(
            "devmemory.api.session_routes.get_session",
            AsyncMock(return_value=None),
        ):
            response = client.get("/sessions/ghost-id")

        assert response.status_code == 404

    def test_patch_session_title(self, client):
        updated = _Session(title="Renamed session")

        with patch(
            "devmemory.api.session_routes.update_session",
            AsyncMock(return_value=updated),
        ):
            response = client.patch(
                "/sessions/sess-1",
                json={"title": "Renamed session"},
            )

        assert response.status_code == 200
        assert response.json()["title"] == "Renamed session"

    def test_patch_session_status(self, client):
        updated = _Session(status="completed")

        with patch(
            "devmemory.api.session_routes.update_session",
            AsyncMock(return_value=updated),
        ):
            response = client.patch(
                "/sessions/sess-1",
                json={"status": "completed"},
            )

        assert response.status_code == 200
        assert response.json()["status"] == "completed"

    def test_patch_session_invalid_status_returns_422(self, client):
        response = client.patch("/sessions/sess-1", json={"status": "deleted"})
        assert response.status_code == 422

    def test_patch_session_no_fields_returns_422(self, client):
        response = client.patch("/sessions/sess-1", json={})
        assert response.status_code == 422

    def test_patch_session_not_found_returns_404(self, client):
        with patch(
            "devmemory.api.session_routes.update_session",
            AsyncMock(return_value=None),
        ):
            response = client.patch("/sessions/ghost", json={"title": "x"})

        assert response.status_code == 404


# ── /sessions/{id}/blocks ──────────────────────────────────────────────────────


class TestContextBlockRoutes:
    def test_list_blocks_returns_200(self, client):
        blocks = [_Block(), _Block(id="b2", block_type="next_step")]

        with patch(
            "devmemory.api.session_routes.get_context_blocks",
            AsyncMock(return_value=blocks),
        ):
            response = client.get("/sessions/sess-1/blocks")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2
        assert data["blocks"][0]["block_type"] == "goal"

    def test_list_blocks_session_not_found_returns_404(self, client):
        with patch(
            "devmemory.api.session_routes.get_context_blocks",
            AsyncMock(return_value=None),
        ):
            response = client.get("/sessions/ghost/blocks")

        assert response.status_code == 404

    def test_delete_block_returns_200(self, client):
        with patch(
            "devmemory.api.session_routes.delete_context_block",
            AsyncMock(return_value=True),
        ):
            response = client.delete("/context-blocks/block-1")

        assert response.status_code == 200
        assert "deleted" in response.json()["message"]

    def test_delete_block_not_found_returns_404(self, client):
        with patch(
            "devmemory.api.session_routes.delete_context_block",
            AsyncMock(return_value=False),
        ):
            response = client.delete("/context-blocks/ghost-block")

        assert response.status_code == 404


# ── /billing/status ────────────────────────────────────────────────────────────


class TestBillingRoutes:
    def test_billing_status_returns_200(self, client):
        with patch(
            "devmemory.api.billing_routes.get_usage_summary",
            AsyncMock(return_value=_USAGE_SUMMARY),
        ):
            response = client.get("/billing/status")

        assert response.status_code == 200
        data = response.json()
        assert data["tier"] == "free"
        assert data["limits"]["max_projects"] == 3
        assert data["usage"]["projects"] == 1
        assert data["usage"]["total_sessions"] == 2

    def test_billing_status_team_has_null_limits(self, client):
        team_summary = {
            "tier": "team",
            "limits": {
                "max_projects": None,
                "max_sessions_per_project": None,
                "max_blocks_per_session": None,
            },
            "usage": {"projects": 50, "total_sessions": 400},
        }

        with patch(
            "devmemory.api.billing_routes.get_usage_summary",
            AsyncMock(return_value=team_summary),
        ):
            response = client.get("/billing/status")

        assert response.status_code == 200
        data = response.json()
        assert data["tier"] == "team"
        assert data["limits"]["max_projects"] is None


# ── /billing/upgrade + /billing/invoice (Cardano payments) ──────────────────────


@dataclass
class _Invoice:
    id: str = "inv-1"
    user_id: str = "user-uuid"
    tier: str = "pro"
    amount_lovelace: int = 10_000_000
    pay_to_address: str = "addr_test1qderived0"
    derivation_index: int = 0
    network: str = "preprod"
    status: str = "pending"
    tx_hash: str | None = None
    expires_at: datetime = field(default_factory=lambda: datetime(2999, 1, 1, tzinfo=timezone.utc))
    created_at: datetime = field(default_factory=_now)

    @property
    def amount_ada(self) -> float:
        return self.amount_lovelace / 1_000_000


def _enable_payments(allow_test: bool = False):
    """Return patchers so payments_enabled is True (unique-address flow)."""
    from devmemory.config import settings

    return (
        patch.object(settings, "blockfrost_project_id", "preprodTEST"),
        patch.object(settings, "cardano_account_xpub", "acct_xvk1test"),
        patch.object(settings, "cardano_allow_test_payments", allow_test),
    )


class TestPaymentRoutes:
    def test_upgrade_returns_503_when_not_configured(self, client):
        # Explicitly unconfigure payments (don't rely on env defaults, which a
        # developer's real .env may have populated).
        from devmemory.config import settings

        with patch.object(settings, "blockfrost_project_id", None), patch.object(
            settings, "cardano_account_xpub", None
        ):
            response = client.post("/billing/upgrade", json={"tier": "pro"})
        assert response.status_code == 503

    def test_upgrade_creates_invoice(self, client):
        p1, p2, p3 = _enable_payments()
        with p1, p2, p3, patch(
            "devmemory.api.billing_routes.next_derivation_index",
            AsyncMock(return_value=0),
        ), patch(
            "devmemory.api.billing_routes.derive_address",
            return_value="addr_test1qderived0",
        ), patch(
            "devmemory.api.billing_routes.create_invoice",
            AsyncMock(return_value=_Invoice()),
        ):
            response = client.post("/billing/upgrade", json={"tier": "pro"})

        assert response.status_code == 200
        data = response.json()
        assert data["tier"] == "pro"
        assert data["status"] == "pending"
        assert data["pay_to_address"] == "addr_test1qderived0"
        assert data["amount_ada"] == pytest.approx(10.0)

    def test_upgrade_invalid_tier_422(self, client):
        p1, p2, p3 = _enable_payments()
        with p1, p2, p3:
            response = client.post("/billing/upgrade", json={"tier": "gold"})
        assert response.status_code == 422

    def test_check_invoice_confirms_and_upgrades(self, client):
        invoice = _Invoice(status="pending")

        async def _mark_paid(db, inv, tx_hash):
            inv.status = "paid"
            inv.tx_hash = tx_hash

        p1, p2, p3 = _enable_payments()
        with p1, p2, p3, patch(
            "devmemory.api.billing_routes.get_invoice",
            AsyncMock(return_value=invoice),
        ), patch(
            "devmemory.billing.settlement.find_matching_payment",
            AsyncMock(return_value="txCONFIRMED"),
        ), patch(
            "devmemory.billing.settlement.mark_invoice_paid",
            AsyncMock(side_effect=_mark_paid),
        ), patch(
            "devmemory.billing.settlement.apply_tier_upgrade",
            AsyncMock(return_value=None),
        ) as mock_upgrade:
            response = client.get("/billing/invoice/inv-1")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "paid"
        assert data["tx_hash"] == "txCONFIRMED"
        assert mock_upgrade.call_args.kwargs["tier"] == "pro"

    def test_check_invoice_still_pending(self, client):
        p1, p2, p3 = _enable_payments()
        with p1, p2, p3, patch(
            "devmemory.api.billing_routes.get_invoice",
            AsyncMock(return_value=_Invoice(status="pending")),
        ), patch(
            "devmemory.billing.settlement.find_matching_payment",
            AsyncMock(return_value=None),
        ):
            response = client.get("/billing/invoice/inv-1")

        assert response.status_code == 200
        assert response.json()["status"] == "pending"

    def test_check_invoice_not_found_404(self, client):
        p1, p2, p3 = _enable_payments()
        with p1, p2, p3, patch(
            "devmemory.api.billing_routes.get_invoice",
            AsyncMock(return_value=None),
        ):
            response = client.get("/billing/invoice/ghost")
        assert response.status_code == 404

    def test_simulate_paid_disabled_by_default_404(self, client):
        p1, p2, p3 = _enable_payments(allow_test=False)
        with p1, p2, p3:
            response = client.post("/billing/invoice/inv-1/simulate-paid")
        assert response.status_code == 404

    def test_simulate_paid_upgrades_when_allowed(self, client):
        invoice = _Invoice(status="pending")

        async def _mark_paid(db, inv, tx_hash):
            inv.status = "paid"
            inv.tx_hash = tx_hash

        p1, p2, p3 = _enable_payments(allow_test=True)
        with p1, p2, p3, patch(
            "devmemory.api.billing_routes.get_invoice",
            AsyncMock(return_value=invoice),
        ), patch(
            "devmemory.api.billing_routes.mark_invoice_paid",
            AsyncMock(side_effect=_mark_paid),
        ), patch(
            "devmemory.api.billing_routes.apply_tier_upgrade",
            AsyncMock(return_value=None),
        ) as mock_upgrade:
            response = client.post("/billing/invoice/inv-1/simulate-paid")

        assert response.status_code == 200
        assert response.json()["status"] == "paid"
        assert mock_upgrade.call_args.kwargs["tier"] == "pro"


# ── /connections ─────────────────────────────────────────────────────────────────


@dataclass
class _Conn:
    client: str = "cursor"
    client_version: str | None = None
    last_seen_at: datetime = field(default_factory=_now)
    created_at: datetime = field(default_factory=_now)


class TestConnectionRoutes:
    def test_list_connections_derives_status(self, client):
        from datetime import timedelta

        now = _now()
        conns = [
            _Conn(client="cursor", last_seen_at=now),  # connected
            _Conn(client="claude-code", last_seen_at=now - timedelta(minutes=30)),  # idle
            _Conn(client="windsurf", last_seen_at=now - timedelta(hours=5)),  # offline
        ]

        with patch(
            "devmemory.api.connection_routes.list_tool_connections",
            AsyncMock(return_value=conns),
        ):
            response = client.get("/connections")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 3
        by_client = {c["client"]: c["status"] for c in data["connections"]}
        assert by_client == {
            "cursor": "connected",
            "claude-code": "idle",
            "windsurf": "offline",
        }

    def test_list_connections_empty(self, client):
        with patch(
            "devmemory.api.connection_routes.list_tool_connections",
            AsyncMock(return_value=[]),
        ):
            response = client.get("/connections")

        assert response.status_code == 200
        assert response.json() == {"connections": [], "count": 0}


# ── /admin (superadmin) ─────────────────────────────────────────────────────────


@dataclass
class _Sub:
    tier: str = "pro"


@dataclass
class _AdminUser:
    id: str = "u1"
    email: str = "user@example.com"
    display_name: str = "User One"
    is_active: bool = True
    is_admin: bool = False
    email_verified: bool = True
    subscription: Any = field(default_factory=_Sub)
    created_at: datetime = field(default_factory=_now)


_ADMIN_AUTH = AuthContext(
    user_id="admin-uuid",
    email="admin@example.com",
    tier=SubscriptionTier.TEAM,
    is_admin=True,
)

_STATS = {
    "users_total": 5,
    "users_active": 4,
    "users_verified": 3,
    "tiers": {"free": 3, "pro": 2},
    "projects": 10,
    "sessions": 20,
    "context_blocks": 100,
    "invoices_paid": 2,
    "invoices_pending": 1,
    "revenue_ada": 20.0,
}


@pytest.fixture()
def admin_client(client):
    """Client whose require_admin resolves to an admin context."""
    client.app.dependency_overrides[require_admin] = lambda: _ADMIN_AUTH
    return client


class TestAdminRoutes:
    def test_non_admin_gets_403(self, client):
        # client overrides require_jwt_user with a non-admin context; require_admin
        # runs for real and must reject it.
        assert client.get("/admin/stats").status_code == 403

    def test_stats(self, admin_client):
        with patch(
            "devmemory.api.admin_routes.platform_stats",
            AsyncMock(return_value=_STATS),
        ):
            r = admin_client.get("/admin/stats")
        assert r.status_code == 200
        assert r.json()["users_total"] == 5
        assert r.json()["revenue_ada"] == 20.0

    def test_list_users(self, admin_client):
        with patch(
            "devmemory.api.admin_routes.list_users_admin",
            AsyncMock(return_value=([_AdminUser()], {"u1": 3}, {"u1": 7}, 1)),
        ):
            r = admin_client.get("/admin/users")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 1
        assert data["users"][0]["tier"] == "pro"
        assert data["users"][0]["projects"] == 3
        assert data["users"][0]["sessions"] == 7

    def test_patch_user_tier(self, admin_client):
        with patch(
            "devmemory.api.admin_routes.admin_update_user",
            AsyncMock(return_value=_AdminUser(subscription=_Sub(tier="team"))),
        ):
            r = admin_client.patch("/admin/users/u1", json={"tier": "team"})
        assert r.status_code == 200
        assert r.json()["tier"] == "team"

    def test_patch_invalid_tier_422(self, admin_client):
        r = admin_client.patch("/admin/users/u1", json={"tier": "gold"})
        assert r.status_code == 422

    def test_cannot_self_demote(self, admin_client):
        # admin acting on their own id, removing admin → 400
        r = admin_client.patch("/admin/users/admin-uuid", json={"is_admin": False})
        assert r.status_code == 400

    def test_list_invoices(self, admin_client):
        inv = _Invoice(status="paid", tx_hash="abc123def456ghi", tier="pro")
        with patch(
            "devmemory.api.admin_routes.list_invoices_admin",
            AsyncMock(return_value=([(inv, "buyer@example.com")], 1)),
        ):
            r = admin_client.get("/admin/invoices?status=paid")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 1
        assert data["invoices"][0]["user_email"] == "buyer@example.com"
        assert data["invoices"][0]["amount_ada"] == 10.0
