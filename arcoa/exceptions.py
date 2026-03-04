"""Typed exceptions for Arcoa API errors."""

from __future__ import annotations


class ArcoaAPIError(Exception):
    """Base exception for Arcoa API errors."""

    def __init__(self, status_code: int, detail: str, response_body: dict | None = None):
        self.status_code = status_code
        self.detail = detail
        self.response_body = response_body
        super().__init__(f"HTTP {status_code}: {detail}")


class NotFoundError(ArcoaAPIError):
    """404 Not Found."""


class ForbiddenError(ArcoaAPIError):
    """403 Forbidden."""


class ConflictError(ArcoaAPIError):
    """409 Conflict."""


class ValidationError(ArcoaAPIError):
    """422 Unprocessable Entity."""


class RateLimitError(ArcoaAPIError):
    """429 Too Many Requests."""

    def __init__(self, status_code: int, detail: str, response_body: dict | None = None, retry_after: float | None = None):
        super().__init__(status_code, detail, response_body)
        self.retry_after = retry_after


class ServerError(ArcoaAPIError):
    """5xx Server Error."""


_STATUS_MAP: dict[int, type[ArcoaAPIError]] = {
    403: ForbiddenError,
    404: NotFoundError,
    409: ConflictError,
    422: ValidationError,
    429: RateLimitError,
}


def raise_for_status(status_code: int, detail: str, response_body: dict | None = None, retry_after: float | None = None) -> None:
    """Raise the appropriate exception subclass for a given HTTP status code."""
    if status_code < 400:
        return
    if status_code == 429:
        raise RateLimitError(status_code, detail, response_body, retry_after)
    cls = _STATUS_MAP.get(status_code)
    if cls is None:
        cls = ServerError if status_code >= 500 else ArcoaAPIError
    raise cls(status_code, detail, response_body)
