"""Domain exceptions. Services raise these; the global handler maps them to HTTP (D-060)."""

from typing import Any


class AppError(Exception):
    status_code: int = 400
    code: str = "bad_request"
    message: str = "The request could not be processed."

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        details: Any = None,
    ) -> None:
        self.message = message or self.message
        self.code = code or self.code
        self.details = details
        super().__init__(self.message)


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"
    message = "The requested resource was not found."


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class VersionConflictError(ConflictError):
    code = "version_conflict"
    message = "This bill was changed by someone else. Reload to see the latest version."


class InvalidStateError(ConflictError):
    code = "invalid_state"


class AuthenticationError(AppError):
    status_code = 401
    code = "not_authenticated"
    message = "Authentication is required."


class InvalidCredentialsError(AuthenticationError):
    code = "invalid_credentials"
    message = "Email or password is incorrect."


class TokenExpiredError(AuthenticationError):
    code = "token_expired"
    message = "Your session has expired. Please sign in again."


class InvalidTokenError(AuthenticationError):
    code = "invalid_token"
    message = "Your session is not valid. Please sign in again."


class ValidationFailedError(AppError):
    status_code = 422
    code = "validation_error"
    message = "Some fields are invalid."


class ApprovalBlockedError(AppError):
    status_code = 422
    code = "approval_blocked"


class PayloadTooLargeError(AppError):
    status_code = 413
    code = "file_too_large"


class UnsupportedMediaTypeError(AppError):
    status_code = 415
    code = "unsupported_file_type"
