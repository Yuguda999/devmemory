"""High-level email senders.

These are the functions route handlers schedule via ``BackgroundTasks``. They
take plain values (never ORM objects, which may be detached from their session
in a background task) and delegate to templates + the SMTP sender.

Notification-preference gating (security_alerts / account_events) is done by the
CALLER before scheduling — transactional mail here is always attempted.
"""

from __future__ import annotations

from devmemory.config import settings
from devmemory.mailer import templates
from devmemory.mailer.sender import send_email


def _link(hash_route: str, token: str) -> str:
    """Build a dashboard deep link carrying a token, e.g. .../app#verify?token=XYZ."""
    base = settings.app_base_url.rstrip("/")
    return f"{base}/app#{hash_route}?token={token}"


async def send_verification_email(to_email: str, display_name: str, raw_token: str) -> bool:
    subject, html, text = templates.verification_email(display_name, _link("verify", raw_token))
    return await send_email(to_email, subject, html, text)


async def send_welcome_email(to_email: str, display_name: str) -> bool:
    app_url = f"{settings.app_base_url.rstrip('/')}/app#dashboard"
    subject, html, text = templates.welcome_email(display_name, app_url)
    return await send_email(to_email, subject, html, text)


async def send_password_reset_email(to_email: str, display_name: str, raw_token: str) -> bool:
    subject, html, text = templates.password_reset_email(
        display_name, _link("reset", raw_token), settings.password_reset_expiry_minutes
    )
    return await send_email(to_email, subject, html, text)


async def send_password_changed_email(to_email: str, display_name: str) -> bool:
    subject, html, text = templates.password_changed_email(display_name)
    return await send_email(to_email, subject, html, text)


async def send_new_login_email(to_email: str, display_name: str, when: str) -> bool:
    subject, html, text = templates.new_login_email(display_name, when)
    return await send_email(to_email, subject, html, text)
