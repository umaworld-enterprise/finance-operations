"""Custom exception hierarchy for the application."""

from http import HTTPStatus


class AppError(Exception):
    """Base application error."""

    status_code: int = HTTPStatus.INTERNAL_SERVER_ERROR
    error_code: str = "INTERNAL_ERROR"

    def __init__(self, message: str, detail: str | None = None) -> None:
        self.message = message
        self.detail = detail
        super().__init__(message)


class NotFoundError(AppError):
    status_code = HTTPStatus.NOT_FOUND
    error_code = "NOT_FOUND"


class ValidationError(AppError):
    status_code = HTTPStatus.UNPROCESSABLE_ENTITY
    error_code = "VALIDATION_ERROR"


class AuthenticationError(AppError):
    status_code = HTTPStatus.UNAUTHORIZED
    error_code = "AUTHENTICATION_ERROR"


class AuthorizationError(AppError):
    status_code = HTTPStatus.FORBIDDEN
    error_code = "AUTHORIZATION_ERROR"


class ConflictError(AppError):
    status_code = HTTPStatus.CONFLICT
    error_code = "CONFLICT"


class BusinessRuleError(AppError):
    """Raised when a domain business rule is violated."""
    status_code = HTTPStatus.UNPROCESSABLE_ENTITY
    error_code = "BUSINESS_RULE_VIOLATION"


class SupplierDefaultedError(BusinessRuleError):
    """Raised when a request targets a defaulted supplier."""
    error_code = "SUPPLIER_DEFAULTED"


class RecordLockedError(BusinessRuleError):
    """Raised when attempting to modify a locked record."""
    error_code = "RECORD_LOCKED"


class InvalidStatusTransitionError(BusinessRuleError):
    """Raised when a status transition is not permitted."""
    error_code = "INVALID_STATUS_TRANSITION"


class IntegrationError(AppError):
    """Raised by external integration failures (Google Form/Sheet)."""
    status_code = HTTPStatus.BAD_GATEWAY
    error_code = "INTEGRATION_ERROR"
