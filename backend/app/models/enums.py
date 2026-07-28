"""Python enums that mirror PostgreSQL enum types."""

import enum
from typing import Type, TypeVar

from sqlalchemy import Enum as SAEnum

_E = TypeVar("_E", bound=enum.Enum)


def pg_enum(enum_cls: Type[_E], pg_name: str) -> SAEnum:
    """SQLAlchemy Enum type that maps Python enum values (not names) to PostgreSQL."""
    return SAEnum(
        enum_cls,
        name=pg_name,
        create_type=False,
        values_callable=lambda obj: [e.value for e in obj],
    )


class UserRole(str, enum.Enum):
    SUPER_ADMIN = "super_admin"
    FINANCE_ADMIN = "finance_admin"
    ACCOUNTS_TEAM = "accounts_team"
    MERCHANDISER = "merchandiser"
    HEAD_OF_MERCHANDISER = "head_of_merchandiser"


class RequestStatus(str, enum.Enum):
    PENDING_PAYMENT = "pending_payment"
    HOLD_BY_MERCHANDISER = "hold_by_merchandiser"
    HOLD_BY_ACCOUNTS = "hold_by_accounts"
    PAYMENT_PROCESSED = "payment_processed"
    CANCELLED_BY_MERCHANDISER = "cancelled_by_merchandiser"
    CANCELLED_BY_ACCOUNTS = "cancelled_by_accounts"
    REOPENED = "reopened"
    PENDING_HOM_APPROVAL = "pending_hom_approval"
    REJECTED_BY_HOM = "rejected_by_hom"


class CurrencyCode(str, enum.Enum):
    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"
    AED = "AED"
    INR = "INR"
    CNY = "CNY"
    JPY = "JPY"
    SGD = "SGD"
    OTHER = "OTHER"


class SubmissionSource(str, enum.Enum):
    GOOGLE_FORM = "google_form"
    GOOGLE_SHEET_SYNC = "google_sheet_sync"
    IN_APP = "in_app"
    PUBLIC_FORM = "public_form"


class SyncStatus(str, enum.Enum):
    SUCCESS = "success"
    FAILED = "failed"
    PENDING = "pending"
    RETRYING = "retrying"


class MerchandiserActionType(str, enum.Enum):
    HOLD = "hold"
    CANCEL = "cancel"
    RESUME = "resume"


class AccountsActionType(str, enum.Enum):
    HOLD = "hold"
    CANCEL = "cancel"
    REOPEN = "reopen"


class PaymentStatus(str, enum.Enum):
    PROCESSED = "processed"
    REJECTED = "rejected"
    HOLD = "hold"


class TrancheStatus(str, enum.Enum):
    UNPAID = "unpaid"
    PAID = "paid"


class AdjustmentStatus(str, enum.Enum):
    """Invoice adjustment lifecycle.

    Approval requirements for invoice adjustments are still an open business
    decision — adjustments are created directly as COMPLETED today, but the
    enum carries the approval states so a review workflow can be added
    without a schema change.
    """

    COMPLETED = "completed"
    PENDING_APPROVAL = "pending_approval"
    REJECTED = "rejected"


class AuditAction(str, enum.Enum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    STATUS_CHANGE = "STATUS_CHANGE"
    LOGIN = "LOGIN"
    AI_QUERY = "AI_QUERY"
