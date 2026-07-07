"""Async email delivery service using Resend API."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING

import resend
from jinja2 import Environment, FileSystemLoader

from syfthub.core.config import settings

if TYPE_CHECKING:
    from syfthub.schemas.collective import InvitationEmailContext

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
_invitation_template = _jinja_env.get_template("collective_invitation_email.html")


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


async def send_otp_email(to_email: str, code: str, purpose: str) -> None:
    """Send an OTP code via Resend API.

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

    max_retries = settings.otp_email_max_retries
    base_delay = settings.otp_email_retry_delay_seconds

    for attempt in range(1, max_retries + 1):
        try:
            await _send_via_resend(to_email, subject, html_body, plain_text)
            logger.info(
                "OTP email sent to %s (purpose=%s)",
                to_email,
                purpose,
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
                    "OTP email delivery failed after %d attempts for %s (purpose=%s)",
                    max_retries,
                    to_email,
                    purpose,
                )


async def _send_with_retries(
    to_email: str, subject: str, html_body: str, plain_text: str, context: str
) -> None:
    """Send an email via Resend with bounded retries.

    Failures are logged, not raised — callers run this from BackgroundTasks.
    """
    max_retries = settings.otp_email_max_retries
    base_delay = settings.otp_email_retry_delay_seconds

    for attempt in range(1, max_retries + 1):
        try:
            await _send_via_resend(to_email, subject, html_body, plain_text)
            logger.info("Email sent to %s (%s)", to_email, context)
            return
        except Exception:
            if attempt < max_retries:
                delay = base_delay * attempt
                logger.warning(
                    "Email attempt %d/%d failed for %s (%s), retrying in %.1fs",
                    attempt,
                    max_retries,
                    to_email,
                    context,
                    delay,
                )
                await asyncio.sleep(delay)
            else:
                logger.error(
                    "Email delivery failed after %d attempts for %s (%s)",
                    max_retries,
                    to_email,
                    context,
                )


async def send_collective_invitation_email(ctx: InvitationEmailContext) -> None:
    """Notify an endpoint owner that their endpoint was invited to a collective.

    Designed to be called from FastAPI BackgroundTasks so it does not block the
    API response. Failures are logged but not raised.

    Args:
        ctx: Rendering context (recipient, inviter, collective and endpoint).
    """
    if not settings.smtp_configured:
        logger.warning(
            "Email not configured — skipping collective invitation email to %s",
            ctx.to_email,
        )
        return

    invite_url = (
        f"{settings.frontend_url.rstrip('/')}"
        f"/collectives/{ctx.collective_slug}/invitations/{ctx.endpoint_id}"
    )
    html_body = _invitation_template.render(
        recipient_name=ctx.recipient_name,
        inviter_name=ctx.inviter_name,
        collective_name=ctx.collective_name,
        endpoint_name=ctx.endpoint_name,
        invite_url=invite_url,
    )
    subject = (
        f"{ctx.inviter_name} invited your endpoint to the "
        f"{ctx.collective_name} collective"
    )
    plain_text = (
        f"Hi {ctx.recipient_name},\n\n"
        f"{ctx.inviter_name} invited your endpoint '{ctx.endpoint_name}' to join "
        f"the '{ctx.collective_name}' collective on SyftHub.\n\n"
        f"Accept or decline this invitation here:\n{invite_url}\n\n"
        f"If you didn't expect this invitation, you can safely ignore this email."
    )
    await _send_with_retries(
        ctx.to_email,
        subject,
        html_body,
        plain_text,
        context="collective_invitation",
    )
