"""
Google Drive upload for TT copy documents.

Uploads via the same service account used for the Sheets sync, into the
Shared Drive folder configured in GOOGLE_DRIVE_FOLDER_ID (must be a Shared
Drive — new service accounts have zero My Drive storage quota). Files get
an anyone-with-link reader permission so the link can be shared in
notifications.

All functions are synchronous — call via asyncio.to_thread from async code.
"""

import io
import json
from datetime import date

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

from app.core.config import get_settings
from app.core.exceptions import IntegrationError
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

SCOPES = ["https://www.googleapis.com/auth/drive"]

ALLOWED_MIME_TYPES = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
}
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB


def build_tt_copy_filename(
    request_number: str,
    mime_type: str,
    today: date | None = None,
    tranche_number: int | None = None,
) -> str:
    """TT_{request_number}[_T{n}]_{YYYYMMDD}{ext} — extension derived from
    mime type; the T{n} segment identifies the tranche the copy belongs to."""
    ext = ALLOWED_MIME_TYPES[mime_type]
    stamp = (today or date.today()).strftime("%Y%m%d")
    tranche_part = f"_T{tranche_number}" if tranche_number is not None else ""
    return f"TT_{request_number}{tranche_part}_{stamp}{ext}"


def validate_tt_copy(mime_type: str | None, size_bytes: int) -> str | None:
    """Returns an error message, or None if the file is acceptable."""
    if mime_type not in ALLOWED_MIME_TYPES:
        return "Only PDF, JPEG, or PNG files are accepted for the TT copy."
    if size_bytes > MAX_FILE_SIZE_BYTES:
        return "TT copy file must be 10 MB or smaller."
    if size_bytes == 0:
        return "The uploaded file is empty."
    return None


def upload_tt_copy_to_drive(content: bytes, filename: str, mime_type: str) -> tuple[str, str]:
    """Upload the TT copy and return (file_id, webViewLink).

    Synchronous (blocking network I/O) — run in a thread from async code.
    """
    if not settings.google_service_account_json or not settings.google_drive_folder_id:
        raise IntegrationError(
            "Google Drive is not configured. Set GOOGLE_SERVICE_ACCOUNT_JSON "
            "and GOOGLE_DRIVE_FOLDER_ID."
        )

    creds_dict = json.loads(settings.google_service_account_json)
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    drive = build("drive", "v3", credentials=creds)

    media = MediaIoBaseUpload(io.BytesIO(content), mimetype=mime_type, resumable=False)
    created = (
        drive.files()
        .create(
            body={"name": filename, "parents": [settings.google_drive_folder_id]},
            media_body=media,
            fields="id, webViewLink",
            supportsAllDrives=True,
        )
        .execute()
    )
    file_id = created["id"]

    # Anyone-with-link reader — the link travels in notifications/emails to
    # people who may not be members of the Shared Drive.
    drive.permissions().create(
        fileId=file_id,
        body={"role": "reader", "type": "anyone"},
        supportsAllDrives=True,
    ).execute()

    link = created.get("webViewLink") or f"https://drive.google.com/file/d/{file_id}/view"
    logger.info("TT copy uploaded to Drive", file_id=file_id, filename=filename)
    return file_id, link
