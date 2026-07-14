"""Outbound email delivery with an auto-selected backend.

Backends, in priority order (see ``config``):
  1. SendGrid HTTP API over HTTPS/443 — works on hosts that block outbound SMTP
     (e.g. Render). Async via httpx.
  2. SMTP via the standard-library ``smtplib`` — blocking, so it runs in a
     worker thread.
  3. Neither configured — the email is logged instead of sent, so local /
     self-hosted development works without any mail setup and no flow ever
     hard-fails on a missing config.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import smtplib
from email.message import EmailMessage

import httpx

from devmemory.config import settings

logger = logging.getLogger(__name__)

_SENDGRID_URL = "https://api.sendgrid.com/v3/mail/send"


async def _send_sendgrid(to: str, subject: str, html: str, text: str) -> bool:
    """Send via the SendGrid v3 HTTP API. Returns True on a 2xx response."""
    payload = {
        "personalizations": [{"to": [{"email": to}]}],
        "from": {"email": settings.smtp_from_email, "name": settings.smtp_from_name},
        "subject": subject,
        "content": [
            {"type": "text/plain", "value": text},
            {"type": "text/html", "value": html},
        ],
    }
    headers = {
        "Authorization": f"Bearer {settings.sendgrid_api_key}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(_SENDGRID_URL, json=payload, headers=headers)
    if resp.status_code // 100 == 2:
        logger.info("[email:sent] via=sendgrid to=%s subject=%r", to, subject)
        return True
    # SendGrid returns error detail in the body — surface it for debugging.
    logger.error(
        "[email:error] sendgrid %s to=%s subject=%r body=%s",
        resp.status_code,
        to,
        subject,
        resp.text[:500],
    )
    return False


def _send_smtp_sync(message: EmailMessage) -> None:
    """Blocking SMTP send. Runs in a worker thread."""
    if settings.smtp_use_ssl:
        smtp: smtplib.SMTP = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=15)
    else:
        smtp = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15)
    try:
        smtp.ehlo()
        if settings.smtp_use_tls and not settings.smtp_use_ssl:
            smtp.starttls()
            smtp.ehlo()
        if settings.smtp_user and settings.smtp_password:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(message)
    finally:
        with contextlib.suppress(Exception):  # closing best-effort
            smtp.quit()


async def _send_smtp(to: str, subject: str, html: str, text: str) -> bool:
    message = EmailMessage()
    message["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
    message["To"] = to
    message["Subject"] = subject
    message.set_content(text)
    message.add_alternative(html, subtype="html")
    await asyncio.to_thread(_send_smtp_sync, message)
    logger.info("[email:sent] via=smtp to=%s subject=%r", to, subject)
    return True


async def send_email(to: str, subject: str, html: str, text: str) -> bool:
    """Send a multipart (text + HTML) email via the configured backend.

    Returns:
        True if handed to a provider, False if only logged (no backend) or
        delivery failed. Callers treat this as best-effort — email is never
        allowed to break the request flow.
    """
    if not settings.email_enabled:
        logger.info(
            "[email:disabled] would send to=%s subject=%r\n%s", to, subject, text
        )
        return False

    try:
        if settings.sendgrid_api_key:
            return await _send_sendgrid(to, subject, html, text)
        return await _send_smtp(to, subject, html, text)
    except Exception:  # noqa: BLE001 — email must never crash the caller
        logger.exception("[email:error] failed to send to=%s subject=%r", to, subject)
        return False
