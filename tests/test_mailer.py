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


def test_enforce_verification_requires_saas_and_email():
    # Self-hosted with email → not enforced.
    s1 = Settings(deployment_mode=DeploymentMode.SELF_HOSTED, smtp_host="smtp.x")
    assert s1.enforce_email_verification is False
    # SaaS without email → not enforced (would lock users out).
    s2 = Settings(deployment_mode=DeploymentMode.SAAS, smtp_host=None)
    assert s2.enforce_email_verification is False
    # SaaS + email → enforced.
    s3 = Settings(deployment_mode=DeploymentMode.SAAS, smtp_host="smtp.x")
    assert s3.enforce_email_verification is True


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


# ── Sender fallback (no SMTP configured) ───────────────────────


async def test_send_email_logs_and_returns_false_when_disabled(monkeypatch):
    from devmemory.mailer import sender

    monkeypatch.setattr(sender.settings, "smtp_host", None)
    result = await sender.send_email("to@x.com", "Subj", "<p>hi</p>", "hi")
    assert result is False
