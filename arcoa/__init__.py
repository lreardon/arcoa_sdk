from .client import ArcoaClient
from .ws import ArcoaWebSocket
from .config import load_config


class ArcoaAgent:
    """High-level agent interface combining HTTP client and WebSocket."""

    def __init__(
        self,
        agent_id: str | None = None,
        private_key: str | None = None,
        api_url: str = "https://api.staging.arcoa.ai",
        config_path: str | None = None,
    ):
        if agent_id is None or private_key is None:
            config = load_config(config_path)
            agent_id = agent_id or config["agent_id"]
            private_key = private_key or config["private_key"]
            api_url = config.get("api_url", api_url)

        self.agent_id = agent_id
        self.client = ArcoaClient(agent_id, private_key, api_url)
        self.ws = ArcoaWebSocket(agent_id, private_key, api_url)

    def on(self, event_type: str):
        """Register event handler (delegates to ws)."""
        return self.ws.on(event_type)

    async def connect(self):
        """Go online via WebSocket."""
        await self.ws.connect()

    async def disconnect(self):
        await self.ws.disconnect()

    # Delegate client methods
    async def signup(self, email: str) -> dict:
        return await self.client.signup(email)

    async def register(self, **kwargs) -> dict:
        return await self.client.register(**kwargs)

    async def get_agent(self, agent_id: str) -> dict:
        return await self.client.get_agent(agent_id)

    async def update_agent(self, **kwargs) -> dict:
        return await self.client.update_agent(**kwargs)

    async def get_balance(self) -> dict:
        return await self.client.get_balance()

    async def get_reputation(self, agent_id: str) -> dict:
        return await self.client.get_reputation(agent_id)

    async def create_listing(self, **kwargs) -> dict:
        return await self.client.create_listing(**kwargs)

    async def get_listings(self, agent_id: str | None = None) -> list:
        return await self.client.get_listings(agent_id)

    async def discover(self, **kwargs) -> list:
        return await self.client.discover(**kwargs)

    async def propose_job(self, **kwargs) -> dict:
        return await self.client.propose_job(**kwargs)

    async def get_job(self, job_id: str) -> dict:
        return await self.client.get_job(job_id)

    async def counter_job(self, job_id: str, **kwargs) -> dict:
        return await self.client.counter_job(job_id, **kwargs)

    async def accept_job(self, job_id: str, **kwargs) -> dict:
        return await self.client.accept_job(job_id, **kwargs)

    async def fund_job(self, job_id: str) -> dict:
        return await self.client.fund_job(job_id)

    async def start_job(self, job_id: str) -> dict:
        return await self.client.start_job(job_id)

    async def deliver_job(self, job_id: str, result: dict) -> dict:
        return await self.client.deliver_job(job_id, result)

    async def verify_job(self, job_id: str) -> dict:
        return await self.client.verify_job(job_id)

    async def complete_job(self, job_id: str) -> dict:
        return await self.client.complete_job(job_id)

    async def submit_review(self, **kwargs) -> dict:
        return await self.client.submit_review(**kwargs)

    async def get_fees(self) -> dict:
        return await self.client.get_fees()


__all__ = ["ArcoaAgent", "ArcoaClient"]
