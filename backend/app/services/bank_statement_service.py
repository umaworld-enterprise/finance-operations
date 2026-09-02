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
# 200 dpi (was 150, 19 Aug 2026): bilingual (Chinese/English) statements such
# as DBS HK carry dense CJK text and long digit runs — the higher resolution
# measurably reduces misread digits.
RENDER_DPI = 200

_SYSTEM_PROMPT = (
    "You are a precise bank-statement data extractor. You read scanned pages "
    "of an account statement — which may be bilingual (English and Chinese) — "
    "and return STRICT JSON only — no markdown, no code fences, no "
    "commentary. Numbers must be plain decimals without thousands "
    "separators. Dates must be ISO format YYYY-MM-DD. If a value is absent "
    "use null. Never invent rows. Copy every amount digit-for-digit from the "
    "page."
)

_PAGE_PROMPT = """Extract this bank statement page into JSON with this exact shape:
{{
  "header": {{
    "bank_name": string|null,        // e.g. "CITI", "DBS" — only if visible on this page
    "account_number": string|null,   // 戶口號碼 / Account No
    "account_title": string|null,    // the account holder name
    "currency": string|null,         // e.g. "HKD" (貨幣 Currency)
    "period_start": "YYYY-MM-DD"|null,
    "period_end": "YYYY-MM-DD"|null,
    "beginning_balance": number|null, // opening / BALANCE BROUGHT FORWARD / 承上結餘
    "ending_balance": number|null,    // closing / CLOSING BALANCE / 戶口結餘
    "total_debits": number|null,      // printed totals row (Grand Total / 總額) — debit/withdrawal side
    "total_credits": number|null      // printed totals row (Grand Total / 總額) — credit/deposit side
  }},
  "transactions": [
    {{
      "date": "YYYY-MM-DD"|null,
      "category": string,            // the transaction type line, e.g. "TRADE SERVICES", "CASH PAYMENT"
      "reference": string|null,      // the reference / cheque number if shown
      "detail": string|null,         // remaining description lines joined with " | "
      "debit": number|null,          // money OUT of the account
      "credit": number|null,         // money INTO the account
      "balance": number|null         // the running balance printed on THIS row (結餘 / Balance column), if any
    }}
  ],
  "closing_balances": [
    {{ "date": "YYYY-MM-DD", "balance": number }}   // one per per-day "CLOSING BALANCE" row (Citi style); empty if the statement has none
  ]
}}
Column mapping — get the direction RIGHT:
- 支出 / Withdrawal / Debit / 借方 → "debit" (money out).
- 存入 / Deposit / Credit / 貸方 → "credit" (money in).
- 結餘 / Balance → "balance" (the running balance AFTER the row). NEVER put a running balance into debit or credit.
- A transaction row has exactly ONE of debit or credit — decide by which COLUMN the amount is printed in, and sanity-check against the balance column: the balance DECREASES after a debit and INCREASES after a credit.
Rows that are NOT transactions (do not list them under "transactions"):
- "BALANCE BROUGHT FORWARD" / 承上結餘 → its amount is header.beginning_balance (first page of the table only).
- "BALANCE CARRIED FORWARD" / 結轉下頁 → ignore (page-break artifact).
- "CLOSING BALANCE" / 戶口結餘 → header.ending_balance (or closing_balances for per-day Citi rows).
- "Grand Total" / 總額 → header.total_debits and header.total_credits.
Other rules:
- Dates printed as MM/DD/YYYY or DD-Mon-YY (e.g. 31-May-26) must be converted to YYYY-MM-DD.
- Amounts printed with commas (1,563,722.30) → plain 1563722.30.
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
    text = str(value).strip()
    # ISO first (truncated: tolerates a trailing time part); then the
    # DD-Mon-YYYY / DD-Mon-YY styles DBS prints (31-May-26) as belt-and-braces
    # fallbacks when the model copies instead of converting. Four-digit year
    # BEFORE two-digit: "01-Jun-2026"[:9] would otherwise parse as 2020.
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        pass
    for fmt in ("%d-%b-%Y", "%d-%b-%y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


# Rows the model must NOT return as transactions — filtered again here as a
# safety net (19 Aug 2026, DBS fix): a brought-forward / closing-balance /
# grand-total row slipping into the list wrecks every total downstream.
_NON_TXN_RE = re.compile(
    r"balance\s+brought\s+forward|balance\s+carried\s+forward|closing\s+balance"
    r"|grand\s+total|承上結餘|結轉|戶口結餘|總額",
    re.IGNORECASE,
)


def is_non_transaction(txn: dict) -> bool:
    text = f"{txn.get('category') or ''} {txn.get('detail') or ''}"
    return bool(_NON_TXN_RE.search(text))


def reconcile_directions(
    beginning: Decimal | None, txns: list[dict]
) -> tuple[int, Decimal | None]:
    """Thorough per-row verification (19 Aug 2026, DBS fix): statements like
    DBS print a running balance on every row, which makes each transaction's
    DIRECTION mathematically checkable — the balance drops after a debit and
    rises after a credit. Walks the rows in order and, wherever the printed
    running balance contradicts the recorded side but matches the flipped
    side, flips it. Also fills a missing amount from an unambiguous balance
    delta. Returns (corrections_made, last_running_balance).

    txns rows carry Decimal|None 'debit'/'credit'/'balance' and are mutated
    in place. Rows without a printed balance advance the expected balance by
    their recorded amounts and are left untouched.
    """
    tolerance = Decimal("0.01")
    corrections = 0
    prev: Decimal | None = beginning
    last_balance: Decimal | None = None
    for txn in txns:
        debit: Decimal | None = txn.get("debit")
        credit: Decimal | None = txn.get("credit")
        balance: Decimal | None = txn.get("balance")
        if balance is not None and prev is not None:
            delta = balance - prev
            recorded = (credit or Decimal("0")) - (debit or Decimal("0"))
            if abs(delta - recorded) > tolerance:
                flipped = (debit or Decimal("0")) - (credit or Decimal("0"))
                if abs(delta - flipped) <= tolerance and (debit or credit):
                    txn["debit"], txn["credit"] = credit, debit
                    corrections += 1
                elif debit is None and credit is None:
                    # Amount missing entirely — recover it from the delta.
                    if delta > 0:
                        txn["credit"] = delta
                    else:
                        txn["debit"] = -delta
                    corrections += 1
        if balance is not None:
            prev = balance
            last_balance = balance
        elif prev is not None:
            prev = prev + (txn.get("credit") or Decimal("0")) - (txn.get("debit") or Decimal("0"))
    return corrections, last_balance


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

                # ── Thorough verification pass (19 Aug 2026, DBS fix) ──────
                # 1. Normalise amounts + drop summary rows the model may have
                #    mistaken for transactions (brought-forward / closing /
                #    grand-total — bilingual patterns).
                normalized: list[dict] = []
                dropped_summary = 0
                for t in transactions:
                    if is_non_transaction(t):
                        dropped_summary += 1
                        continue
                    normalized.append(
                        {
                            **t,
                            "debit": safe_decimal(t.get("debit")),
                            "credit": safe_decimal(t.get("credit")),
                            "balance": safe_decimal(t.get("balance")),
                        }
                    )

                beginning = safe_decimal(header.get("beginning_balance"))
                ending = safe_decimal(header.get("ending_balance"))
                # Fallbacks from the running-balance column when the header
                # values weren't printed / extracted.
                if beginning is None and normalized:
                    first = normalized[0]
                    if first["balance"] is not None:
                        beginning = (
                            first["balance"]
                            + (first["debit"] or Decimal("0"))
                            - (first["credit"] or Decimal("0"))
                        )

                # 2. Per-row direction check against the running balance —
                #    flips debit/credit wherever the math proves the side
                #    wrong, and recovers missing amounts from balance deltas.
                corrections, last_balance = reconcile_directions(beginning, normalized)
                if ending is None and last_balance is not None:
                    ending = last_balance

                total_debits = Decimal("0")
                total_credits = Decimal("0")
                for t in normalized:
                    total_debits += t["debit"] or Decimal("0")
                    total_credits += t["credit"] or Decimal("0")
                    session.add(
                        BankTransaction(
                            statement_id=statement.id,
                            txn_date=safe_date(t.get("date")),
                            category=(t.get("category") or "")[:200] or None,
                            reference=(t.get("reference") or "")[:200] or None,
                            detail=t.get("detail") or None,
                            debit=t["debit"],
                            credit=t["credit"],
                        )
                    )
                for d, b in closing.items():
                    session.add(
                        BankDailyBalance(
                            statement_id=statement.id, balance_date=d, closing_balance=b
                        )
                    )

                # 3. Integrity: beginning − debits + credits vs ending, PLUS
                #    the statement's own printed Grand Total when present.
                _, note = integrity_note(beginning, ending, total_debits, total_credits)
                extras: list[str] = []
                if corrections:
                    extras.append(
                        f"{corrections} row(s) auto-corrected against the running balance."
                    )
                if dropped_summary:
                    extras.append(f"{dropped_summary} summary row(s) excluded.")
                printed_debits = safe_decimal(header.get("total_debits"))
                printed_credits = safe_decimal(header.get("total_credits"))
                if printed_debits is not None and printed_credits is not None:
                    if (
                        abs(printed_debits - total_debits) <= Decimal("0.01")
                        and abs(printed_credits - total_credits) <= Decimal("0.01")
                    ):
                        extras.append(
                            "Extracted totals MATCH the statement's printed Grand Total."
                        )
                    else:
                        extras.append(
                            f"Grand Total MISMATCH: statement prints debits "
                            f"{printed_debits} / credits {printed_credits}, extracted "
                            f"{total_debits} / {total_credits} — review the rows."
                        )
                if extras:
                    note = f"{note} {' '.join(extras)}"

                statement.bank_name = (header.get("bank_name") or statement.bank_name)[:100]
                statement.account_number = account_number
                statement.account_title = header.get("account_title")
                statement.currency = header.get("currency")
                statement.period_start = period_start
                statement.period_end = period_end
                statement.beginning_balance = beginning
                statement.ending_balance = ending
                statement.status = BankStatementStatus.EXTRACTED.value
                statement.extraction_note = f"{len(normalized)} transactions. {note}"
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
