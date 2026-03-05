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
PRIVATE_KEY = "a" * 64  # dummy hex key (not used — respx intercepts before signing matters)


def _client() -> ArcoaClient:
    return ArcoaClient(agent_id=AGENT_ID, private_key=PRIVATE_KEY, api_url=BASE)


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


# --------------------------------------------------------------------------
# Agent status & balance
# --------------------------------------------------------------------------


class TestAgentStatusAndBalance:
    @respx.mock
    async def test_get_agent_status(self):
        respx.get(f"{BASE}/agents/{AGENT_ID}/status").mock(
            return_value=httpx.Response(200, json={"status": "active", "display_name": "Bot"}),
        )
        result = await _client().get_agent_status()
        assert result["status"] == "active"

    @respx.mock
    async def test_get_agent_status_other(self):
        other = "11111111-2222-3333-4444-555555555555"
        respx.get(f"{BASE}/agents/{other}/status").mock(
            return_value=httpx.Response(200, json={"status": "inactive"}),
        )
        result = await _client().get_agent_status(other)
        assert result["status"] == "inactive"

    @respx.mock
    async def test_get_agent_balance(self):
        respx.get(f"{BASE}/agents/{AGENT_ID}/balance").mock(
            return_value=httpx.Response(200, json={"balance": "50.00"}),
        )
        result = await _client().get_agent_balance()
        assert result["balance"] == "50.00"

    @respx.mock
    async def test_dev_deposit(self):
        respx.post(f"{BASE}/agents/{AGENT_ID}/deposit").mock(
            return_value=httpx.Response(200, json={"balance": "150.00"}),
        )
        result = await _client().dev_deposit("100.00")
        assert result["balance"] == "150.00"


# --------------------------------------------------------------------------
# Job abort & dispute
# --------------------------------------------------------------------------


class TestJobAbortAndDispute:
    @respx.mock
    async def test_abort_job(self):
        respx.post(f"{BASE}/jobs/j1/abort").mock(
            return_value=httpx.Response(200, json={"job_id": "j1", "status": "aborted"}),
        )
        result = await _client().abort_job("j1")
        assert result["status"] == "aborted"

    @respx.mock
    async def test_dispute_job(self):
        respx.post(f"{BASE}/jobs/j1/dispute").mock(
            return_value=httpx.Response(200, json={"job_id": "j1", "status": "disputed"}),
        )
        result = await _client().dispute_job("j1")
        assert result["status"] == "disputed"


# --------------------------------------------------------------------------
# Webhook methods
# --------------------------------------------------------------------------


class TestWebhookMethods:
    @respx.mock
    async def test_list_webhooks(self):
        respx.get(f"{BASE}/agents/{AGENT_ID}/webhooks").mock(
            return_value=httpx.Response(200, json=[{"delivery_id": "d1", "status": "delivered"}]),
        )
        result = await _client().list_webhooks()
        assert len(result) == 1
        assert result[0]["delivery_id"] == "d1"

    @respx.mock
    async def test_list_webhooks_with_status_filter(self):
        respx.get(f"{BASE}/agents/{AGENT_ID}/webhooks").mock(
            return_value=httpx.Response(200, json=[]),
        )
        result = await _client().list_webhooks(status="failed")
        assert result == []

    @respx.mock
    async def test_redeliver_webhook(self):
        respx.post(f"{BASE}/agents/{AGENT_ID}/webhooks/d1/redeliver").mock(
            return_value=httpx.Response(200, json={"delivery_id": "d1", "status": "pending"}),
        )
        result = await _client().redeliver_webhook("d1")
        assert result["status"] == "pending"


# --------------------------------------------------------------------------
# Auth recovery
# --------------------------------------------------------------------------


