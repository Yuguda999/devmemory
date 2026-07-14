"""Tests for the mailer: link building, templates, and config gating."""

from __future__ import annotations

import pytest

from devmemory.config import DeploymentMode, Settings
from devmemory.mailer import service, templates

# ── Config gating ──────────────────────────────────────────────


def test_email_disabled_without_smtp_host():
    s = Settings(smtp_host=None)
    assert s.email_enabled is False


def test_email_enabled_with_smtp_host():
    s = Settings(smtp_host="smtp.example.com")
    assert s.email_enabled is True


def test_email_enabled_with_sendgrid_key():
    s = Settings(smtp_host=None, sendgrid_api_key="SG.abc")
    assert s.email_enabled is True


def test_enforce_verification_requires_saas_and_email():
    # Self-hosted with email → not enforced.
    s1 = Settings(deployment_mode=DeploymentMode.SELF_HOSTED, smtp_host="smtp.x")
    assert s1.enforce_email_verification is False
    # SaaS without email → not enforced (would lock users out).
    s2 = Settings(deployment_mode=DeploymentMode.SAAS, smtp_host=None)
    assert s2.enforce_email_verification is False
    # SaaS + SMTP → enforced.
    s3 = Settings(deployment_mode=DeploymentMode.SAAS, smtp_host="smtp.x")
    assert s3.enforce_email_verification is True
    # SaaS + SendGrid → enforced.
    s4 = Settings(deployment_mode=DeploymentMode.SAAS, sendgrid_api_key="SG.x")
    assert s4.enforce_email_verification is True


# ── Link building ──────────────────────────────────────────────


def test_link_builder(monkeypatch):
    monkeypatch.setattr(service.settings, "app_base_url", "https://app.devmemory.io/")
    link = service._link("verify", "TOK123")
    assert link == "https://app.devmemory.io/app#verify?token=TOK123"


# ── Templates ──────────────────────────────────────────────────


def test_verification_template_contains_link():
    subject, html, text = templates.verification_email("Alice", "https://x/app#verify?token=abc")
    assert "verify" in subject.lower()
    assert "https://x/app#verify?token=abc" in html
    assert "https://x/app#verify?token=abc" in text
    assert "Alice" in html


def test_reset_template_shows_expiry():
    subject, html, text = templates.password_reset_email("Bob", "https://x/reset", 30)
    assert "reset" in subject.lower()
    assert "30 minutes" in text
    assert "https://x/reset" in html


@pytest.mark.parametrize(
    "builder,args",
    [
        (templates.welcome_email, ("Dee", "https://x/app")),
        (templates.password_changed_email, ("Dee",)),
        (templates.new_login_email, ("Dee", "2026-07-12 16:00 UTC")),
    ],
)
def test_all_templates_return_three_nonempty_parts(builder, args):
    subject, html, text = builder(*args)
    assert subject and html and text
    assert "<html" in html.lower()


# ── Sender backends ────────────────────────────────────────────


async def test_send_email_logs_and_returns_false_when_disabled(monkeypatch):
    from devmemory.mailer import sender

    monkeypatch.setattr(sender.settings, "smtp_host", None)
    monkeypatch.setattr(sender.settings, "sendgrid_api_key", None)
    result = await sender.send_email("to@x.com", "Subj", "<p>hi</p>", "hi")
    assert result is False


class _FakeResp:
    def __init__(self, code, text=""):
        self.status_code = code
        self.text = text


class _FakeClient:
    captured: dict = {}

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, json, headers):
        _FakeClient.captured = {"url": url, "json": json, "headers": headers}
        return _FakeResp(202)


async def test_send_via_sendgrid_when_key_set(monkeypatch):
    from devmemory.mailer import sender

    monkeypatch.setattr(sender.settings, "sendgrid_api_key", "SG.testkey")
    monkeypatch.setattr(sender.settings, "smtp_host", "smtp.should-not-be-used")
    monkeypatch.setattr(sender.settings, "smtp_from_email", "sender@example.com")
    monkeypatch.setattr(sender.httpx, "AsyncClient", _FakeClient)

    result = await sender.send_email("to@x.com", "Subj", "<p>hi</p>", "hi")
    assert result is True

    cap = _FakeClient.captured
    assert cap["url"] == sender._SENDGRID_URL
    assert cap["headers"]["Authorization"] == "Bearer SG.testkey"
    assert cap["json"]["personalizations"][0]["to"][0]["email"] == "to@x.com"
    assert cap["json"]["from"]["email"] == "sender@example.com"
    # Both text and HTML parts included.
    types = {c["type"] for c in cap["json"]["content"]}
    assert types == {"text/plain", "text/html"}


async def test_sendgrid_non_2xx_returns_false(monkeypatch):
    from devmemory.mailer import sender

    class _ErrClient(_FakeClient):
        async def post(self, url, json, headers):
            return _FakeResp(401, "unauthorized")

    monkeypatch.setattr(sender.settings, "sendgrid_api_key", "SG.bad")
    monkeypatch.setattr(sender.httpx, "AsyncClient", _ErrClient)
    result = await sender.send_email("to@x.com", "Subj", "<p>hi</p>", "hi")
    assert result is False
