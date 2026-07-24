"""
Google Form webhook handler.

Receives HMAC-signed payloads from Google Apps Script,
deduplicates on google_response_id, transforms payload,
and creates a DepositRequest.
"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import IntegrationError, ValidationError
from app.core.logging import get_logger
from app.integrations.google_form.transformer import extract_raw_fields, to_deposit_request_create
from app.models.enums import SubmissionSource
from app.models.integrations import GoogleFormSubmission
from app.models.masters import Customer, Supplier, Vertical
from app.repositories.user_repo import UserRepository
from app.services.deposit_request_service import DepositRequestService

logger = get_logger(__name__)


async def handle_form_submission(payload: dict, session: AsyncSession) -> str:
    """
    Process a single Google Form webhook payload.
    Returns the deposit_request_id if created, or 'duplicate' if already processed.
    """
    response_id = payload.get("response_id")
    submitted_email = payload.get("respondent_email", "")

    # Deduplication check
    if response_id:
        existing = await session.execute(
            select(GoogleFormSubmission).where(
                GoogleFormSubmission.google_response_id == response_id
            )
        )
        if existing.scalar_one_or_none():
            logger.info("Duplicate Google Form submission ignored", response_id=response_id)
            return "duplicate"

    # Store raw submission immediately (before processing)
    submission = GoogleFormSubmission(
        google_response_id=response_id,
        submitted_by_email=submitted_email,
        submitted_at=datetime.now(timezone.utc),
        raw_payload_json=payload,
        processed=False,
    )
    session.add(submission)
    await session.flush()

    try:
        raw = extract_raw_fields(payload)

        # Resolve names → UUIDs from master data
        supplier = await _resolve_master(session, Supplier, raw.get("_supplier_name", ""), "supplier")
        customer = await _resolve_master(session, Customer, raw.get("_customer_name", ""), "customer")
        vertical = await _resolve_master(session, Vertical, raw.get("_vertical_name", ""), "vertical")

        # Resolve submitter → user
        user_repo = UserRepository(session)
        user = await user_repo.get_by_email(submitted_email)
        if not user:
            raise ValidationError(
                f"Submitter email '{submitted_email}' not registered in the system."
            )

        data = to_deposit_request_create(raw, supplier.id, customer.id, vertical.id)

        service = DepositRequestService(session)
        request = await service.create(data, user.id, source=SubmissionSource.GOOGLE_FORM)

        submission.processed = True
        submission.deposit_request_id = request.id

        logger.info("Google Form submission processed", request_id=str(request.id))
        return str(request.id)

    except Exception as exc:
        submission.error_message = str(exc)
        submission.retry_count += 1
        logger.error("Google Form processing failed", error=str(exc))
        raise IntegrationError(f"Form processing failed: {exc}") from exc


async def _resolve_master(session: AsyncSession, model, name: str, field: str):  # type: ignore[no-untyped-def]
    """Look up a master record by name. Raises ValidationError if not found."""
    result = await session.execute(
        select(model).where(model.name == name.strip(), model.is_active == True)  # noqa: E712
    )
    record = result.scalar_one_or_none()
    if not record:
        raise ValidationError(
            f"'{name}' not found in {field} master. "
            "Ensure the Google Form dropdown values match the application master data."
        )
    return record
