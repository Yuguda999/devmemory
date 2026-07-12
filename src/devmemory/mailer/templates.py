"""HTML + plain-text email templates.

Each builder returns ``(subject, html, text)``. Styling is inlined because email
clients strip <style> blocks; the palette mirrors the app's indigo→cyan system.
"""

from __future__ import annotations

_ACCENT = "#6366f1"
_ACCENT_2 = "#22d3ee"
_BG = "#0b0d13"
_SURFACE = "#151824"
_TEXT = "#e6e8ef"
_MUTED = "#9aa2b5"


def _button(label: str, url: str) -> str:
    return (
        f'<a href="{url}" '
        f'style="display:inline-block;padding:12px 22px;border-radius:10px;'
        f"background:linear-gradient(135deg,{_ACCENT},{_ACCENT_2});color:#0b0d13;"
        f'font-weight:700;text-decoration:none;font-size:15px">{label}</a>'
    )


def _wrap(title: str, body_html: str) -> str:
    """Wrap inner body HTML in the branded shell."""
    return f"""\
<!doctype html>
<html>
  <body style="margin:0;padding:0;background:{_BG};font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{_BG};padding:32px 16px">
      <tr><td align="center">
        <table role="presentation" width="480" cellpadding="0" cellspacing="0"
               style="max-width:480px;background:{_SURFACE};border-radius:16px;overflow:hidden;border:1px solid rgba(255,255,255,0.06)">
          <tr><td style="padding:28px 32px 8px 32px">
            <div style="font-size:18px;font-weight:800;color:{_TEXT};letter-spacing:-0.3px">
              <span style="color:{_ACCENT}">Dev</span><span style="color:{_ACCENT_2}">Memory</span>
            </div>
          </td></tr>
          <tr><td style="padding:8px 32px 8px 32px">
            <h1 style="margin:12px 0 4px 0;font-size:20px;color:{_TEXT};font-weight:700">{title}</h1>
          </td></tr>
          <tr><td style="padding:4px 32px 28px 32px;color:{_MUTED};font-size:15px;line-height:1.6">
            {body_html}
          </td></tr>
        </table>
        <div style="color:{_MUTED};font-size:12px;margin-top:18px">
          DevMemory — persistent memory for every AI coding tool
        </div>
      </td></tr>
    </table>
  </body>
</html>"""


# ── Verification (signup) ──────────────────────────────────────


def verification_email(display_name: str, link: str) -> tuple[str, str, str]:
    subject = "Verify your DevMemory email"
    body = (
        f"<p>Hi {display_name},</p>"
        "<p>Welcome to DevMemory. Confirm this email address to activate your "
        "account and start syncing context across your AI coding tools.</p>"
        f'<p style="margin:22px 0">{_button("Verify email", link)}</p>'
        "<p style=\"font-size:13px\">Or paste this link into your browser:<br>"
        f'<a href="{link}" style="color:{_ACCENT_2};word-break:break-all">{link}</a></p>'
        "<p style=\"font-size:13px\">This link expires in 24 hours. If you didn't "
        "create an account, you can ignore this email.</p>"
    )
    text = (
        f"Hi {display_name},\n\n"
        "Welcome to DevMemory. Verify your email to activate your account:\n"
        f"{link}\n\n"
        "This link expires in 24 hours. If you didn't create an account, ignore this email."
    )
    return subject, _wrap("Verify your email", body), text


# ── Welcome (after verification) ───────────────────────────────


def welcome_email(display_name: str, app_url: str) -> tuple[str, str, str]:
    subject = "Welcome to DevMemory"
    body = (
        f"<p>Hi {display_name},</p>"
        "<p>Your email is verified and your account is ready. Connect an AI coding "
        "tool and your context will follow you everywhere.</p>"
        f'<p style="margin:22px 0">{_button("Open dashboard", app_url)}</p>'
    )
    text = (
        f"Hi {display_name},\n\n"
        f"Your DevMemory account is ready. Open your dashboard:\n{app_url}"
    )
    return subject, _wrap("Welcome aboard", body), text


# ── Password reset ─────────────────────────────────────────────


def password_reset_email(display_name: str, link: str, minutes: int) -> tuple[str, str, str]:
    subject = "Reset your DevMemory password"
    body = (
        f"<p>Hi {display_name},</p>"
        "<p>We received a request to reset your password. Choose a new one using "
        "the button below.</p>"
        f'<p style="margin:22px 0">{_button("Reset password", link)}</p>'
        "<p style=\"font-size:13px\">Or paste this link into your browser:<br>"
        f'<a href="{link}" style="color:{_ACCENT_2};word-break:break-all">{link}</a></p>'
        f'<p style="font-size:13px">This link expires in {minutes} minutes. If you '
        "didn't request a reset, ignore this email — your password won't change.</p>"
    )
    text = (
        f"Hi {display_name},\n\n"
        f"Reset your DevMemory password:\n{link}\n\n"
        f"This link expires in {minutes} minutes. If you didn't request it, ignore this email."
    )
    return subject, _wrap("Reset your password", body), text


# ── Security alerts (always transactional, or gated per caller) ─


def password_changed_email(display_name: str) -> tuple[str, str, str]:
    subject = "Your DevMemory password was changed"
    body = (
        f"<p>Hi {display_name},</p>"
        "<p>Your account password was just changed. If this was you, no action is "
        "needed.</p>"
        "<p style=\"font-size:13px\">If you did <strong>not</strong> change your "
        "password, reset it immediately and contact support.</p>"
    )
    text = (
        f"Hi {display_name},\n\n"
        "Your DevMemory password was just changed. If this wasn't you, reset it "
        "immediately and contact support."
    )
    return subject, _wrap("Password changed", body), text


def new_login_email(display_name: str, when: str) -> tuple[str, str, str]:
    subject = "New sign-in to your DevMemory account"
    body = (
        f"<p>Hi {display_name},</p>"
        f"<p>Your DevMemory account was signed in to on <strong style=\"color:{_TEXT}\">"
        f"{when}</strong>.</p>"
        "<p style=\"font-size:13px\">If this was you, no action is needed. Otherwise, "
        "reset your password right away.</p>"
    )
    text = (
        f"Hi {display_name},\n\n"
        f"Your DevMemory account was signed in to on {when}. "
        "If this wasn't you, reset your password right away."
    )
    return subject, _wrap("New sign-in", body), text
