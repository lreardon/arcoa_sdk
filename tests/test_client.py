"""Tests for ArcoaClient — wallet methods, context manager, error handling."""

import httpx
import pytest
import respx

from arcoa import ArcoaClient
from arcoa.exceptions import (
    ArcoaAPIError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    RateLimitError,
    ServerError,
    ValidationError,
)

BASE = "https://api.arcoa.test"
AGENT_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
API_KEY = "test-key-123"


def _client() -> ArcoaClient:
    return ArcoaClient(BASE, AGENT_ID, API_KEY)


# --------------------------------------------------------------------------
# Context manager
# --------------------------------------------------------------------------


class TestContextManager:
    @respx.mock
    async def test_async_context_manager(self):
        route = respx.get(f"{BASE}/fees").mock(return_value=httpx.Response(200, json={"base": "1%"}))
        async with _client() as c:
            result = await c.get_fees()
            assert result == {"base": "1%"}
        assert route.called

    @respx.mock
    async def test_reuses_connection(self):
        """Inside `async with`, the same httpx.AsyncClient is reused."""
        respx.get(f"{BASE}/fees").mock(return_value=httpx.Response(200, json={}))
        async with _client() as c:
            assert c._client is not None
            first_client = c._client
            await c.get_fees()
            await c.get_fees()
            assert c._client is first_client
        assert c._client is None  # closed

    @respx.mock
    async def test_without_context_manager(self):
        respx.get(f"{BASE}/fees").mock(return_value=httpx.Response(200, json={"ok": True}))
        c = _client()
        result = await c.get_fees()
        assert result == {"ok": True}
        assert c._client is None  # never assigned


# --------------------------------------------------------------------------
# Wallet methods
# --------------------------------------------------------------------------


class TestWalletMethods:
    @respx.mock
    async def test_get_balance(self):
        respx.get(f"{BASE}/agents/{AGENT_ID}/wallet/balance").mock(
            return_value=httpx.Response(200, json={"balance": "100.00", "available_balance": "90.00", "pending_withdrawals": "10.00"}),
        )
        result = await _client().get_balance()
        assert result["balance"] == "100.00"

    @respx.mock
    async def test_get_deposit_address(self):
        body = {"agent_id": AGENT_ID, "address": "0xabc", "network": "base_sepolia"}
        respx.get(f"{BASE}/agents/{AGENT_ID}/wallet/deposit-address").mock(
            return_value=httpx.Response(200, json=body),
        )
        result = await _client().get_deposit_address()
        assert result["address"] == "0xabc"

    @respx.mock
    async def test_notify_deposit(self):
        respx.post(f"{BASE}/agents/{AGENT_ID}/wallet/deposit-notify").mock(
            return_value=httpx.Response(201, json={"status": "pending", "tx_hash": "0xdef"}),
        )
        result = await _client().notify_deposit("0xdef")
        assert result["tx_hash"] == "0xdef"

    @respx.mock
    async def test_request_withdrawal(self):
        respx.post(f"{BASE}/agents/{AGENT_ID}/wallet/withdraw").mock(
            return_value=httpx.Response(201, json={"status": "pending", "amount": "50.00"}),
        )
        result = await _client().request_withdrawal("50.00", "0x123")
        assert result["amount"] == "50.00"

    @respx.mock
    async def test_get_transactions(self):
        respx.get(f"{BASE}/agents/{AGENT_ID}/wallet/transactions").mock(
            return_value=httpx.Response(200, json={"deposits": [], "withdrawals": []}),
        )
        result = await _client().get_transactions()
        assert "deposits" in result


# --------------------------------------------------------------------------
# Job lifecycle methods
# --------------------------------------------------------------------------


