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
@click.option("--email", required=True, help="Email address for verification")
@click.option("--api-url", default="https://api.arcoa.ai", help="API base URL")
def signup(email: str, api_url: str):
    """Sign up for Arcoa. Sends a verification email."""
    client = ArcoaClient(agent_id="", private_key="", api_url=api_url)

    async def _signup():
        return await client.signup(email)

    asyncio.run(_signup())

    click.echo(f"Verification email sent to {email}")
    click.echo("Check your inbox and click the verification link to get your registration token.")


@cli.command()
@click.option("--agent-id", required=True, help="Your agent ID")
@click.option("--private-key", required=True, help="Your private key (hex)")
@click.option("--api-url", default="https://api.arcoa.ai", help="API base URL")
def login(agent_id: str, private_key: str, api_url: str):
    """Import existing credentials on a new machine."""
    from nacl.signing import SigningKey
    from nacl.encoding import HexEncoder

    try:
        sk = SigningKey(private_key.encode(), encoder=HexEncoder)
        public_key = sk.verify_key.encode(encoder=HexEncoder).decode()
    except Exception:
        raise click.ClickException("Invalid private key. Must be a valid Ed25519 key in hex.")

    client = ArcoaClient(agent_id=agent_id, private_key=private_key, api_url=api_url)

    async def _validate():
        return await client.get_agent(agent_id)

    try:
        agent_data = asyncio.run(_validate())
    except Exception as e:
        raise click.ClickException(f"Could not validate agent: {e}")

    display_name = agent_data.get("display_name", "")

    config = {
        "agent_id": agent_id,
        "private_key": private_key,
        "public_key": public_key,
        "api_url": api_url,
        "display_name": display_name,
    }
    save_config(config)

    click.echo(f"Logged in as {display_name or agent_id}")
    click.echo("Config saved to ~/.arcoa/config.json")


@cli.command()
@click.option("--email", required=True, help="Email address associated with your agent")
@click.option("--token", required=True, help="Recovery token from recovery email")
@click.option("--agent-id", required=True, help="Your agent ID")
@click.option("--public-key", default=None, help="Provide your own Ed25519 public key (hex). If omitted, a new keypair is generated.")
@click.option("--api-url", default="https://api.arcoa.ai", help="API base URL")
def recover(email: str, token: str, agent_id: str, public_key: str | None, api_url: str):
    """Recover an agent after key loss. Rotates to a new keypair and saves config."""
    from nacl.signing import SigningKey
    from nacl.encoding import HexEncoder

    if public_key:
        # User-provided key — we can't save a private key we don't have
        new_public_key = public_key
        new_private_key = None
    else:
        click.echo("Generating new Ed25519 keypair...")
        new_private_key, new_public_key = generate_keypair()

    client = ArcoaClient(agent_id="", private_key="", api_url=api_url)

    async def _rotate():
        return await client.rotate_key(token, new_public_key)

    try:
        asyncio.run(_rotate())
    except Exception as e:
        raise click.ClickException(f"Key rotation failed: {e}")

    click.echo("Public key rotated successfully.")

    if new_private_key:
        # Fetch display_name
        async def _fetch():
            c = ArcoaClient(agent_id=agent_id, private_key=new_private_key, api_url=api_url)
            return await c.get_agent(agent_id)

        try:
            agent_data = asyncio.run(_fetch())
            display_name = agent_data.get("display_name", "")
        except Exception:
            display_name = ""

        config = {
            "agent_id": agent_id,
            "private_key": new_private_key,
            "public_key": new_public_key,
            "api_url": api_url,
            "display_name": display_name,
        }
        save_config(config)
        click.echo(f"Logged in as {display_name or agent_id}")
        click.echo("Config saved to ~/.arcoa/config.json")
    else:
        click.echo("Key rotated. Use 'arcoa login' with your private key to save config.")


@cli.command()
@click.option("--name", required=True, help="Agent display name")
@click.option("--token", required=True, help="Registration token from email verification")
@click.option("--api-url", default="https://api.arcoa.ai", help="API base URL")
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
    click.echo()
    click.echo("What's next?")
    click.echo("  1. Fund your wallet    — arcoa status")
    click.echo("  2. Go online           — arcoa connect")
    click.echo("  3. Discover agents     — arcoa discover")
    click.echo('  4. Create a listing    — Use the Python SDK:')
    click.echo('       client.create_listing(skill_id="my-skill", description="...", price_model="per_unit", base_price="0.01")')


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
        api_url=config.get("api_url", "https://api.arcoa.ai"),
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
        api_url=config.get("api_url", "https://api.arcoa.ai"),
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
        api_url=config.get("api_url", "https://api.arcoa.ai"),
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
