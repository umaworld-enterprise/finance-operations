"""
Google Sheets sync service (Option 2 integration).

Reads new rows from the Google Sheet since the last sync checkpoint
and creates DepositRequest records. Used as a fallback when the
Google Form webhook (Option 1) is not available.
"""

import json
from datetime import datetime, timezone

import gspread
from google.oauth2.service_account import Credentials
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.enums import SubmissionSource, SyncStatus
from app.models.integrations import SyncLog

logger = get_logger(__name__)
settings = get_settings()

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

# Column header → internal field name mapping (matches actual sheet headers)
_COL_MAP: dict[str, str] = {
    "Timestamp": "_timestamp",
    "Email Address": "_email",
    "Sunshine Invoice Number": "sunshine_invoice_number",
    "Vertical / Category": "_vertical_name",
    "Customer": "_customer_name",
    "Supplier": "_supplier_name",
    "Supplier Invoice Number": "supplier_invoice_number",
    "Total Supplier Proforma Invoice Amount": "total_supplier_invoice_amount",
    "Deposit Advance Percentage": "deposit_percentage",
    "Currency of Advance Deposit": "currency",
    "Estimated Shipment Date": "estimated_shipment_date",
    "Remarks": "remarks",
}


async def sync_from_sheet(session_factory: async_sessionmaker) -> int:
    """Incremental sync from Google Sheet. Returns number of new records created."""
    if not settings.google_service_account_json or not settings.google_sheet_id:
        logger.warning("Google Sheet integration not configured — skipping sync")
        return 0

    async with session_factory() as session:
        try:
            creds_dict = json.loads(settings.google_service_account_json)
            creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
            gc = gspread.authorize(creds)
            sh = gc.open_by_key(settings.google_sheet_id)
            ws = sh.worksheet(settings.google_sheet_tab_name)

            all_rows = ws.get_all_records()
            last_synced_count = await _get_last_synced_count(session)

            new_rows = all_rows[last_synced_count:]
            if not new_rows:
                logger.info("Google Sheet sync: no new rows")
                return 0

            from app.integrations.google_form.handler import handle_form_submission
            created = 0
            for row in new_rows:
                # Convert sheet row → webhook-like payload
                payload = {
                    "response_id": f"sheet-row-{last_synced_count + created + 1}",
                    "respondent_email": row.get("Email Address", ""),
                    "items": [
                        {"question": k, "answer": str(v)} for k, v in row.items()
                    ],
                }
                try:
                    result = await handle_form_submission(payload, session)
                    if result != "duplicate":
                        created += 1
                except Exception as exc:
                    logger.error("Sheet row processing failed", error=str(exc))

            await _write_sync_log(session, SyncStatus.SUCCESS, created)
            await session.commit()
            return created

        except Exception as exc:
            logger.error("Google Sheet sync failed", error=str(exc))
            async with session_factory() as err_session:
                await _write_sync_log(err_session, SyncStatus.FAILED, 0, str(exc))
                await err_session.commit()
            return 0


async def _get_last_synced_count(session: AsyncSession) -> int:
    from sqlalchemy import select, func
    from app.models.integrations import GoogleFormSubmission
    result = await session.execute(
        select(func.count(GoogleFormSubmission.id)).where(
            GoogleFormSubmission.google_response_id.like("sheet-row-%")
        )
    )
    return result.scalar_one() or 0


async def _write_sync_log(
    session: AsyncSession,
    status: SyncStatus,
    records: int,
    error: str | None = None,
) -> None:
    session.add(
        SyncLog(
            source_type=SubmissionSource.GOOGLE_SHEET_SYNC,
            sync_status=status,
            records_synced=records,
            error_message=error,
        )
    )
