"""Transactional email via Resend.

Single dependency-light helper used by the password-reset flow. If
RESEND_API_KEY is unset (dev, tests, or before the account is configured),
send_email logs and returns False instead of raising, so callers never break.
"""

import requests

from config import Config

RESEND_ENDPOINT = "https://api.resend.com/emails"


def send_email(to_address, subject, html, text=None):
    """Send one email through Resend. Returns True on a 2xx from Resend,
    False if email isn't configured or the send failed. Never raises."""
    if not Config.RESEND_API_KEY:
        print(f"[email] RESEND_API_KEY unset; skipping send to {to_address}")
        return False

    payload = {
        "from": Config.RESET_FROM_EMAIL,
        "to": [to_address],
        "subject": subject,
        "html": html,
    }
    if text:
        payload["text"] = text

    try:
        resp = requests.post(
            RESEND_ENDPOINT,
            json=payload,
            headers={"Authorization": f"Bearer {Config.RESEND_API_KEY}"},
            timeout=15,
        )
        if 200 <= resp.status_code < 300:
            return True
        print(f"[email] Resend rejected send: {resp.status_code} {resp.text[:300]}")
        return False
    except requests.RequestException as e:
        print(f"[email] Resend request failed: {e}")
        return False


def password_reset_email(reset_url, ttl_minutes):
    """(subject, html, text) for the reset email. Plain on purpose."""
    subject = "Reset your ShelfMates password"
    html = f"""\
<div style="font-family: -apple-system, Helvetica, Arial, sans-serif; max-width: 480px; margin: 0 auto; color: #2D2520;">
  <h2 style="color: #2D5F4F;">Reset your password</h2>
  <p>We got a request to reset the password on your ShelfMates account.</p>
  <p style="margin: 28px 0;">
    <a href="{reset_url}"
       style="background: #2D5F4F; color: #FFFCF7; text-decoration: none; padding: 14px 24px; border-radius: 8px; font-weight: 600;">
      Set a new password
    </a>
  </p>
  <p style="color: #7B5E47; font-size: 14px;">
    This link expires in {ttl_minutes} minutes. If you didn't ask to reset your
    password, you can ignore this email and nothing will change.
  </p>
  <p style="color: #7B5E47; font-size: 13px;">
    If the button doesn't work, paste this into your browser:<br>
    <span style="word-break: break-all;">{reset_url}</span>
  </p>
</div>"""
    text = (
        "Reset your ShelfMates password\n\n"
        "We got a request to reset the password on your ShelfMates account.\n"
        f"Open this link to set a new one (expires in {ttl_minutes} minutes):\n\n"
        f"{reset_url}\n\n"
        "If you didn't ask to reset your password, ignore this email."
    )
    return subject, html, text
