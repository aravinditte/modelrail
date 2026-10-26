"""Standardised error taxonomy.

Every error leaving ModelRail uses the OpenAI-style envelope:
{"error": {"message": str, "type": str, "code": str}}
Error *classes* drive retry / fallback decisions (spec section 9).
"""

from __future__ import annotations

import enum


class ErrorClass(str, enum.Enum):
    TIMEOUT = "timeout"
    CONNECTION = "connection"
    RATE_LIMIT = "rate_limit"
    SERVER = "server_error"
    AUTH = "auth_error"
    BAD_REQUEST = "bad_request"
    NOT_FOUND = "not_found"
    UNKNOWN = "unknown"


#: classes where retrying the SAME provider may succeed
RETRYABLE = {ErrorClass.TIMEOUT, ErrorClass.CONNECTION, ErrorClass.RATE_LIMIT, ErrorClass.SERVER}
#: classes where moving to the next eligible route may succeed
FALLBACKABLE = RETRYABLE | {ErrorClass.AUTH}


class ProviderError(Exception):
    def __init__(
        self,
        message: str,
        error_class: ErrorClass = ErrorClass.UNKNOWN,
        status_code: int | None = None,
        retry_after_s: float | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.error_class = error_class
        self.status_code = status_code
        self.retry_after_s = retry_after_s

    @property
    def retryable(self) -> bool:
        return self.error_class in RETRYABLE

    @property
    def fallbackable(self) -> bool:
        return self.error_class in FALLBACKABLE


class GatewayError(Exception):
    """An error that maps directly onto the public API envelope."""

    def __init__(self, status_code: int, code: str, message: str, err_type: str = "invalid_request_error"):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.err_type = err_type

    def envelope(self) -> dict:
        return {"error": {"message": self.message, "type": self.err_type, "code": self.code}}


def err(status: int, code: str, message: str, err_type: str = "invalid_request_error") -> GatewayError:
    return GatewayError(status, code, message, err_type)
