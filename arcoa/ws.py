import asyncio
import json
import logging
import secrets
from collections.abc import Callable
from datetime import datetime, UTC

import websockets

from .auth import build_signature_message
from .exceptions import ArcoaWebSocketError
from nacl.signing import SigningKey
from nacl.encoding import HexEncoder

logger = logging.getLogger(__name__)


class ArcoaWebSocket:
    def __init__(self, agent_id: str, private_key: str, api_url: str):
        self.agent_id = agent_id
        self.private_key = private_key
        self.api_url = api_url
        self._handlers: dict[str, list[Callable]] = {}
        self._ws = None
        self._running = False
        self._listen_task: asyncio.Task | None = None

    @property
    def _ws_url(self) -> str:
        url = self.api_url.rstrip("/")
        if url.startswith("https://"):
            url = "wss://" + url[len("https://"):]
        elif url.startswith("http://"):
            url = "ws://" + url[len("http://"):]
        return url + "/ws/agent"

    def on(self, event_type: str) -> Callable:
        """Decorator to register event handlers."""
        def decorator(func: Callable) -> Callable:
            self._handlers.setdefault(event_type, []).append(func)
            return func
        return decorator

    async def connect(self) -> None:
        """Connect, authenticate, start listening. Reconnects on failure."""
        self._running = True
        backoff = 1
        while self._running:
            try:
                ws = await websockets.connect(self._ws_url)
                self._ws = ws
                await self._auth(ws)
                backoff = 1  # reset on successful connect
                await self._listen(ws)
            except Exception as e:
                if not self._running:
                    break
                logger.warning(f"WebSocket connection failed: {e}. Reconnecting in {backoff}s...")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)

    async def disconnect(self) -> None:
        """Gracefully disconnect."""
        self._running = False
        if self._ws:
            await self._ws.close()
            self._ws = None

    async def _auth(self, ws) -> None:
        """Send auth message after connecting."""
        timestamp = datetime.now(UTC).isoformat()
        signing_key = SigningKey(self.private_key.encode(), encoder=HexEncoder)
        message = build_signature_message(timestamp, "WS", "/ws/agent", b"")
        signed = signing_key.sign(message, encoder=HexEncoder)

        auth_msg = {
            "type": "auth",
            "agent_id": self.agent_id,
            "timestamp": timestamp,
            "signature": signed.signature.decode(),
            "nonce": secrets.token_hex(16),
        }
        await ws.send(json.dumps(auth_msg))

        response = await ws.recv()
        data = json.loads(response)
        if data.get("type") == "error":
            raise ArcoaWebSocketError(f"Auth failed: {data.get('detail', 'unknown error')}")
        if data.get("type") != "auth_ok":
            raise ArcoaWebSocketError(f"Unexpected auth response: {data}")

    async def _listen(self, ws) -> None:
        """Main loop: handle pings and dispatch events."""
        try:
            async for raw in ws:
                data = json.loads(raw)
                msg_type = data.get("type")

                if msg_type == "ping":
                    await ws.send(json.dumps({"type": "pong"}))
                elif msg_type == "event":
                    event_type = data.get("event_type", "")
                    payload = data.get("payload", {})
                    handlers = self._handlers.get(event_type, [])
                    for handler in handlers:
                        try:
                            result = handler(payload)
                            if asyncio.iscoroutine(result):
                                await result
                        except Exception:
                            logger.exception(f"Error in handler for {event_type}")
                elif msg_type == "error":
                    logger.error(f"Server error: {data.get('detail', '')}")
        except websockets.ConnectionClosed:
            logger.info("WebSocket connection closed")
        except Exception as e:
            if self._running:
                logger.warning(f"WebSocket listen error: {e}")
