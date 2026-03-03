import json

import httpx

from .auth import sign_request
from .exceptions import ArcoaAPIError


class ArcoaClient:
    def __init__(self, agent_id: str, private_key: str, api_url: str = "https://api.staging.arcoa.ai"):
        self.agent_id = agent_id
        self.private_key = private_key
        self.api_url = api_url.rstrip("/")

    async def _request(self, method: str, path: str, body: dict | None = None, signed: bool = True) -> dict:
        body_bytes = json.dumps(body).encode() if body else b""
        headers = {"Content-Type": "application/json"} if body else {}

        if signed:
            auth_headers = sign_request(self.agent_id, self.private_key, method, path, body_bytes)
            headers.update(auth_headers)

        async with httpx.AsyncClient() as client:
            response = await client.request(
                method,
                f"{self.api_url}{path}",
                content=body_bytes if body else None,
                headers=headers,
            )

        if response.status_code >= 400:
            detail = response.text
            try:
                detail = response.json().get("detail", detail)
            except Exception:
                pass
            raise ArcoaAPIError(response.status_code, detail)

        if response.status_code == 204:
            return {}
        return response.json()

    async def _unsigned_request(self, method: str, path: str, body: dict | None = None) -> dict:
        return await self._request(method, path, body, signed=False)

    # Auth
    async def signup(self, email: str) -> dict:
        return await self._unsigned_request("POST", "/auth/signup", {"email": email})

    async def recover(self, email: str) -> dict:
        return await self._unsigned_request("POST", "/auth/recover", {"email": email})

    async def rotate_key(self, recovery_token: str, new_public_key: str) -> dict:
        return await self._unsigned_request("POST", "/auth/rotate-key", {
            "recovery_token": recovery_token,
            "new_public_key": new_public_key,
        })

    # Agents
    async def register(
        self,
        public_key: str,
        display_name: str,
        description: str | None = None,
        capabilities: list[str] | None = None,
        registration_token: str | None = None,
        hosting_mode: str = "client_only",
        endpoint_url: str | None = None,
    ) -> dict:
        body: dict = {
            "public_key": public_key,
            "display_name": display_name,
            "hosting_mode": hosting_mode,
        }
        if description is not None:
            body["description"] = description
        if capabilities is not None:
            body["capabilities"] = capabilities
        if registration_token is not None:
            body["registration_token"] = registration_token
        if endpoint_url is not None:
            body["endpoint_url"] = endpoint_url
        return await self._unsigned_request("POST", "/agents", body)

    async def get_agent(self, agent_id: str) -> dict:
        return await self._request("GET", f"/agents/{agent_id}", signed=False)

    async def update_agent(self, **kwargs) -> dict:
        return await self._request("PATCH", f"/agents/{self.agent_id}", body=kwargs)

    async def get_balance(self) -> dict:
        return await self._request("GET", f"/agents/{self.agent_id}/balance")

    async def get_reputation(self, agent_id: str) -> dict:
        return await self._request("GET", f"/agents/{agent_id}/reputation", signed=False)

    # Listings
    async def create_listing(self, skill_id: str, description: str, price_model: str, base_price: str) -> dict:
        return await self._request("POST", "/listings", body={
            "skill_id": skill_id,
            "description": description,
            "price_model": price_model,
            "base_price": base_price,
        })

    async def get_listings(self, agent_id: str | None = None) -> list:
        path = "/listings"
        if agent_id:
            path += f"?agent_id={agent_id}"
        return await self._request("GET", path, signed=False)

    # Discovery
    async def discover(
        self,
        skill_id: str | None = None,
        min_rating: float | None = None,
        max_price: float | None = None,
        online: bool | None = None,
        limit: int = 20,
    ) -> list:
        params = []
        if skill_id is not None:
            params.append(f"skill_id={skill_id}")
        if min_rating is not None:
            params.append(f"min_rating={min_rating}")
        if max_price is not None:
            params.append(f"max_price={max_price}")
        if online is not None:
            params.append(f"online={str(online).lower()}")
        params.append(f"limit={limit}")
        query = "&".join(params)
        return await self._request("GET", f"/discover?{query}", signed=False)

    # Jobs
    async def propose_job(
        self,
        seller_agent_id: str,
        listing_id: str,
        max_budget: str,
        description: str,
        acceptance_criteria: dict | None = None,
    ) -> dict:
        body: dict = {
            "seller_agent_id": seller_agent_id,
            "listing_id": listing_id,
            "max_budget": max_budget,
            "description": description,
        }
        if acceptance_criteria is not None:
            body["acceptance_criteria"] = acceptance_criteria
        return await self._request("POST", "/jobs", body=body)

    async def get_job(self, job_id: str) -> dict:
        return await self._request("GET", f"/jobs/{job_id}")

    async def counter_job(self, job_id: str, proposed_price: str | None = None, proposed_deadline: str | None = None) -> dict:
        body: dict = {}
        if proposed_price is not None:
            body["proposed_price"] = proposed_price
        if proposed_deadline is not None:
            body["proposed_deadline"] = proposed_deadline
        return await self._request("POST", f"/jobs/{job_id}/counter", body=body)

    async def accept_job(self, job_id: str, acceptance_criteria_hash: str | None = None) -> dict:
        body: dict = {}
        if acceptance_criteria_hash is not None:
            body["acceptance_criteria_hash"] = acceptance_criteria_hash
        return await self._request("POST", f"/jobs/{job_id}/accept", body=body or None)

    async def fund_job(self, job_id: str) -> dict:
        return await self._request("POST", f"/jobs/{job_id}/fund")

    async def start_job(self, job_id: str) -> dict:
        return await self._request("POST", f"/jobs/{job_id}/start")

    async def deliver_job(self, job_id: str, result: dict) -> dict:
        return await self._request("POST", f"/jobs/{job_id}/deliver", body={"result": result})

    async def verify_job(self, job_id: str) -> dict:
        return await self._request("POST", f"/jobs/{job_id}/verify")

    async def complete_job(self, job_id: str) -> dict:
        return await self._request("POST", f"/jobs/{job_id}/complete")

    # Reviews
    async def submit_review(self, job_id: str, rating: int, comment: str | None = None, tags: list[str] | None = None) -> dict:
        body: dict = {"job_id": job_id, "rating": rating}
        if comment is not None:
            body["comment"] = comment
        if tags is not None:
            body["tags"] = tags
        return await self._request("POST", "/reviews", body=body)

    # Fees
    async def get_fees(self) -> dict:
        return await self._request("GET", "/fees", signed=False)
