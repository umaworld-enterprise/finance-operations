"""Executive TT emails (19 Aug 2026): every active user is emailed when a TT
copy is uploaded and when a tranche is marked paid, with the document as a
real attachment (Drive link kept as the online fallback)."""

import pytest

from app.services.email_service import (
    build_tranche_paid_email,
    build_tt_uploaded_email,
)

def test_tt_uploaded_email_wording():
    subject, text, html = build_tt_uploaded_email(
        "Dep-2026-0052", "Deposit - Tranche 2", "https://drive.test/x"
    )
    assert subject == "TT copy uploaded — Deposit - Tranche 2 of Dep-2026-0052"
    assert "attached" in text and "https://drive.test/x" in text
    assert "Dep-2026-0052" in html and "https://drive.test/x" in html


def test_tranche_paid_email_wording_and_completion():
    subject, text, html = build_tranche_paid_email(
        "Dep-2026-0052", "Deposit - Tranche 2",
        amount="500.00 USD", payment_date="21/08/2026", bank="DBS (USD)",
        tt_copy_url="https://drive.test/x", completed=True,
    )
    assert subject == "Payment made — Deposit - Tranche 2 of Dep-2026-0052"
    for fragment in ("500.00 USD", "21/08/2026", "DBS (USD)", "final tranche"):
        assert fragment in text
    assert "fully paid" in html and "https://drive.test/x" in html

    # Partial payment: no completion sentence.
    _, text_partial, _ = build_tranche_paid_email(
        "Dep-2026-0052", "Deposit - Tranche 1",
        amount="200.00 USD", payment_date=None, bank=None,
        tt_copy_url=None, completed=False,
    )
    assert "final tranche" not in text_partial


@pytest.mark.asyncio
async def test_paid_email_goes_to_every_active_user(db_session, engine, monkeypatch):
    """_email_tranche_paid targets ALL active users and carries the TT copy
    downloaded back from Drive as an attachment."""
    from decimal import Decimal

    from app.models.enums import TrancheStatus, UserRole
    from app.services import notification_service as ns
    from tests.factories import (
        make_customer, make_request, make_supplier, make_tranche, make_user,
    )

    merch = await make_user(db_session, UserRole.MERCHANDISER)
    accounts = await make_user(db_session, UserRole.ACCOUNTS_TEAM)
    hom = await make_user(db_session, UserRole.HEAD_OF_MERCHANDISER)
    supplier = await make_supplier(db_session)
    customer = await make_customer(db_session)
    request = await make_request(
        db_session, supplier=supplier, customer=customer, created_by=merch,
    )
    tranche = await make_tranche(
        db_session, request, number=1, amount=Decimal("200.00"),
        status=TrancheStatus.PAID, paid_by=accounts,
    )
    tranche.tt_copy_file_id = "drive-file-1"
    tranche.tt_copy_filename = "TT_Dep_T1.pdf"
    tranche.tt_copy_url = "https://drive.test/x"
    await db_session.flush()

    sent: dict = {}

    async def fake_send_email(recipients, subject, text, html, attachments=None):
        sent.update(
            recipients=recipients, subject=subject, attachments=attachments
        )
        return True

    monkeypatch.setattr("app.services.email_service.send_email", fake_send_email)
    monkeypatch.setattr(
        "app.integrations.google_drive.drive_service.download_tt_copy_from_drive",
        lambda file_id: b"%PDF-fake",
    )

    await ns._email_tranche_paid(db_session, request, tranche)

    assert set(sent["recipients"]) == {merch.email, accounts.email, hom.email}
    assert sent["subject"].startswith("Payment made — Deposit - Tranche 1")
    assert sent["attachments"] == [("TT_Dep_T1.pdf", "application/pdf", b"%PDF-fake")]
