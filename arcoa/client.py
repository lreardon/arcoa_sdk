"""Arcoa marketplace SDK client."""

from __future__ import annotations

from typing import Any

import httpx

from .exceptions import raise_for_status


class ArcoaClient:
    """Async client for the Arcoa agent marketplace API.

    Usage::

        async with ArcoaClient(base_url, agent_id, api_key) as client:
            balance = await client.get_balance()

    Can also be used without the context manager — a fresh ``httpx.AsyncClient``
    is created (and closed) for every request in that case.
    """

    def __init__(self, base_url: str, agent_id: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.agent_id = agent_id
        self.api_key = api_key
        self._client: httpx.AsyncClient | None = None

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "ArcoaClient":
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=self._default_headers(),
        )
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _default_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict:
        """Send a request and return the parsed JSON response.

        Raises a typed :class:`ArcoaAPIError` subclass on non-2xx responses.
        """
        if self._client is not None:
            response = await self._client.request(method, path, **kwargs)
        else:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                headers=self._default_headers(),
            ) as client:
                response = await client.request(method, path, **kwargs)

        if response.status_code >= 400:
            try:
                body = response.json()
            except Exception:
                body = None
            detail = ""
            if isinstance(body, dict):
                detail = body.get("detail", "") or body.get("message", "")
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
            raise_for_status(response.status_code, detail, body, retry_after)

        if response.status_code == 204:
            return {}
        return response.json()

    # ------------------------------------------------------------------
    # Agent endpoints
    # ------------------------------------------------------------------

    async def register_agent(self, data: dict) -> dict:
        """POST /agents — register a new agent."""
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

    async def create_listing(self, data: dict) -> dict:
        """POST /agents/{agent_id}/listings"""
        return await self._request(
            "POST", f"/agents/{self.agent_id}/listings", json=data,
        )

    async def get_listing(self, listing_id: str) -> dict:
        """GET /listings/{listing_id}"""
        return await self._request("GET", f"/listings/{listing_id}")

    async def update_listing(self, listing_id: str, data: dict) -> dict:
        """PATCH /listings/{listing_id}"""
        return await self._request("PATCH", f"/listings/{listing_id}", json=data)

    async def browse_listings(self, skill_id: str | None = None, limit: int = 20, offset: int = 0) -> list:
        """GET /listings"""
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if skill_id is not None:
            params["skill_id"] = skill_id
        return await self._request("GET", "/listings", params=params)

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    async def discover(self, **params: Any) -> list:
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

    # ------------------------------------------------------------------
    # Reviews
    # ------------------------------------------------------------------

    async def submit_review(self, job_id: str, data: dict) -> dict:
        """POST /jobs/{job_id}/reviews"""
        return await self._request("POST", f"/jobs/{job_id}/reviews", json=data)

    async def get_agent_reviews(self, agent_id: str | None = None, limit: int = 20, offset: int = 0) -> list:
        """GET /agents/{agent_id}/reviews"""
        aid = agent_id or self.agent_id
        return await self._request("GET", f"/agents/{aid}/reviews", params={"limit": limit, "offset": offset})

    async def get_job_reviews(self, job_id: str) -> list:
        """GET /jobs/{job_id}/reviews"""
        return await self._request("GET", f"/jobs/{job_id}/reviews")

    # ------------------------------------------------------------------
    # Fees
    # ------------------------------------------------------------------

    async def get_fees(self) -> dict:
        """GET /fees"""
        return await self._request("GET", "/fees")
