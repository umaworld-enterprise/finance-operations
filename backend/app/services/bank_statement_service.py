"""Bank statement extraction (Banking module, Aug 2026).

Citi's statement PDFs embed fonts WITHOUT unicode maps — the text layer is
gibberish, so extraction goes through vision: each page is rendered to a PNG
(PyMuPDF) and the configured AI provider (OpenAI/Claude — client decision
11 Aug 2026) reads it into strict JSON. An integrity check compares
beginning − debits + credits against the statement's own ending balance and
the result is stored on the statement, so a bad extraction is visible, not
silent.

Runs as a BackgroundTask with its own session (same contract as the
notification jobs): the upload endpoint answers immediately with the
statement row in `processing`, and the row flips to `extracted`/`failed`
when the job finishes.
"""

import json
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID

import structlog

logger = structlog.get_logger()

MAX_PAGES = 80
RENDER_DPI = 150

_SYSTEM_PROMPT = (
    "You are a precise bank-statement data extractor. You read scanned pages "
    "of an account statement and return STRICT JSON only — no markdown, no "
    "code fences, no commentary. Numbers must be plain decimals without "
    "thousands separators. Dates must be ISO format YYYY-MM-DD. If a value "
    "is absent use null. Never invent rows."
)

_PAGE_PROMPT = """Extract this bank statement page into JSON with this exact shape:
{{
  "header": {{
    "bank_name": string|null,        // e.g. "CITI" — only if visible on this page
    "account_number": string|null,
    "account_title": string|null,
    "currency": string|null,         // e.g. "HKD"
    "period_start": "YYYY-MM-DD"|null,
    "period_end": "YYYY-MM-DD"|null,
    "beginning_balance": number|null,
    "ending_balance": number|null
  }},
  "transactions": [
    {{
      "date": "YYYY-MM-DD"|null,
      "category": string,            // the transaction type line, e.g. "IMPORT AND EXPORT BILLS - DEBIT"
      "reference": string|null,      // the "Ref:" value
      "detail": string|null,         // remaining description lines joined with " | " (counterparty, bills reference, value date...)
      "debit": number|null,
      "credit": number|null
    }}
  ],
  "closing_balances": [
    {{ "date": "YYYY-MM-DD", "balance": number }}   // one per "CLOSING BALANCE" row on this page
  ]
}}
Rules:
- "BALANCE CARRIED FORWARD" and "CLOSING BALANCE" rows are NOT transactions — closing balances go in closing_balances only.
- Dates printed as MM/DD/YYYY must be converted to YYYY-MM-DD.
- Every real transaction row has a debit OR a credit amount — copy it exactly.
- This is page {page_no} of {page_count}."""


# ── Pure helpers (unit-tested) ────────────────────────────────────────────────


def parse_page_json(raw: str) -> dict:
    """Model output → dict. Tolerates accidental code fences."""
    cleaned = raw.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    data = json.loads(cleaned)
    if not isinstance(data, dict):
        raise ValueError("Extraction did not return a JSON object.")
    data.setdefault("header", {})
    data.setdefault("transactions", [])
    data.setdefault("closing_balances", [])
    return data


def safe_decimal(value) -> Decimal | None:  # type: ignore[no-untyped-def]
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value).replace(",", "")).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def safe_date(value) -> date | None:  # type: ignore[no-untyped-def]
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def integrity_note(
    beginning: Decimal | None,
    ending: Decimal | None,
    total_debits: Decimal,
    total_credits: Decimal,
) -> tuple[bool, str]:
    """beginning − debits + credits should equal the statement's own ending
    balance. Returns (ok, human-readable note)."""
    if beginning is None or ending is None:
        return False, (
            "Integrity check skipped — the statement's beginning/ending "
            "balances were not extracted."
        )
    computed = beginning - total_debits + total_credits
    delta = computed - ending
    if abs(delta) <= Decimal("0.01"):
        return True, (
            f"Integrity check passed: beginning {beginning} − debits "
            f"{total_debits} + credits {total_credits} = ending {ending}."
        )
    return False, (
        f"Integrity check MISMATCH: beginning {beginning} − debits "
        f"{total_debits} + credits {total_credits} = {computed}, but the "
        f"statement says ending {ending} (difference {delta}). Review the "
        "extracted rows before relying on this statement."
    )


def render_pdf_pages(pdf_bytes: bytes, dpi: int = RENDER_DPI) -> list[bytes]:
    """PDF → one PNG per page. Raises ValueError on unreadable/oversized PDFs."""
    try:
        import pymupdf  # type: ignore[import]
    except ImportError:  # pragma: no cover - environment guard
        import fitz as pymupdf  # type: ignore[import, no-redef]

    try:
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        raise ValueError(f"Could not open the PDF: {exc}") from exc
    if len(doc) == 0:
        raise ValueError("The PDF has no pages.")
    if len(doc) > MAX_PAGES:
        raise ValueError(
            f"The PDF has {len(doc)} pages — the maximum supported is {MAX_PAGES}."
        )
    images: list[bytes] = []
    for page in doc:
        pix = page.get_pixmap(dpi=dpi)
        images.append(pix.tobytes("png"))
    return images


