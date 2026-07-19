"""Outbound transactional email — SMTP delivery, templates, and pref-gated sends.

Named ``mailer`` (not ``email``) to avoid shadowing the Python standard-library
``email`` package that the message builders rely on.
"""

from devmemory.mailer.sender import send_email

__all__ = ["send_email"]