class TestJobMethods:
    @respx.mock
    async def test_propose_job(self):
        respx.post(f"{BASE}/jobs").mock(
            return_value=httpx.Response(201, json={"job_id": "j1", "status": "proposed"}),
        )
        result = await _client().propose_job({"seller_agent_id": "s1", "requirements": "test"})
        assert result["status"] == "proposed"

    @respx.mock
    async def test_get_job(self):
        respx.get(f"{BASE}/jobs/j1").mock(
            return_value=httpx.Response(200, json={"job_id": "j1"}),
        )
        assert (await _client().get_job("j1"))["job_id"] == "j1"

    @respx.mock
    async def test_accept_and_fund(self):
        respx.post(f"{BASE}/jobs/j1/accept").mock(
            return_value=httpx.Response(200, json={"status": "agreed"}),
        )
        respx.post(f"{BASE}/jobs/j1/fund").mock(
            return_value=httpx.Response(200, json={"status": "funded"}),
        )
        c = _client()
        assert (await c.accept_job("j1"))["status"] == "agreed"
        assert (await c.fund_job("j1"))["status"] == "funded"

    @respx.mock
    async def test_deliver_and_verify(self):
        respx.post(f"{BASE}/jobs/j1/deliver").mock(
            return_value=httpx.Response(200, json={"status": "delivered"}),
        )
        respx.post(f"{BASE}/jobs/j1/verify").mock(
            return_value=httpx.Response(200, json={"status": "completed"}),
        )
        c = _client()
        assert (await c.deliver_job("j1", {"output": "done"}))["status"] == "delivered"
        assert (await c.verify_job("j1"))["status"] == "completed"


# --------------------------------------------------------------------------
# Error handling
# --------------------------------------------------------------------------


class TestErrorHandling:
    @respx.mock
    async def test_403_raises_forbidden(self):
        respx.get(f"{BASE}/agents/{AGENT_ID}/wallet/balance").mock(
            return_value=httpx.Response(403, json={"detail": "Can only access own wallet"}),
        )
        with pytest.raises(ForbiddenError) as exc_info:
            await _client().get_balance()
        assert exc_info.value.status_code == 403
        assert "own wallet" in exc_info.value.detail

    @respx.mock
    async def test_404_raises_not_found(self):
        respx.get(f"{BASE}/jobs/missing").mock(
            return_value=httpx.Response(404, json={"detail": "Job not found"}),
        )
        with pytest.raises(NotFoundError):
            await _client().get_job("missing")

    @respx.mock
    async def test_409_raises_conflict(self):
        respx.post(f"{BASE}/jobs/j1/fund").mock(
            return_value=httpx.Response(409, json={"detail": "Already funded"}),
        )
        with pytest.raises(ConflictError):
            await _client().fund_job("j1")

    @respx.mock
    async def test_422_raises_validation(self):
        respx.post(f"{BASE}/jobs").mock(
            return_value=httpx.Response(422, json={"detail": "missing field"}),
        )
        with pytest.raises(ValidationError):
            await _client().propose_job({})

    @respx.mock
    async def test_429_raises_rate_limit_with_retry_after(self):
        respx.get(f"{BASE}/fees").mock(
            return_value=httpx.Response(429, json={"detail": "rate limited"}, headers={"Retry-After": "30"}),
        )
        with pytest.raises(RateLimitError) as exc_info:
            await _client().get_fees()
        assert exc_info.value.retry_after == 30.0

    @respx.mock
    async def test_500_raises_server_error(self):
        respx.get(f"{BASE}/fees").mock(
            return_value=httpx.Response(500, json={"detail": "internal server error"}),
        )
        with pytest.raises(ServerError):
            await _client().get_fees()

    @respx.mock
    async def test_204_returns_empty_dict(self):
        respx.delete(f"{BASE}/agents/{AGENT_ID}").mock(
            return_value=httpx.Response(204),
        )
        result = await _client().deactivate_agent()
        assert result == {}

    @respx.mock
    async def test_error_with_non_json_body(self):
        respx.get(f"{BASE}/fees").mock(
            return_value=httpx.Response(503, text="Service Unavailable"),
        )
        with pytest.raises(ServerError) as exc_info:
            await _client().get_fees()
        assert "Service Unavailable" in exc_info.value.detail
