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


class RequestStatus(str, enum.Enum):
    PENDING_PAYMENT = "pending_payment"
    HOLD_BY_MERCHANDISER = "hold_by_merchandiser"
    HOLD_BY_ACCOUNTS = "hold_by_accounts"
    PAYMENT_PROCESSED = "payment_processed"
    CANCELLED_BY_MERCHANDISER = "cancelled_by_merchandiser"
    CANCELLED_BY_ACCOUNTS = "cancelled_by_accounts"
    REOPENED = "reopened"


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


class AuditAction(str, enum.Enum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    STATUS_CHANGE = "STATUS_CHANGE"
