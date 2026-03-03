class ArcoaError(Exception):
    """Base exception for Arcoa SDK."""


class ArcoaAPIError(ArcoaError):
    """Raised when the API returns an error response."""

    def __init__(self, status_code: int, detail: str = ""):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"API error {status_code}: {detail}")


class ArcoaAuthError(ArcoaError):
    """Raised when authentication fails."""


class ArcoaConfigError(ArcoaError):
    """Raised when config is missing or invalid."""


class ArcoaWebSocketError(ArcoaError):
    """Raised on WebSocket connection issues."""