class TestAuthMethods:
    @respx.mock
    async def test_signup(self):
        respx.post(f"{BASE}/auth/signup").mock(
            return_value=httpx.Response(200, json={"message": "Verification email sent"}),
        )
        c = ArcoaClient(api_url=BASE)
        result = await c.signup("test@example.com")
        assert "message" in result

    @respx.mock
    async def test_request_recovery(self):
        respx.post(f"{BASE}/auth/recover").mock(
            return_value=httpx.Response(200, json={"message": "Recovery email sent"}),
        )
        c = ArcoaClient(api_url=BASE)
        result = await c.request_recovery("test@example.com")
        assert "message" in result

    @respx.mock
    async def test_rotate_key(self):
        respx.post(f"{BASE}/auth/rotate-key").mock(
            return_value=httpx.Response(200, json={"message": "Public key rotated successfully."}),
        )
        c = ArcoaClient(api_url=BASE)
        result = await c.rotate_key("tok-123", "newpubkey")
        assert "rotated" in result["message"]


# --------------------------------------------------------------------------
# SDK-1: Previously untested client methods
# --------------------------------------------------------------------------


class TestJobLifecycleMissing:
    """counter_job, start_job, complete_job, fail_job."""

    @respx.mock
    async def test_counter_job(self):
        respx.post(f"{BASE}/jobs/j1/counter").mock(
            return_value=httpx.Response(200, json={"job_id": "j1", "status": "proposed"}),
        )
        result = await _client().counter_job("j1", {"max_budget": "200.00"})
        assert result["status"] == "proposed"

    @respx.mock
    async def test_start_job(self):
        respx.post(f"{BASE}/jobs/j1/start").mock(
            return_value=httpx.Response(200, json={"job_id": "j1", "status": "in_progress"}),
        )
        result = await _client().start_job("j1")
        assert result["status"] == "in_progress"

    @respx.mock
    async def test_complete_job(self):
        respx.post(f"{BASE}/jobs/j1/complete").mock(
            return_value=httpx.Response(200, json={"job_id": "j1", "status": "completed"}),
        )
        result = await _client().complete_job("j1")
        assert result["status"] == "completed"

    @respx.mock
    async def test_fail_job(self):
        respx.post(f"{BASE}/jobs/j1/fail").mock(
            return_value=httpx.Response(200, json={"job_id": "j1", "status": "failed"}),
        )
        result = await _client().fail_job("j1")
        assert result["status"] == "failed"


class TestAgentMethodsMissing:
    """update_agent, get_agent_card, register_agent, register."""

    @respx.mock
    async def test_update_agent(self):
        respx.patch(f"{BASE}/agents/{AGENT_ID}").mock(
            return_value=httpx.Response(200, json={"agent_id": AGENT_ID, "display_name": "Updated"}),
        )
        result = await _client().update_agent({"display_name": "Updated"})
        assert result["display_name"] == "Updated"

    @respx.mock
    async def test_get_agent_card(self):
        card = {"agent_id": AGENT_ID, "name": "TestBot", "skills": []}
        respx.get(f"{BASE}/agents/{AGENT_ID}/agent-card").mock(
            return_value=httpx.Response(200, json=card),
        )
        result = await _client().get_agent_card()
        assert result["name"] == "TestBot"

    @respx.mock
    async def test_get_agent_card_other_agent(self):
        other = "11111111-2222-3333-4444-555555555555"
        respx.get(f"{BASE}/agents/{other}/agent-card").mock(
            return_value=httpx.Response(200, json={"agent_id": other, "name": "OtherBot"}),
        )
        result = await _client().get_agent_card(other)
        assert result["agent_id"] == other

    @respx.mock
    async def test_register_agent_raw(self):
        respx.post(f"{BASE}/agents").mock(
            return_value=httpx.Response(201, json={"agent_id": "new-1", "status": "active"}),
        )
        result = await _client().register_agent({"public_key": "abc", "display_name": "Bot"})
        assert result["agent_id"] == "new-1"

    @respx.mock
    async def test_register(self):
        respx.post(f"{BASE}/agents").mock(
            return_value=httpx.Response(201, json={"agent_id": "new-2", "status": "active"}),
        )
        result = await _client().register(
            public_key="abc123",
            display_name="NewBot",
            description="A test bot",
            capabilities=["pdf", "ocr"],
            registration_token="tok-abc",
        )
        assert result["status"] == "active"

    @respx.mock
    async def test_get_reputation(self):
        respx.get(f"{BASE}/agents/{AGENT_ID}/reputation").mock(
            return_value=httpx.Response(200, json={"score": "4.8", "review_count": 12}),
        )
        result = await _client().get_reputation()
        assert result["score"] == "4.8"


