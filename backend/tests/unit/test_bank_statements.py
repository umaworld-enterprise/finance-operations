"""Banking module (Aug 2026): pure extraction helpers + the background
extraction job run against a fake AI vision client."""

import json
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from app.models.bank_statement import (
    BankDailyBalance,
    BankStatement,
    BankTransaction,
)
from app.models.enums import UserRole
from app.services.bank_statement_service import (
    extract_statement,
    integrity_note,
    parse_page_json,
    safe_date,
    safe_decimal,
)
from tests.factories import make_user

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture(autouse=True)
async def _wipe_committed_rows(db_session):
    yield
    for model in (BankTransaction, BankDailyBalance, BankStatement):
        await db_session.execute(delete(model))
    await db_session.commit()


# ── Pure helpers ──────────────────────────────────────────────────────────────


async def test_parse_page_json_tolerates_fences_and_fills_defaults():
    data = parse_page_json('```json\n{"transactions": [{"debit": 5}]}\n```')
    assert data["transactions"] == [{"debit": 5}]
    assert data["header"] == {}
    assert data["closing_balances"] == []
    with pytest.raises(Exception):
        parse_page_json("not json at all")


async def test_safe_decimal_and_date():
    assert safe_decimal("1,234.5") == Decimal("1234.50")
    assert safe_decimal(None) is None
    assert safe_decimal("n/a") is None
    assert safe_date("2026-06-01") == date(2026, 6, 1)
    assert safe_date("06/01/2026") is None  # non-ISO refused, never guessed
    assert safe_date(None) is None


async def test_integrity_note_outcomes():
    ok, note = integrity_note(Decimal("100"), Decimal("80"), Decimal("30"), Decimal("10"))
    assert ok and "passed" in note
    ok, note = integrity_note(Decimal("100"), Decimal("90"), Decimal("30"), Decimal("10"))
    assert not ok and "MISMATCH" in note
    ok, note = integrity_note(None, Decimal("90"), Decimal("0"), Decimal("0"))
    assert not ok and "skipped" in note


# ── Background extraction with a fake vision client ───────────────────────────


_PAGE1 = {
    "header": {
        "bank_name": "CITI",
        "account_number": "1243838009",
        "account_title": "HKCA",
        "currency": "HKD",
        "period_start": "2026-06-01",
        "period_end": "2026-06-30",
        "beginning_balance": 5000.00,
        "ending_balance": 4400.00,
    },
    "transactions": [
        {"date": "2026-06-01", "category": "INWARD CHECK CLEARING",
         "reference": "0000774210", "detail": "INWARD CLEARING CHECK DEBIT",
         "debit": 700.00, "credit": None},
    ],
    "closing_balances": [{"date": "2026-06-01", "balance": 4300.00}],
}

_PAGE2 = {
    "header": {},
    "transactions": [
        {"date": "2026-06-05", "category": "INWARD REMITTANCE",
         "reference": "QH611", "detail": "CUSTOMER PAYMENT",
         "debit": None, "credit": 100.00},
    ],
    "closing_balances": [{"date": "2026-06-05", "balance": 4400.00}],
}


class _FakeClient:
    def __init__(self, pages):
        self._pages = list(pages)
        self.calls = 0

    async def chat_vision(self, system, user, images_png, max_tokens=4000):
        self.calls += 1
        return json.dumps(self._pages.pop(0))


def _patch(engine, monkeypatch, fake_client, page_images=2):
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr("app.core.database.AsyncSessionFactory", factory)

    async def _fake_config(session):
        return "claude", "test-key", None

    monkeypatch.setattr("app.services.bi_service._load_ai_config", _fake_config)
    monkeypatch.setattr(
        "app.services.ai_service.get_client", lambda *a, **k: fake_client
    )
    monkeypatch.setattr(
        "app.services.bank_statement_service.render_pdf_pages",
        lambda pdf_bytes, dpi=150: [b"png"] * page_images,
    )


