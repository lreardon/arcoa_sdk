import hashlib
import secrets
from datetime import datetime, UTC

from nacl.signing import SigningKey
from nacl.encoding import HexEncoder


def build_signature_message(timestamp: str, method: str, path: str, body: bytes) -> bytes:
    body_hash = hashlib.sha256(body).hexdigest()
    message = f"{timestamp}\n{method}\n{path}\n{body_hash}"
    return message.encode()


def sign_request(agent_id: str, private_key_hex: str, method: str, path: str, body: bytes = b"") -> dict:
    """Returns dict with Authorization, X-Timestamp, X-Nonce headers."""
    timestamp = datetime.now(UTC).isoformat()
    signing_key = SigningKey(private_key_hex.encode(), encoder=HexEncoder)
    message = build_signature_message(timestamp, method, path, body)
    signed = signing_key.sign(message, encoder=HexEncoder)
    return {
        "Authorization": f"AgentSig {agent_id}:{signed.signature.decode()}",
        "X-Timestamp": timestamp,
        "X-Nonce": secrets.token_hex(16),
    }


def generate_keypair() -> tuple[str, str]:
    """Returns (private_key_hex, public_key_hex)."""
    sk = SigningKey.generate()
    return (
        sk.encode(encoder=HexEncoder).decode(),
        sk.verify_key.encode(encoder=HexEncoder).decode(),
    )
