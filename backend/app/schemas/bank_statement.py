"""Schemas for the Banking module (Aug 2026)."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from app.schemas.common import OrmBase


class BankTransactionResponse(OrmBase):
    id: UUID
    txn_date: date | None
    category: str | None
    reference: str | None
    detail: str | None
    debit: Decimal | None
    credit: Decimal | None


class BankDailyBalanceResponse(OrmBase):
    balance_date: date
    closing_balance: Decimal


class BankStatementResponse(OrmBase):
    id: UUID
    bank_name: str
    account_number: str | None
    account_title: str | None
    currency: str | None
    period_start: date | None
    period_end: date | None
    beginning_balance: Decimal | None
    ending_balance: Decimal | None
    page_count: int
    original_filename: str
    status: str
    extraction_note: str | None
    created_at: datetime


class BankStatementDetailResponse(BankStatementResponse):
    transactions: list[BankTransactionResponse] = []
    daily_balances: list[BankDailyBalanceResponse] = []
