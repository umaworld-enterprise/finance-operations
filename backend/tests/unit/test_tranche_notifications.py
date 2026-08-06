"""Pure tests for tranche notification message builders."""

from uuid import uuid4

from app.services.notification_service import (
    TYPE_TRANCHE_PAID,
    TYPE_TRANCHE_UPDATED,
    build_tranche_notification_message,
)


def test_tranche_paid_message_names_tranche_and_request():
    rid = uuid4()
    msg = build_tranche_notification_message(
        TYPE_TRANCHE_PAID, "Dep-2026-0004", "Tranche II", rid
    )
    assert msg["title"] == "Tranche paid"
    assert "Tranche II" in msg["body"]
    assert "Dep-2026-0004" in msg["body"]
    assert msg["url"] == f"/merchandiser/{rid}"
    assert msg["attachment_url"] is None


def test_tranche_paid_message_mentions_tt_copy_when_present():
    msg = build_tranche_notification_message(
        TYPE_TRANCHE_PAID, "Dep-2026-0004", "Tranche I", uuid4(),
        tt_copy_url="https://drive.test/x",
    )
    assert "TT copy attached" in msg["body"]
    assert msg["attachment_url"] == "https://drive.test/x"


# test_tranche_tt_attached_follow_up was removed 4 Aug 2026 with the
# notification itself — a TT upload alone no longer notifies anyone.


def test_tranche_updated_targets_accounts_view():
    rid = uuid4()
    msg = build_tranche_notification_message(
        TYPE_TRANCHE_UPDATED, "Dep-2026-0010", "Tranche I", rid,
        changes="amount → 500.00",
    )
    assert msg["title"] == "Tranche updated"
    assert "amount → 500.00" in msg["body"]
    assert msg["url"] == f"/accounts/{rid}"
