"""File Remarks — tracked merchandiser → Accounts communication on a file
(CIO batch 2, Aug 2026; migration 0025).

Bypasses the Adjust Invoices module for the time being: invoice-number
changes and invoice splits on already-paid files are raised as structured
remarks with an Open → Resolved lifecycle. Moves no money — Accounts act
manually and resolve with an optional response note.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPrimaryKeyMixin


class FileRemarkCategory(str, enum.Enum):
    INVOICE_SPLIT = "invoice_split"
    INVOICE_AMOUNT_CHANGE = "invoice_amount_change"


class FileRemarkStatus(str, enum.Enum):
    OPEN = "open"
    # UAT change note Aug 2026 (item 14): Accounts decide with Approve or
    # Reject instead of a single Resolve. RESOLVED remains valid for rows
    # decided before the rework (displayed as a legacy "Resolved").
    APPROVED = "approved"
    REJECTED = "rejected"
    RESOLVED = "resolved"


class FileRemark(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "file_remarks"

    deposit_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("deposit_requests.id"), nullable=False
    )
    # Plain varchar + CHECK (not a PG enum) — categories can grow without
    # ALTER TYPE pain.
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    # Invoice amount change: old file + amount → new file + amount.
    old_file_number: Mapped[str | None] = mapped_column(String(200), nullable=True)
    old_amount: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    new_file_number: Mapped[str | None] = mapped_column(String(200), nullable=True)
    new_amount: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    # Split Invoices: dynamic [{"file_number": str, "amount": number}, …].
    split_targets: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Optional (4 Aug rework) — the structured fields carry the instruction.
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=FileRemarkStatus.OPEN.value
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    response_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    deposit_request: Mapped["DepositRequest"] = relationship()
    creator: Mapped["User"] = relationship(foreign_keys=[created_by])
    resolver: Mapped["User | None"] = relationship(foreign_keys=[resolved_by])

    __table_args__ = (
        CheckConstraint(
            "category IN ('invoice_split', 'invoice_amount_change')",
            name="ck_file_remarks_category",
        ),
        CheckConstraint(
            "status IN ('open', 'approved', 'rejected', 'resolved')",
            name="ck_file_remarks_status",
        ),
        Index("idx_file_remarks_status", "status"),
        Index("idx_file_remarks_request", "deposit_request_id"),
        Index("idx_file_remarks_created_by", "created_by"),
    )


from app.models.deposit_request import DepositRequest  # noqa: E402
from app.models.masters import User  # noqa: E402
