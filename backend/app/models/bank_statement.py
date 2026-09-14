"""Banking module (Aug 2026) — uploaded bank statements and their
AI-extracted transactions. Standalone from the Advance Payment module;
super-admin only for now."""

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPrimaryKeyMixin


class BankStatementStatus(str, enum.Enum):
    PROCESSING = "processing"
    EXTRACTED = "extracted"
    FAILED = "failed"


class BankStatement(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "bank_statements"

    bank_name: Mapped[str] = mapped_column(String(100), nullable=False)
    account_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    account_title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    beginning_balance: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    ending_balance: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    original_filename: Mapped[str] = mapped_column(String(300), nullable=False)
    # processing → extracted | failed
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=BankStatementStatus.PROCESSING.value
    )
    # Human-readable extraction outcome: integrity-check result or the error.
    extraction_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    transactions: Mapped[list["BankTransaction"]] = relationship(
        back_populates="statement", cascade="all, delete-orphan",
        order_by="BankTransaction.txn_date",
    )
    daily_balances: Mapped[list["BankDailyBalance"]] = relationship(
        back_populates="statement", cascade="all, delete-orphan",
        order_by="BankDailyBalance.balance_date",
    )

    __table_args__ = (
        # One statement per account + period — re-uploading replaces via
        # delete + upload, never silently duplicates.
        UniqueConstraint(
            "account_number", "period_start", "period_end",
            name="uq_bank_statement_account_period",
        ),
        Index("idx_bank_statements_status", "status"),
    )


class BankTransaction(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "bank_transactions"

    statement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bank_statements.id", ondelete="CASCADE"),
        nullable=False,
    )
    txn_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # The statement's type line, e.g. "IMPORT AND EXPORT BILLS - DEBIT".
    category: Mapped[str | None] = mapped_column(String(200), nullable=True)
    reference: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Remaining detail lines (counterparty, bills reference, value date …).
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    debit: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    credit: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)

    statement: Mapped[BankStatement] = relationship(back_populates="transactions")

    __table_args__ = (
        Index("idx_bank_transactions_statement", "statement_id"),
        Index("idx_bank_transactions_date", "txn_date"),
    )


class BankDailyBalance(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "bank_daily_balances"

    statement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bank_statements.id", ondelete="CASCADE"),
        nullable=False,
    )
    balance_date: Mapped[date] = mapped_column(Date, nullable=False)
    closing_balance: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)

    statement: Mapped[BankStatement] = relationship(back_populates="daily_balances")

    __table_args__ = (
        UniqueConstraint("statement_id", "balance_date", name="uq_bank_daily_balance"),
        Index("idx_bank_daily_balances_statement", "statement_id"),
    )
