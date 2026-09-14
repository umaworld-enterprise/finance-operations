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


Attachment = tuple[str, str, bytes]  # (filename, mime_type, content)


def _send_sync(
    recipients: list[str],
    subject: str,
    text_body: str,
    html_body: str,
    attachments: list[Attachment] | None = None,
) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from or settings.smtp_user
    msg["To"] = ", ".join(recipients)
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")
    for filename, mime_type, content in attachments or []:
        maintype, _, subtype = (mime_type or "application/octet-stream").partition("/")
        msg.add_attachment(
            content, maintype=maintype, subtype=subtype or "octet-stream", filename=filename
        )

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


async def send_email(
    recipients: list[str],
    subject: str,
    text_body: str,
    html_body: str,
    attachments: list[Attachment] | None = None,
) -> bool:
    """Send an email; returns True if sent. Never raises."""
    if not settings.smtp_host:
        logger.info("SMTP not configured — skipping email", subject=subject)
        return False
    if not recipients:
        return False
    try:
        await asyncio.to_thread(
            _send_sync, recipients, subject, text_body, html_body, attachments
        )
        logger.info("Email sent", subject=subject, recipients=len(recipients))
        return True
    except Exception as exc:
        logger.error("Email send failed", subject=subject, error=str(exc))
        return False


def build_tt_uploaded_email(
    request_number: str, tranche_label: str, tt_copy_url: str | None
) -> tuple[str, str, str]:
    """TT copy uploaded (19 Aug 2026 executive emails). The file itself
    travels as an attachment; the Drive link stays as the online copy."""
    subject = f"TT copy uploaded — {tranche_label} of {request_number}"
    link_text = f"\nView online: {tt_copy_url}\n" if tt_copy_url else ""
    link_html = f'<p><a href="{tt_copy_url}">View the TT copy online</a></p>' if tt_copy_url else ""
    text = (
        f"A TT copy has been uploaded for {tranche_label} of Supplier Advance "
        f"Payment Request {request_number}. The document is attached.\n{link_text}"
    )
    html = (
        f"<p>A TT copy has been uploaded for <strong>{tranche_label}</strong> of "
        f"Supplier Advance Payment Request <strong>{request_number}</strong>. "
        f"The document is attached.</p>{link_html}"
    )
    return subject, text, html


def build_tranche_paid_email(
    request_number: str,
    tranche_label: str,
    amount: str,
    payment_date: str | None,
    bank: str | None,
    tt_copy_url: str | None,
    completed: bool,
) -> tuple[str, str, str]:
    """Tranche marked paid (19 Aug 2026 executive emails). The TT copy
    travels as an attachment; the Drive link stays as the online copy."""
    subject = f"Payment made — {tranche_label} of {request_number}"
    detail_bits = [f"Amount: {amount}"]
    if payment_date:
        detail_bits.append(f"Payment date: {payment_date}")
    if bank:
        detail_bits.append(f"Bank: {bank}")
    details = " · ".join(detail_bits)
    completion = (
        " This was the final tranche — the request is fully paid and the record is locked."
        if completed
        else ""
    )
    link_text = f"\nView online: {tt_copy_url}\n" if tt_copy_url else ""
    link_html = f'<p><a href="{tt_copy_url}">View the TT copy online</a></p>' if tt_copy_url else ""
    text = (
        f"{tranche_label} of Supplier Advance Payment Request {request_number} "
        f"has been marked paid.{completion}\n\n{details}\n"
        f"The TT copy is attached.\n{link_text}"
    )
    html = (
        f"<p><strong>{tranche_label}</strong> of Supplier Advance Payment Request "
        f"<strong>{request_number}</strong> has been marked paid.{completion}</p>"
        f"<p>{details}</p><p>The TT copy is attached.</p>{link_html}"
    )
    return subject, text, html


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
