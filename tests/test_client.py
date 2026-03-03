import json
import pytest
import httpx
import respx

from arcoa.auth import generate_keypair
from arcoa.client import ArcoaClient
from arcoa.exceptions import ArcoaAPIError

AGENT_ID = "test-agent-id"
API_URL = "https://api.staging.arcoa.ai"


@pytest.fixture
def keys():
    return generate_keypair()


@pytest.fixture
def client(keys):
    return ArcoaClient(AGENT_ID, keys[0], API_URL)


class TestUnsignedRequests:
    @respx.mock
    async def test_signup(self, client):
        respx.post(f"{API_URL}/auth/signup").mock(
            return_value=httpx.Response(200, json={"message": "ok", "token": "abc"})
        )
        result = await client.signup("test@example.com")
        assert result["token"] == "abc"

    @respx.mock
    async def test_register(self, client):
        respx.post(f"{API_URL}/agents").mock(
            return_value=httpx.Response(200, json={"agent_id": "new-id", "display_name": "Bot"})
        )
        result = await client.register(
            public_key="deadbeef",
            display_name="Bot",
            registration_token="tok",
        )
        assert result["agent_id"] == "new-id"

    @respx.mock
    async def test_register_no_auth_header(self, client):
        route = respx.post(f"{API_URL}/agents").mock(
            return_value=httpx.Response(200, json={"agent_id": "x"})
        )
        await client.register(public_key="ab", display_name="B")
        request = route.calls[0].request
        assert "Authorization" not in request.headers

    @respx.mock
    async def test_get_agent(self, client):
        respx.get(f"{API_URL}/agents/some-id").mock(
            return_value=httpx.Response(200, json={"agent_id": "some-id", "display_name": "X"})
        )
        result = await client.get_agent("some-id")
        assert result["agent_id"] == "some-id"

    @respx.mock
    async def test_get_reputation(self, client):
        respx.get(f"{API_URL}/agents/some-id/reputation").mock(
            return_value=httpx.Response(200, json={"seller_rating": 4.5})
        )
        result = await client.get_reputation("some-id")
        assert result["seller_rating"] == 4.5

    @respx.mock
    async def test_get_fees(self, client):
        respx.get(f"{API_URL}/fees").mock(
            return_value=httpx.Response(200, json={"platform_fee_percent": 5.0})
        )
        result = await client.get_fees()
        assert result["platform_fee_percent"] == 5.0

    @respx.mock
    async def test_get_listings(self, client):
        respx.get(f"{API_URL}/listings").mock(
            return_value=httpx.Response(200, json=[{"listing_id": "l1"}])
        )
        result = await client.get_listings()
        assert len(result) == 1

    @respx.mock
    async def test_discover(self, client):
        respx.get(url__startswith=f"{API_URL}/discover").mock(
            return_value=httpx.Response(200, json=[{"agent_id": "a1"}])
        )
        result = await client.discover(skill_id="pdf", online=True, limit=5)
        assert len(result) == 1


class TestSignedRequests:
    @respx.mock
    async def test_update_agent_sends_auth(self, client):
        route = respx.patch(f"{API_URL}/agents/{AGENT_ID}").mock(
            return_value=httpx.Response(200, json={"agent_id": AGENT_ID})
        )
        await client.update_agent(display_name="NewName")
        request = route.calls[0].request
        assert "Authorization" in request.headers
        assert request.headers["Authorization"].startswith(f"AgentSig {AGENT_ID}:")
        assert "X-Timestamp" in request.headers
        assert "X-Nonce" in request.headers

    @respx.mock
    async def test_get_balance(self, client):
        respx.get(f"{API_URL}/agents/{AGENT_ID}/balance").mock(
            return_value=httpx.Response(200, json={"agent_id": AGENT_ID, "balance": "100.00"})
        )
        result = await client.get_balance()
        assert result["balance"] == "100.00"

    @respx.mock
    async def test_create_listing(self, client):
        respx.post(f"{API_URL}/listings").mock(
            return_value=httpx.Response(200, json={"listing_id": "l1"})
        )
        result = await client.create_listing("pdf", "Extract PDF", "per_unit", "0.05")
        assert result["listing_id"] == "l1"

    @respx.mock
    async def test_propose_job(self, client):
        respx.post(f"{API_URL}/jobs").mock(
            return_value=httpx.Response(200, json={"job_id": "j1", "status": "proposed"})
        )
        result = await client.propose_job("seller-1", "l1", "10.00", "Do the thing")
        assert result["job_id"] == "j1"

    @respx.mock
    async def test_get_job(self, client):
        respx.get(f"{API_URL}/jobs/j1").mock(
            return_value=httpx.Response(200, json={"job_id": "j1"})
        )
        result = await client.get_job("j1")
        assert result["job_id"] == "j1"

    @respx.mock
    async def test_job_lifecycle(self, client):
        for action in ["accept", "fund", "start", "verify", "complete"]:
            respx.post(f"{API_URL}/jobs/j1/{action}").mock(
                return_value=httpx.Response(200, json={"job_id": "j1", "status": action})
            )

        assert (await client.accept_job("j1"))["status"] == "accept"
        assert (await client.fund_job("j1"))["status"] == "fund"
        assert (await client.start_job("j1"))["status"] == "start"
        assert (await client.verify_job("j1"))["status"] == "verify"
        assert (await client.complete_job("j1"))["status"] == "complete"

    @respx.mock
    async def test_deliver_job(self, client):
        respx.post(f"{API_URL}/jobs/j1/deliver").mock(
            return_value=httpx.Response(200, json={"job_id": "j1", "status": "delivered"})
        )
        result = await client.deliver_job("j1", {"output": "data"})
        assert result["status"] == "delivered"

    @respx.mock
    async def test_counter_job(self, client):
        respx.post(f"{API_URL}/jobs/j1/counter").mock(
            return_value=httpx.Response(200, json={"job_id": "j1"})
        )
        result = await client.counter_job("j1", proposed_price="5.00")
        assert result["job_id"] == "j1"

    @respx.mock
    async def test_submit_review(self, client):
        respx.post(f"{API_URL}/reviews").mock(
            return_value=httpx.Response(200, json={"review_id": "r1"})
        )
        result = await client.submit_review("j1", 5, comment="Great")
        assert result["review_id"] == "r1"


class TestErrorHandling:
    @respx.mock
    async def test_4xx_error(self, client):
        respx.get(f"{API_URL}/agents/bad-id").mock(
            return_value=httpx.Response(404, json={"detail": "Not found"})
        )
        with pytest.raises(ArcoaAPIError) as exc_info:
            await client.get_agent("bad-id")
        assert exc_info.value.status_code == 404
        assert "Not found" in exc_info.value.detail

    @respx.mock
    async def test_5xx_error(self, client):
        respx.get(f"{API_URL}/agents/{AGENT_ID}/balance").mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )
        with pytest.raises(ArcoaAPIError) as exc_info:
            await client.get_balance()
        assert exc_info.value.status_code == 500

    @respx.mock
    async def test_204_returns_empty_dict(self, client):
        respx.post(f"{API_URL}/jobs/j1/complete").mock(
            return_value=httpx.Response(204)
        )
        result = await client.complete_job("j1")
        assert result == {}
