"""Business rules around record locking after payment processed."""

from app.core.exceptions import RecordLockedError
from app.models.enums import UserRole


def assert_record_not_locked(is_locked: bool, role: UserRole) -> None:
    """
    Raise RecordLockedError if record is locked and the user is not Super Admin.
    Super Admin is the only role that can modify a locked record.
    """
    if is_locked and role != UserRole.SUPER_ADMIN:
        raise RecordLockedError(
            "This record has been locked after payment processing. "
            "Contact a Super Admin to override the lock."
        )
