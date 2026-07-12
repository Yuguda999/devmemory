"""Low-level SMTP delivery via the standard-library ``smtplib``.

Sending is blocking, so it runs in a worker thread (``asyncio.to_thread``) to
keep the event loop free. If SMTP is not configured (``settings.email_enabled``
is False) the email is logged instead of sent, so local/self-hosted development
works without a mail server and no flow ever hard-fails on a missing config.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import smtplib
from email.message import EmailMessage

from devmemory.config import settings

logger = logging.getLogger(__name__)


def _send_sync(message: EmailMessage) -> None:
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


async def send_email(to: str, subject: str, html: str, text: str) -> bool:
    """Send a multipart (text + HTML) email.

    Args:
        to: Recipient address.
        subject: Subject line.
        html: HTML body.
        text: Plain-text fallback body.

    Returns:
        True if handed to the SMTP server, False if only logged (SMTP off) or
        delivery failed. Callers should treat this as best-effort — email is
        never allowed to break the request flow.
    """
    if not settings.email_enabled:
        logger.info(
            "[email:disabled] would send to=%s subject=%r\n%s",
            to,
            subject,
            text,
        )
        return False

    message = EmailMessage()
    message["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
    message["To"] = to
    message["Subject"] = subject
    message.set_content(text)
    message.add_alternative(html, subtype="html")

    try:
        await asyncio.to_thread(_send_sync, message)
        logger.info("[email:sent] to=%s subject=%r", to, subject)
        return True
    except Exception:  # noqa: BLE001 — email must never crash the caller
        logger.exception("[email:error] failed to send to=%s subject=%r", to, subject)
        return False
