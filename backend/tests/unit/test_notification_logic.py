"""Unit tests for notification trigger logic, message building, and TT copy validation.

Pure functions only — no DB, no network.
"""

from datetime import date
from uuid import UUID

from app.integrations.google_drive.drive_service import (
    MAX_FILE_SIZE_BYTES,
    build_tt_copy_filename,
    validate_tt_copy,
)
from app.services.notification_service import (
    TYPE_PAYMENT_PROCESSED,
    TYPE_TT_COPY_ATTACHED,
    build_notification_message,
    decide_on_process,
    decide_on_tt_upload,
    is_subscription_gone,
    resolve_target,
)

_REQ_ID = UUID("11111111-2222-3333-4444-555555555555")


# ── Message builder ──────────────────────────────────────────────────────────


def test_payment_processed_message_with_tt_copy():
    msg = build_notification_message(
        TYPE_PAYMENT_PROCESSED, "ADT-2026-00021", _REQ_ID, "https://drive.google.com/x"
    )
    assert msg["title"] == "Payment processed"
    assert "ADT-2026-00021" in msg["body"]
    assert "TT copy attached" in msg["body"]
    assert msg["url"] == f"/merchandiser/{_REQ_ID}"
    assert msg["attachment_url"] == "https://drive.google.com/x"


def test_payment_processed_message_without_tt_copy():
    msg = build_notification_message(TYPE_PAYMENT_PROCESSED, "ADT-2026-00021", _REQ_ID, None)
    assert msg["title"] == "Payment processed"
    assert "TT copy" not in msg["body"]
    assert msg["attachment_url"] is None


def test_tt_copy_attached_message():
    msg = build_notification_message(
        TYPE_TT_COPY_ATTACHED, "ADT-2026-00021", _REQ_ID, "https://drive.google.com/x"
    )
    assert msg["title"] == "TT copy attached"
    assert msg["attachment_url"] == "https://drive.google.com/x"


# ── Which-notification decision ──────────────────────────────────────────────


def test_upload_after_process_sends_payment_processed():
    # Normal flow: process first, then upload → one notification with the link
    assert decide_on_tt_upload(request_is_processed=True, already_notified=False) == TYPE_PAYMENT_PROCESSED


def test_upload_after_fallback_sends_tt_copy_attached():
    # Fallback already told the merchandiser → follow-up with the link only
    assert decide_on_tt_upload(request_is_processed=True, already_notified=True) == TYPE_TT_COPY_ATTACHED


def test_upload_before_process_sends_nothing():
    # Uploaded pre-process → the process step will notify
    assert decide_on_tt_upload(request_is_processed=False, already_notified=False) is None


def test_process_with_tt_copy_notifies_immediately():
    assert decide_on_process(has_tt_copy=True, already_notified=False) == TYPE_PAYMENT_PROCESSED


def test_process_without_tt_copy_waits():
    assert decide_on_process(has_tt_copy=False, already_notified=False) is None


def test_process_never_double_notifies():
    assert decide_on_process(has_tt_copy=True, already_notified=True) is None


# ── Target resolution ────────────────────────────────────────────────────────


def test_target_prefers_created_by():
    mode, email = resolve_target(_REQ_ID, "someone@sunshine.com")
    assert mode == "created_by"
    assert email is None


def test_target_falls_back_to_submitter_email_lowercased():
    mode, email = resolve_target(None, "  Someone@Sunshine.COM ")
    assert mode == "email"
    assert email == "someone@sunshine.com"


def test_target_none_when_no_creator_or_email():
    assert resolve_target(None, None) == ("none", None)
    assert resolve_target(None, "") == ("none", None)


# ── Gone-subscription classification ─────────────────────────────────────────


def test_404_and_410_mean_gone():
    assert is_subscription_gone(404) is True
    assert is_subscription_gone(410) is True


def test_other_statuses_are_not_gone():
    assert is_subscription_gone(400) is False
    assert is_subscription_gone(429) is False
    assert is_subscription_gone(500) is False
    assert is_subscription_gone(None) is False


# ── TT copy validation and filename ──────────────────────────────────────────


def test_valid_pdf_accepted():
    assert validate_tt_copy("application/pdf", 1024) is None


def test_valid_images_accepted():
    assert validate_tt_copy("image/jpeg", 1024) is None
    assert validate_tt_copy("image/png", 1024) is None


def test_wrong_mime_rejected():
    assert validate_tt_copy("application/zip", 1024) is not None
    assert validate_tt_copy(None, 1024) is not None


def test_oversize_rejected():
    assert validate_tt_copy("application/pdf", MAX_FILE_SIZE_BYTES + 1) is not None
    assert validate_tt_copy("application/pdf", MAX_FILE_SIZE_BYTES) is None


def test_empty_file_rejected():
    assert validate_tt_copy("application/pdf", 0) is not None


def test_filename_format():
    name = build_tt_copy_filename("ADT-2026-00021", "application/pdf", today=date(2026, 7, 9))
    assert name == "TT_ADT-2026-00021_20260709.pdf"
    name = build_tt_copy_filename("ADT-2026-00021", "image/jpeg", today=date(2026, 7, 9))
    assert name.endswith(".jpg")
