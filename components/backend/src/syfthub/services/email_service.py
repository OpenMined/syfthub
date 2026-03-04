"""Async email delivery service using aiosmtplib and Jinja2 templates."""

from __future__ import annotations

import asyncio
import logging
from email.message import EmailMessage
from pathlib import Path

import aiosmtplib
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


async def send_otp_email(to_email: str, code: str, purpose: str) -> None:
    """Send an OTP code via email.

    This is designed to be called from FastAPI BackgroundTasks so it
    does not block the API response. Failures are logged but not raised.

    Args:
        to_email: Recipient email address.
        code: The plain-text 6-digit OTP code.
        purpose: "registration" or "password_reset".
    """
    if not settings.smtp_configured:
        logger.warning("SMTP not configured — skipping OTP email to %s", to_email)
        return

    html_body = _otp_template.render(
        code=code,
        purpose=purpose,
        expiry_minutes=settings.otp_expiry_minutes,
    )

    msg = EmailMessage()
    msg["Subject"] = SUBJECTS.get(purpose, "Your SyftHub verification code")
    msg["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
    msg["To"] = to_email
    msg.set_content(
        f"Your SyftHub verification code is: {code}\n"
        f"This code expires in {settings.otp_expiry_minutes} minutes.",
    )
    msg.add_alternative(html_body, subtype="html")

    max_retries = settings.otp_email_max_retries
    base_delay = settings.otp_email_retry_delay_seconds

    for attempt in range(1, max_retries + 1):
        try:
            await aiosmtplib.send(
                msg,
                hostname=settings.smtp_host,
                port=settings.smtp_port,
                username=settings.smtp_username,
                password=settings.smtp_password,
                start_tls=settings.smtp_use_tls,
            )
            logger.info("OTP email sent to %s (purpose=%s)", to_email, purpose)
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
                    "OTP email delivery failed after %d attempts for %s (purpose=%s)",
                    max_retries,
                    to_email,
                    purpose,
                )