class TestListingMethodsMissing:
    """create_listing, get_listing, update_listing, browse_listings."""

    @respx.mock
    async def test_create_listing_with_kwargs(self):
        respx.post(f"{BASE}/agents/{AGENT_ID}/listings").mock(
            return_value=httpx.Response(201, json={"listing_id": "l1", "skill_id": "pdf"}),
        )
        result = await _client().create_listing(
            skill_id="pdf", description="Extract PDFs", base_price="0.05",
        )
        assert result["listing_id"] == "l1"

    @respx.mock
    async def test_create_listing_with_data(self):
        respx.post(f"{BASE}/agents/{AGENT_ID}/listings").mock(
            return_value=httpx.Response(201, json={"listing_id": "l2"}),
        )
        result = await _client().create_listing(data={"skill_id": "ocr", "base_price": "0.10", "price_model": "per_call"})
        assert result["listing_id"] == "l2"

    @respx.mock
    async def test_get_listing(self):
        respx.get(f"{BASE}/listings/l1").mock(
            return_value=httpx.Response(200, json={"listing_id": "l1", "skill_id": "pdf"}),
        )
        result = await _client().get_listing("l1")
        assert result["skill_id"] == "pdf"

    @respx.mock
    async def test_update_listing(self):
        respx.patch(f"{BASE}/listings/l1").mock(
            return_value=httpx.Response(200, json={"listing_id": "l1", "base_price": "0.10"}),
        )
        result = await _client().update_listing("l1", {"base_price": "0.10"})
        assert result["base_price"] == "0.10"

    @respx.mock
    async def test_browse_listings(self):
        respx.get(f"{BASE}/listings").mock(
            return_value=httpx.Response(200, json={"items": [{"listing_id": "l1"}], "total": 1}),
        )
        result = await _client().browse_listings()
        assert result["total"] == 1

    @respx.mock
    async def test_browse_listings_with_filter(self):
        respx.get(f"{BASE}/listings").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0}),
        )
        result = await _client().browse_listings(skill_id="ocr", limit=5, offset=10)
        assert result["total"] == 0


class TestReviewMethodsMissing:
    """submit_review, get_agent_reviews, get_job_reviews."""

    @respx.mock
    async def test_submit_review(self):
        respx.post(f"{BASE}/jobs/j1/reviews").mock(
            return_value=httpx.Response(201, json={"review_id": "r1", "rating": 5}),
        )
        result = await _client().submit_review("j1", {"rating": 5, "comment": "Great work"})
        assert result["rating"] == 5

    @respx.mock
    async def test_get_agent_reviews(self):
        respx.get(f"{BASE}/agents/{AGENT_ID}/reviews").mock(
            return_value=httpx.Response(200, json={"items": [{"rating": 5}], "total": 1}),
        )
        result = await _client().get_agent_reviews()
        assert result["total"] == 1

    @respx.mock
    async def test_get_agent_reviews_other(self):
        other = "11111111-2222-3333-4444-555555555555"
        respx.get(f"{BASE}/agents/{other}/reviews").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0}),
        )
        result = await _client().get_agent_reviews(other)
        assert result["total"] == 0

    @respx.mock
    async def test_get_job_reviews(self):
        respx.get(f"{BASE}/jobs/j1/reviews").mock(
            return_value=httpx.Response(200, json=[{"rating": 5}, {"rating": 4}]),
        )
        result = await _client().get_job_reviews("j1")
        assert len(result) == 2


class TestDiscoverMethod:
    @respx.mock
    async def test_discover(self):
        respx.get(f"{BASE}/discover").mock(
            return_value=httpx.Response(200, json={"items": [{"skill_id": "pdf"}], "total": 1}),
        )
        result = await _client().discover(skill_id="pdf", max_price="1.00")
        assert result["total"] == 1

    @respx.mock
    async def test_discover_no_params(self):
        respx.get(f"{BASE}/discover").mock(
            return_value=httpx.Response(200, json={"items": [], "total": 0}),
        )
        result = await _client().discover()
        assert result["total"] == 0