async def _seed_statement(db_session):
    """Returns the statement id — captured before commit so the test never
    touches an expired ORM attribute outside the async context."""
    admin = await make_user(db_session, UserRole.SUPER_ADMIN)
    statement = BankStatement(
        bank_name="Bank statement",
        original_filename="sample.pdf",
        uploaded_by=admin.id,
    )
    db_session.add(statement)
    await db_session.flush()
    statement_id = statement.id
    await db_session.commit()
    return statement_id


async def test_extraction_persists_rows_and_passes_integrity(db_session, engine, monkeypatch):
    statement_id = await _seed_statement(db_session)
    fake = _FakeClient([_PAGE1, _PAGE2])
    _patch(engine, monkeypatch, fake)

    await extract_statement(statement_id, b"%PDF-fake")

    db_session.expire_all()
    row = await db_session.get(BankStatement, statement_id)
    assert row.status == "extracted"
    assert fake.calls == 2
    assert row.bank_name == "CITI"
    assert row.account_number == "1243838009"
    assert row.currency == "HKD"
    assert row.period_start == date(2026, 6, 1)
    assert Decimal(str(row.beginning_balance)) == Decimal("5000.00")
    # 5000 − 700 + 100 = 4400 = stated ending → integrity passes.
    assert "passed" in (row.extraction_note or "")

    txns = (
        await db_session.execute(
            select(BankTransaction).where(BankTransaction.statement_id == row.id)
        )
    ).scalars().all()
    assert len(txns) == 2
    assert {t.category for t in txns} == {"INWARD CHECK CLEARING", "INWARD REMITTANCE"}

    balances = (
        await db_session.execute(
            select(BankDailyBalance).where(BankDailyBalance.statement_id == row.id)
        )
    ).scalars().all()
    assert {(b.balance_date, Decimal(str(b.closing_balance))) for b in balances} == {
        (date(2026, 6, 1), Decimal("4300.00")),
        (date(2026, 6, 5), Decimal("4400.00")),
    }


async def test_extraction_flags_integrity_mismatch(db_session, engine, monkeypatch):
    bad_page = json.loads(json.dumps(_PAGE1))
    bad_page["header"]["ending_balance"] = 9999.99  # doesn't reconcile
    statement_id = await _seed_statement(db_session)
    _patch(engine, monkeypatch, _FakeClient([bad_page]), page_images=1)

    await extract_statement(statement_id, b"%PDF-fake")

    db_session.expire_all()
    row = await db_session.get(BankStatement, statement_id)
    assert row.status == "extracted"  # rows kept — but the mismatch is loud
    assert "MISMATCH" in (row.extraction_note or "")


async def test_extraction_failure_marks_statement_failed(db_session, engine, monkeypatch):
    statement_id = await _seed_statement(db_session)

    class _Boom:
        async def chat_vision(self, *a, **k):
            raise RuntimeError("provider exploded")

    _patch(engine, monkeypatch, _Boom(), page_images=1)

    await extract_statement(statement_id, b"%PDF-fake")

    db_session.expire_all()
    row = await db_session.get(BankStatement, statement_id)
    assert row.status == "failed"
    assert "provider exploded" in (row.extraction_note or "")


async def test_duplicate_period_is_refused(db_session, engine, monkeypatch):
    admin = await make_user(db_session, UserRole.SUPER_ADMIN)
    existing = BankStatement(
        bank_name="CITI",
        account_number="1243838009",
        period_start=date(2026, 6, 1),
        period_end=date(2026, 6, 30),
        original_filename="june.pdf",
        uploaded_by=admin.id,
        status="extracted",
    )
    db_session.add(existing)
    await db_session.commit()

    statement_id = await _seed_statement(db_session)
    _patch(engine, monkeypatch, _FakeClient([_PAGE1]), page_images=1)

    await extract_statement(statement_id, b"%PDF-fake")

    db_session.expire_all()
    row = await db_session.get(BankStatement, statement_id)
    assert row.status == "failed"
    assert "already exists" in (row.extraction_note or "")
