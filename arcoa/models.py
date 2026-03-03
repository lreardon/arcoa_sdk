from pydantic import BaseModel


class AgentInfo(BaseModel):
    agent_id: str
    display_name: str
    public_key: str | None = None
    description: str | None = None
    capabilities: list[str] | None = None
    hosting_mode: str | None = None
    endpoint_url: str | None = None
    status: str | None = None


class Balance(BaseModel):
    agent_id: str
    balance: str


class Reputation(BaseModel):
    agent_id: str
    seller_rating: float | None = None
    client_rating: float | None = None
    total_reviews: int = 0


class Listing(BaseModel):
    listing_id: str
    agent_id: str
    skill_id: str
    description: str
    price_model: str
    base_price: str
    status: str | None = None


class Job(BaseModel):
    job_id: str
    buyer_agent_id: str | None = None
    seller_agent_id: str | None = None
    listing_id: str | None = None
    status: str | None = None
    max_budget: str | None = None
    description: str | None = None


class DiscoveryResult(BaseModel):
    agent_id: str
    display_name: str
    skill_id: str | None = None
    base_price: str | None = None
    price_model: str | None = None
    rating: float | None = None
    capabilities: list[str] | None = None


class Fees(BaseModel):
    platform_fee_percent: float | None = None
    escrow_fee_percent: float | None = None
