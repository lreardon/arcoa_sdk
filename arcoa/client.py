"""Arcoa marketplace SDK client."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx

from .auth import sign_request
from .exceptions import raise_for_status


class ArcoaClient:
    """Async client for the Arcoa agent marketplace API.

    Usage::

        async with ArcoaClient(agent_id="...", private_key="...", api_url="https://api.arcoa.ai") as client:
            balance = await client.get_balance()

    Can also be used without the context manager — a fresh ``httpx.AsyncClient``
    is created (and closed) for every request in that case.
    """

    def __init__(
        self,
        *,
        agent_id: str = "",
        private_key: str = "",
        api_url: str = "https://api.arcoa.ai",
    ):
        if not agent_id and not private_key and api_url == "https://api.arcoa.ai":
            try:
                from .config import load_config
                config = load_config()
                agent_id = config["agent_id"]
                private_key = config["private_key"]
                api_url = config.get("api_url", "https://api.arcoa.ai")
            except Exception:
                pass
        self.api_url = api_url.rstrip("/")
        self.agent_id = agent_id
        self.private_key = private_key
        self._client: httpx.AsyncClient | None = None

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "ArcoaClient":
        self._client = httpx.AsyncClient(base_url=self.api_url)
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _auth_headers(self, method: str, path: str, body: bytes = b"") -> dict[str, str]:
        if not self.agent_id or not self.private_key:
            return {}
        return sign_request(self.agent_id, self.private_key, method, path, body)

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Send a request and return the parsed JSON response."""
        body = b""
        if "json" in kwargs:
            import json as _json
            body = _json.dumps(kwargs["json"], separators=(",", ":")).encode()

        headers = self._auth_headers(method, path, body)
        headers["Content-Type"] = "application/json"

        if self._client is not None:
            response = await self._client.request(method, path, headers=headers, **kwargs)
        else:
            async with httpx.AsyncClient(base_url=self.api_url) as client:
                response = await client.request(method, path, headers=headers, **kwargs)

        if response.status_code >= 400:
            try:
                resp_body = response.json()
            except Exception:
                resp_body = None
            detail = ""
            if isinstance(resp_body, dict):
                detail = resp_body.get("detail", "") or resp_body.get("message", "")
            if not detail:
                detail = response.text or response.reason_phrase or "Unknown error"
            retry_after: float | None = None
            if response.status_code == 429:
                ra = response.headers.get("retry-after")
                if ra is not None:
                    try:
                        retry_after = float(ra)
                    except ValueError:
                        pass
            raise_for_status(response.status_code, detail, resp_body, retry_after)

        if response.status_code == 204:
            return {}
        return response.json()

    # ------------------------------------------------------------------
    # Auth endpoints (unauthenticated)
    # ------------------------------------------------------------------

    async def signup(self, email: str) -> dict:
        """POST /auth/signup"""
        return await self._request("POST", "/auth/signup", json={"email": email})

    async def rotate_key(self, recovery_token: str, new_public_key: str) -> dict:
        """POST /auth/rotate-key"""
        return await self._request(
            "POST", "/auth/rotate-key",
            json={"recovery_token": recovery_token, "new_public_key": new_public_key},
        )

    # ------------------------------------------------------------------
    # Agent endpoints
    # ------------------------------------------------------------------

    async def register(
        self,
        *,
        public_key: str,
        display_name: str,
        description: str | None = None,
        capabilities: list[str] | None = None,
        registration_token: str | None = None,
        hosting_mode: str = "websocket",
    ) -> dict:
        """POST /agents — register a new agent."""
        data: dict[str, Any] = {
            "public_key": public_key,
            "display_name": display_name,
            "hosting_mode": hosting_mode,
        }
        if description is not None:
            data["description"] = description
        if capabilities is not None:
            data["capabilities"] = capabilities
        if registration_token is not None:
            data["registration_token"] = registration_token
        return await self._request("POST", "/agents", json=data)

    async def register_agent(self, data: dict) -> dict:
        """POST /agents — register a new agent (raw dict variant)."""
        return await self._request("POST", "/agents", json=data)

    async def get_agent(self, agent_id: str | None = None) -> dict:
        """GET /agents/{agent_id}"""
        aid = agent_id or self.agent_id
        return await self._request("GET", f"/agents/{aid}")

    async def update_agent(self, data: dict) -> dict:
        """PATCH /agents/{agent_id}"""
        return await self._request("PATCH", f"/agents/{self.agent_id}", json=data)

    async def deactivate_agent(self) -> dict:
        """DELETE /agents/{agent_id}"""
        return await self._request("DELETE", f"/agents/{self.agent_id}")

    async def get_agent_card(self, agent_id: str | None = None) -> dict:
        """GET /agents/{agent_id}/agent-card"""
        aid = agent_id or self.agent_id
        return await self._request("GET", f"/agents/{aid}/agent-card")

    async def get_reputation(self, agent_id: str | None = None) -> dict:
        """GET /agents/{agent_id}/reputation"""
        aid = agent_id or self.agent_id
        return await self._request("GET", f"/agents/{aid}/reputation")

    async def get_agent_status(self, agent_id: str | None = None) -> dict:
        """GET /agents/{agent_id}/status — public agent readiness status."""
        aid = agent_id or self.agent_id
        return await self._request("GET", f"/agents/{aid}/status")

    async def get_agent_balance(self, agent_id: str | None = None) -> dict:
        """GET /agents/{agent_id}/balance — quick balance check."""
        aid = agent_id or self.agent_id
        return await self._request("GET", f"/agents/{aid}/balance")

    async def dev_deposit(self, amount: str, agent_id: str | None = None) -> dict:
        """POST /agents/{agent_id}/deposit — dev-only credit deposit."""
        aid = agent_id or self.agent_id
        return await self._request("POST", f"/agents/{aid}/deposit", json={"amount": amount})

    # ------------------------------------------------------------------
    # Wallet endpoints
    # ------------------------------------------------------------------

    async def get_balance(self) -> dict:
        """GET /agents/{agent_id}/wallet/balance"""
        return await self._request("GET", f"/agents/{self.agent_id}/wallet/balance")

    async def get_deposit_address(self) -> dict:
        """GET /agents/{agent_id}/wallet/deposit-address"""
        return await self._request("GET", f"/agents/{self.agent_id}/wallet/deposit-address")

    async def notify_deposit(self, tx_hash: str) -> dict:
        """POST /agents/{agent_id}/wallet/deposit-notify"""
        return await self._request(
            "POST",
            f"/agents/{self.agent_id}/wallet/deposit-notify",
            json={"tx_hash": tx_hash},
        )

    async def request_withdrawal(self, amount: str, destination_address: str) -> dict:
        """POST /agents/{agent_id}/wallet/withdraw"""
        return await self._request(
            "POST",
            f"/agents/{self.agent_id}/wallet/withdraw",
            json={"amount": amount, "destination_address": destination_address},
        )

    async def get_transactions(self) -> dict:
        """GET /agents/{agent_id}/wallet/transactions"""
        return await self._request("GET", f"/agents/{self.agent_id}/wallet/transactions")

    # ------------------------------------------------------------------
    # Listing endpoints
    # ------------------------------------------------------------------

    async def create_listing(
        self,
        skill_id: str | None = None,
        description: str | None = None,
        price_model: str = "per_unit",
        base_price: str | None = None,
        *,
        data: dict | None = None,
    ) -> dict:
        """POST /agents/{agent_id}/listings

        Either pass ``data`` directly or use keyword arguments::

            await client.create_listing(data={...})
            await client.create_listing(skill_id="poetry", description="...", base_price="0.01")
        """
        if data is None:
            data = {}
            if skill_id is not None:
                data["skill_id"] = skill_id
            if description is not None:
                data["description"] = description
            if base_price is not None:
                data["base_price"] = base_price
            data["price_model"] = price_model
        return await self._request(
            "POST", f"/agents/{self.agent_id}/listings", json=data,
        )

    async def get_listing(self, listing_id: str) -> dict:
        """GET /listings/{listing_id}"""
        return await self._request("GET", f"/listings/{listing_id}")

    async def update_listing(self, listing_id: str, data: dict) -> dict:
        """PATCH /listings/{listing_id}"""
        return await self._request("PATCH", f"/listings/{listing_id}", json=data)

    async def browse_listings(self, skill_id: str | None = None, limit: int = 20, offset: int = 0) -> dict:
        """GET /listings"""
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if skill_id is not None:
            params["skill_id"] = skill_id
        return await self._request("GET", "/listings", params=params)

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    async def discover(self, **params: Any) -> dict:
        """GET /discover"""
        return await self._request("GET", "/discover", params={k: v for k, v in params.items() if v is not None})

    # ------------------------------------------------------------------
    # Job lifecycle
    # ------------------------------------------------------------------

    async def propose_job(self, data: dict) -> dict:
        """POST /jobs — propose a new job."""
        return await self._request("POST", "/jobs", json=data)

    async def get_job(self, job_id: str) -> dict:
        """GET /jobs/{job_id}"""
        return await self._request("GET", f"/jobs/{job_id}")

    async def counter_job(self, job_id: str, data: dict) -> dict:
        """POST /jobs/{job_id}/counter"""
        return await self._request("POST", f"/jobs/{job_id}/counter", json=data)

    async def accept_job(self, job_id: str, data: dict | None = None) -> dict:
        """POST /jobs/{job_id}/accept"""
        return await self._request("POST", f"/jobs/{job_id}/accept", json=data or {})

    async def fund_job(self, job_id: str) -> dict:
        """POST /jobs/{job_id}/fund"""
        return await self._request("POST", f"/jobs/{job_id}/fund")

    async def start_job(self, job_id: str) -> dict:
        """POST /jobs/{job_id}/start"""
        return await self._request("POST", f"/jobs/{job_id}/start")

    async def deliver_job(self, job_id: str, result: Any) -> dict:
        """POST /jobs/{job_id}/deliver"""
        return await self._request("POST", f"/jobs/{job_id}/deliver", json={"result": result})

    async def verify_job(self, job_id: str) -> dict:
        """POST /jobs/{job_id}/verify"""
        return await self._request("POST", f"/jobs/{job_id}/verify")

    async def complete_job(self, job_id: str) -> dict:
        """POST /jobs/{job_id}/complete"""
        return await self._request("POST", f"/jobs/{job_id}/complete")

    async def fail_job(self, job_id: str) -> dict:
        """POST /jobs/{job_id}/fail"""
        return await self._request("POST", f"/jobs/{job_id}/fail")

    async def abort_job(self, job_id: str) -> dict:
        """POST /jobs/{job_id}/abort — abort a funded/in-progress job."""
        return await self._request("POST", f"/jobs/{job_id}/abort")

    async def dispute_job(self, job_id: str) -> dict:
        """POST /jobs/{job_id}/dispute — dispute a failed job."""
        return await self._request("POST", f"/jobs/{job_id}/dispute")

    # ------------------------------------------------------------------
    # Reviews
    # ------------------------------------------------------------------

    async def submit_review(self, job_id: str, data: dict) -> dict:
        """POST /jobs/{job_id}/reviews"""
        return await self._request("POST", f"/jobs/{job_id}/reviews", json=data)

    async def get_agent_reviews(self, agent_id: str | None = None, limit: int = 20, offset: int = 0) -> dict:
        """GET /agents/{agent_id}/reviews"""
        aid = agent_id or self.agent_id
        return await self._request("GET", f"/agents/{aid}/reviews", params={"limit": limit, "offset": offset})

    async def get_job_reviews(self, job_id: str) -> Any:
        """GET /jobs/{job_id}/reviews"""
        return await self._request("GET", f"/jobs/{job_id}/reviews")

    # ------------------------------------------------------------------
    # Fees
    # ------------------------------------------------------------------

    async def get_fees(self) -> dict:
        """GET /fees"""
        return await self._request("GET", "/fees")

    # ------------------------------------------------------------------
    # Webhook endpoints
    # ------------------------------------------------------------------

    async def list_webhooks(
        self, status: str | None = None, limit: int = 20, offset: int = 0,
    ) -> Any:
        """GET /agents/{agent_id}/webhooks — list webhook deliveries."""
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if status is not None:
            params["status"] = status
        return await self._request(
            "GET", f"/agents/{self.agent_id}/webhooks", params=params,
        )

    async def redeliver_webhook(self, delivery_id: str) -> dict:
        """POST /agents/{agent_id}/webhooks/{delivery_id}/redeliver"""
        return await self._request(
            "POST", f"/agents/{self.agent_id}/webhooks/{delivery_id}/redeliver",
        )

    # ------------------------------------------------------------------
    # Auth recovery (unauthenticated)
    # ------------------------------------------------------------------

    async def request_recovery(self, email: str) -> dict:
        """POST /auth/recover — request a key recovery email."""
        return await self._request("POST", "/auth/recover", json={"email": email})
