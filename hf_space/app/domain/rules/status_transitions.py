"""
Valid status transition graph for deposit requests.

Each key is the CURRENT status; the value is the set of statuses it may
transition TO, keyed by which role is allowed to perform that transition.
"""

from app.core.exceptions import InvalidStatusTransitionError
from app.models.enums import RequestStatus, UserRole

# (current_status, new_status) -> frozenset of roles that may make this move
_ALLOWED_TRANSITIONS: dict[tuple[RequestStatus, RequestStatus], frozenset[UserRole]] = {
    # Merchandiser places own request on hold
    (RequestStatus.PENDING_PAYMENT, RequestStatus.HOLD_BY_MERCHANDISER): frozenset({
        UserRole.MERCHANDISER, UserRole.SUPER_ADMIN,
    }),
    # Merchandiser cancels own request before payment
    (RequestStatus.PENDING_PAYMENT, RequestStatus.CANCELLED_BY_MERCHANDISER): frozenset({
        UserRole.MERCHANDISER, UserRole.SUPER_ADMIN,
    }),
    # Accounts places request on hold
    (RequestStatus.PENDING_PAYMENT, RequestStatus.HOLD_BY_ACCOUNTS): frozenset({
        UserRole.ACCOUNTS_TEAM, UserRole.SUPER_ADMIN,
    }),
    # Accounts processes payment → locks record
    (RequestStatus.PENDING_PAYMENT, RequestStatus.PAYMENT_PROCESSED): frozenset({
        UserRole.ACCOUNTS_TEAM, UserRole.SUPER_ADMIN,
    }),
    # Merchandiser resumes from own hold
    (RequestStatus.HOLD_BY_MERCHANDISER, RequestStatus.PENDING_PAYMENT): frozenset({
        UserRole.MERCHANDISER, UserRole.SUPER_ADMIN,
    }),
    # Merchandiser cancels while on own hold
    (RequestStatus.HOLD_BY_MERCHANDISER, RequestStatus.CANCELLED_BY_MERCHANDISER): frozenset({
        UserRole.MERCHANDISER, UserRole.SUPER_ADMIN,
    }),
    # Accounts resumes from accounts hold
    (RequestStatus.HOLD_BY_ACCOUNTS, RequestStatus.PENDING_PAYMENT): frozenset({
        UserRole.ACCOUNTS_TEAM, UserRole.SUPER_ADMIN,
    }),
    # Accounts cancels while on accounts hold
    (RequestStatus.HOLD_BY_ACCOUNTS, RequestStatus.CANCELLED_BY_ACCOUNTS): frozenset({
        UserRole.ACCOUNTS_TEAM, UserRole.SUPER_ADMIN,
    }),
    # Accounts reopens a cancelled-by-accounts request
    (RequestStatus.CANCELLED_BY_ACCOUNTS, RequestStatus.REOPENED): frozenset({
        UserRole.ACCOUNTS_TEAM, UserRole.SUPER_ADMIN,
    }),
    # After reopen → back to pending payment
    (RequestStatus.REOPENED, RequestStatus.PENDING_PAYMENT): frozenset({
        UserRole.ACCOUNTS_TEAM, UserRole.SUPER_ADMIN,
    }),
}


def assert_transition_allowed(
    current: RequestStatus,
    target: RequestStatus,
    role: UserRole,
) -> None:
    """
    Raise InvalidStatusTransitionError if the transition is not permitted
    for the given role.
    """
    allowed_roles = _ALLOWED_TRANSITIONS.get((current, target))
    if allowed_roles is None:
        raise InvalidStatusTransitionError(
            f"Transition from '{current.value}' to '{target.value}' is not defined."
        )
    if role not in allowed_roles:
        raise InvalidStatusTransitionError(
            f"Role '{role.value}' cannot transition from '{current.value}' to '{target.value}'."
        )
