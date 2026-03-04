"""Async email delivery service supporting Resend API and SMTP fallback."""

from __future__ import annotations

import asyncio
import logging
from email.message import EmailMessage
from pathlib import Path

import aiosmtplib
import resend
from jinja2 import Environment, FileSystemLoader

from syfthub.core.config import settings

logger = logging.getLogger(__name__)

# Load templates once at module level
_templates_dir = Path(__file__).resolve().parent.parent / "templates"
_jinja_env = Environment(
    loader=FileSystemLoader(str(_templates_dir)),
    autoescape=True,
)


SUBJECTS = {
    "registration": "Your SyftHub verification code",
    "password_reset": "Your SyftHub password reset code",
}

_otp_template = _jinja_env.get_template("otp_email.html")


async def _send_via_resend(
    to_email: str, subject: str, html_body: str, plain_text: str
) -> None:
    """Send email via Resend HTTP API."""
    resend.api_key = settings.resend_api_key

    params: resend.Emails.SendParams = {
        "from": f"{settings.smtp_from_name} <{settings.smtp_from_email}>",
        "to": [to_email],
        "subject": subject,
        "html": html_body,
        "text": plain_text,
    }

    await asyncio.to_thread(resend.Emails.send, params)


async def _send_via_smtp(
    to_email: str, subject: str, html_body: str, plain_text: str
) -> None:
    """Send email via SMTP/STARTTLS."""
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
    msg["To"] = to_email
    msg.set_content(plain_text)
    msg.add_alternative(html_body, subtype="html")

    await aiosmtplib.send(
        msg,
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_username,
        password=settings.smtp_password,
        start_tls=settings.smtp_use_tls,
    )


async def send_otp_email(to_email: str, code: str, purpose: str) -> None:
    """Send an OTP code via email.

    Uses Resend API when configured, falls back to SMTP.
    Designed to be called from FastAPI BackgroundTasks so it
    does not block the API response. Failures are logged but not raised.

    Args:
        to_email: Recipient email address.
        code: The plain-text 6-digit OTP code.
        purpose: "registration" or "password_reset".
    """
    if not settings.smtp_configured:
        logger.warning("Email not configured — skipping OTP email to %s", to_email)
        return

    html_body = _otp_template.render(
        code=code,
        purpose=purpose,
        expiry_minutes=settings.otp_expiry_minutes,
    )
    subject = SUBJECTS.get(purpose, "Your SyftHub verification code")
    plain_text = (
        f"Your SyftHub verification code is: {code}\n"
        f"This code expires in {settings.otp_expiry_minutes} minutes."
    )

    send_fn = _send_via_resend if settings.resend_configured else _send_via_smtp
    provider = "resend" if settings.resend_configured else "smtp"

    max_retries = settings.otp_email_max_retries
    base_delay = settings.otp_email_retry_delay_seconds

    for attempt in range(1, max_retries + 1):
        try:
            await send_fn(to_email, subject, html_body, plain_text)
            logger.info(
                "OTP email sent to %s (purpose=%s, provider=%s)",
                to_email,
                purpose,
                provider,
            )
            return
        except Exception:
            if attempt < max_retries:
                delay = base_delay * attempt
                logger.warning(
                    "OTP email attempt %d/%d failed for %s, retrying in %.1fs",
                    attempt,
                    max_retries,
                    to_email,
                    delay,
                )
                await asyncio.sleep(delay)
            else:
                logger.error(
                    "OTP email delivery failed after %d attempts for %s "
                    "(purpose=%s, provider=%s)",
                    max_retries,
                    to_email,
                    purpose,
                    provider,
                )
