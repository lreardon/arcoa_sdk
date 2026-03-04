"""Tests for typed exception hierarchy."""

import pytest

from arcoa.exceptions import (
    ArcoaAPIError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    RateLimitError,
    ServerError,
    ValidationError,
    raise_for_status,
)


class TestExceptionHierarchy:
    def test_all_subclass_arcoa_api_error(self):
        for cls in (NotFoundError, ForbiddenError, ConflictError, ValidationError, RateLimitError, ServerError):
            assert issubclass(cls, ArcoaAPIError)

    def test_arcoa_api_error_attributes(self):
        err = ArcoaAPIError(400, "bad request", {"detail": "bad"})
        assert err.status_code == 400
        assert err.detail == "bad request"
        assert err.response_body == {"detail": "bad"}
        assert "400" in str(err)

    def test_rate_limit_error_retry_after(self):
        err = RateLimitError(429, "slow down", retry_after=5.0)
        assert err.retry_after == 5.0


class TestRaiseForStatus:
    def test_2xx_no_raise(self):
        raise_for_status(200, "ok")  # should not raise

    def test_403_forbidden(self):
        with pytest.raises(ForbiddenError) as exc_info:
            raise_for_status(403, "forbidden")
        assert exc_info.value.status_code == 403

    def test_404_not_found(self):
        with pytest.raises(NotFoundError):
            raise_for_status(404, "not found")

    def test_409_conflict(self):
        with pytest.raises(ConflictError):
            raise_for_status(409, "conflict")

    def test_422_validation(self):
        with pytest.raises(ValidationError):
            raise_for_status(422, "invalid")

    def test_429_rate_limit(self):
        with pytest.raises(RateLimitError) as exc_info:
            raise_for_status(429, "too many", retry_after=10.0)
        assert exc_info.value.retry_after == 10.0

    def test_500_server_error(self):
        with pytest.raises(ServerError):
            raise_for_status(500, "internal")

    def test_502_server_error(self):
        with pytest.raises(ServerError):
            raise_for_status(502, "bad gateway")

    def test_400_generic(self):
        with pytest.raises(ArcoaAPIError) as exc_info:
            raise_for_status(400, "bad")
        # Should be the base class, not a subclass
        assert type(exc_info.value) is ArcoaAPIError

    def test_418_generic(self):
        with pytest.raises(ArcoaAPIError):
            raise_for_status(418, "teapot")
