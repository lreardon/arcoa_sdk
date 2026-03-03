import asyncio
import click

from .auth import generate_keypair
from .client import ArcoaClient
from .config import load_config, save_config, config_exists
from .exceptions import ArcoaConfigError


@click.group()
def cli():
    """Arcoa agent marketplace CLI."""
    pass


@cli.command()
@click.option("--name", required=True, help="Agent display name")
@click.option("--token", required=True, help="Registration token from email verification")
@click.option("--api-url", default="https://api.staging.arcoa.ai", help="API base URL")
@click.option("--description", default=None, help="Agent description")
@click.option("--capabilities", default=None, help="Comma-separated capabilities")
def init(name: str, token: str, api_url: str, description: str | None, capabilities: str | None):
    """Register a new agent and save config."""
    click.echo("Generating Ed25519 keypair...")
    private_key, public_key = generate_keypair()

    caps = [c.strip() for c in capabilities.split(",")] if capabilities else None

    client = ArcoaClient(agent_id="", private_key=private_key, api_url=api_url)

    async def _register():
        return await client.register(
            public_key=public_key,
            display_name=name,
            description=description,
            capabilities=caps,
            registration_token=token,
            hosting_mode="websocket",
        )

    result = asyncio.run(_register())
    agent_id = result["agent_id"]

    config = {
        "agent_id": agent_id,
        "private_key": private_key,
        "public_key": public_key,
        "api_url": api_url,
        "display_name": name,
    }
    save_config(config)

    click.echo(f"Agent registered: {name} (agent_id: {agent_id})")
    click.echo("Config saved to ~/.arcoa/config.json")


@cli.command()
def connect():
    """Connect to the marketplace and listen for events."""
    try:
        config = load_config()
    except ArcoaConfigError as e:
        raise click.ClickException(str(e))

    from . import ArcoaAgent

    agent = ArcoaAgent(
        agent_id=config["agent_id"],
        private_key=config["private_key"],
        api_url=config.get("api_url", "https://api.staging.arcoa.ai"),
    )

    click.echo(f"Connecting as {config.get('display_name', config['agent_id'])}...")

    async def _connect():
        try:
            await agent.connect()
        except asyncio.CancelledError:
            pass
        finally:
            await agent.disconnect()

    try:
        asyncio.run(_connect())
    except KeyboardInterrupt:
        click.echo("\nDisconnected.")


@cli.command()
def status():
    """Show agent status, balance, and reputation."""
    try:
        config = load_config()
    except ArcoaConfigError as e:
        raise click.ClickException(str(e))

    client = ArcoaClient(
        agent_id=config["agent_id"],
        private_key=config["private_key"],
        api_url=config.get("api_url", "https://api.staging.arcoa.ai"),
    )

    async def _status():
        balance = await client.get_balance()
        reputation = await client.get_reputation(config["agent_id"])
        return balance, reputation

    balance, reputation = asyncio.run(_status())

    click.echo(f"Agent: {config.get('display_name', 'Unknown')}")
    click.echo(f"ID: {config['agent_id']}")
    click.echo(f"Balance: {balance.get('balance', 'N/A')} credits")
    seller = reputation.get("seller_rating", "N/A")
    client_r = reputation.get("client_rating", "N/A")
    click.echo(f"Reputation: {seller} (seller) / {client_r} (client)")


@cli.command()
@click.option("--skill", default=None, help="Filter by skill ID")
@click.option("--online", is_flag=True, default=False, help="Only show online agents")
@click.option("--min-rating", type=float, default=None, help="Minimum rating")
@click.option("--max-price", type=float, default=None, help="Maximum price")
@click.option("--limit", type=int, default=20, help="Max results")
def discover(skill: str | None, online: bool, min_rating: float | None, max_price: float | None, limit: int):
    """Discover agents on the marketplace."""
    try:
        config = load_config()
    except ArcoaConfigError as e:
        raise click.ClickException(str(e))

    client = ArcoaClient(
        agent_id=config["agent_id"],
        private_key=config["private_key"],
        api_url=config.get("api_url", "https://api.staging.arcoa.ai"),
    )

    async def _discover():
        return await client.discover(
            skill_id=skill,
            min_rating=min_rating,
            max_price=max_price,
            online=online if online else None,
            limit=limit,
        )

    results = asyncio.run(_discover())

    if not results:
        click.echo("No agents found.")
        return

    click.echo(f"Found {len(results)} agents:")
    for agent in results:
        name = agent.get("display_name", "Unknown")
        rating = agent.get("rating", "N/A")
        price = agent.get("base_price", "N/A")
        price_model = agent.get("price_model", "")
        caps = ", ".join(agent.get("capabilities", []))
        click.echo(f"  {name} ({rating}*) -- {price_model} ${price} -- {caps}")
