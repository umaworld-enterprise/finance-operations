"""
Minimal SMTP email sender — config-gated like the Sheets sync.

SMTP_HOST empty → emails are silently skipped (logged). Sending is
synchronous smtplib — call the async wrappers, which run it in a thread.
"""

import asyncio
import smtplib
from email.message import EmailMessage

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


def _send_sync(recipients: list[str], subject: str, text_body: str, html_body: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from or settings.smtp_user
    msg["To"] = ", ".join(recipients)
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")

    if settings.smtp_port == 465:
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=30) as server:
            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)
    else:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as server:
            server.starttls()
            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)


async def send_email(recipients: list[str], subject: str, text_body: str, html_body: str) -> bool:
    """Send an email; returns True if sent. Never raises."""
    if not settings.smtp_host:
        logger.info("SMTP not configured — skipping email", subject=subject)
        return False
    if not recipients:
        return False
    try:
        await asyncio.to_thread(_send_sync, recipients, subject, text_body, html_body)
        logger.info("Email sent", subject=subject, recipients=len(recipients))
        return True
    except Exception as exc:
        logger.error("Email send failed", subject=subject, error=str(exc))
        return False


def build_payment_processed_email(
    request_number: str, tt_copy_url: str | None
) -> tuple[str, str, str]:
    """Returns (subject, text_body, html_body)."""
    subject = f"Payment processed — {request_number}"
    if tt_copy_url:
        text = (
            f"The payment for Supplier Advance Payment Request {request_number} has been processed.\n\n"
            f"TT copy: {tt_copy_url}\n"
        )
        html = (
            f"<p>The payment for Supplier Advance Payment Request <strong>{request_number}</strong> "
            f"has been processed.</p>"
            f'<p><a href="{tt_copy_url}">View the TT copy</a></p>'
        )
    else:
        text = f"The payment for Supplier Advance Payment Request {request_number} has been processed.\n"
        html = (
            f"<p>The payment for Supplier Advance Payment Request <strong>{request_number}</strong> "
            f"has been processed.</p>"
        )
    return subject, text, html