# ── Background extraction job (own session) ───────────────────────────────────


async def extract_statement(statement_id: UUID, pdf_bytes: bytes) -> None:
    """Render → per-page vision extraction → aggregate → integrity check →
    persist. Failures flip the statement to `failed` with the error in
    extraction_note; they never raise (BackgroundTasks contract)."""
    from sqlalchemy import select

    from app.core.database import AsyncSessionFactory
    from app.models.bank_statement import (
        BankDailyBalance,
        BankStatement,
        BankStatementStatus,
        BankTransaction,
    )
    from app.services.ai_service import get_client
    from app.services.bi_service import _load_ai_config

    try:
        async with AsyncSessionFactory() as session:
            statement = await session.get(BankStatement, statement_id)
            if statement is None:
                return
            try:
                provider, api_key, model = await _load_ai_config(session)
                if not api_key:
                    raise RuntimeError(
                        "No AI API key configured — set one in AI Settings first."
                    )
                client = get_client(provider, api_key, model)

                pages = render_pdf_pages(pdf_bytes)
                statement.page_count = len(pages)

                header: dict = {}
                transactions: list[dict] = []
                closing: dict[date, Decimal] = {}
                for page_no, png in enumerate(pages, start=1):
                    raw = await client.chat_vision(
                        _SYSTEM_PROMPT,
                        _PAGE_PROMPT.format(page_no=page_no, page_count=len(pages)),
                        [png],
                    )
                    data = parse_page_json(raw)
                    # First page carrying header values wins; later pages fill gaps.
                    for key, value in (data.get("header") or {}).items():
                        if value not in (None, "") and key not in header:
                            header[key] = value
                    transactions.extend(data.get("transactions") or [])
                    for cb in data.get("closing_balances") or []:
                        d = safe_date(cb.get("date"))
                        b = safe_decimal(cb.get("balance"))
                        if d is not None and b is not None:
                            closing[d] = b

                # Duplicate-period guard (the DB constraint can't fire while
                # the header fields were still NULL at upload time).
                account_number = header.get("account_number")
                period_start = safe_date(header.get("period_start"))
                period_end = safe_date(header.get("period_end"))
                if account_number and period_start and period_end:
                    dupe = (
                        await session.execute(
                            select(BankStatement.id).where(
                                BankStatement.account_number == account_number,
                                BankStatement.period_start == period_start,
                                BankStatement.period_end == period_end,
                                BankStatement.id != statement.id,
                            )
                        )
                    ).scalar_one_or_none()
                    if dupe is not None:
                        raise RuntimeError(
                            f"A statement for account {account_number} covering "
                            f"{period_start} to {period_end} already exists — "
                            "delete it first to re-upload."
                        )

                total_debits = Decimal("0")
                total_credits = Decimal("0")
                for t in transactions:
                    debit = safe_decimal(t.get("debit"))
                    credit = safe_decimal(t.get("credit"))
                    total_debits += debit or Decimal("0")
                    total_credits += credit or Decimal("0")
                    session.add(
                        BankTransaction(
                            statement_id=statement.id,
                            txn_date=safe_date(t.get("date")),
                            category=(t.get("category") or "")[:200] or None,
                            reference=(t.get("reference") or "")[:200] or None,
                            detail=t.get("detail") or None,
                            debit=debit,
                            credit=credit,
                        )
                    )
                for d, b in closing.items():
                    session.add(
                        BankDailyBalance(
                            statement_id=statement.id, balance_date=d, closing_balance=b
                        )
                    )

                beginning = safe_decimal(header.get("beginning_balance"))
                ending = safe_decimal(header.get("ending_balance"))
                _, note = integrity_note(beginning, ending, total_debits, total_credits)

                statement.bank_name = (header.get("bank_name") or statement.bank_name)[:100]
                statement.account_number = account_number
                statement.account_title = header.get("account_title")
                statement.currency = header.get("currency")
                statement.period_start = period_start
                statement.period_end = period_end
                statement.beginning_balance = beginning
                statement.ending_balance = ending
                statement.status = BankStatementStatus.EXTRACTED.value
                statement.extraction_note = f"{len(transactions)} transactions. {note}"
                await session.commit()
            except Exception as exc:
                await session.rollback()
                statement = await session.get(BankStatement, statement_id)
                if statement is not None:
                    statement.status = BankStatementStatus.FAILED.value
                    statement.extraction_note = str(exc)[:2000]
                    await session.commit()
                logger.error(
                    "bank statement extraction failed",
                    statement_id=str(statement_id), error=str(exc),
                )
    except Exception as exc:  # session-level failure — log and swallow
        logger.error(
            "bank statement extraction crashed",
            statement_id=str(statement_id), error=str(exc),
        )
