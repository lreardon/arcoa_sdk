import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from arcoa.auth import generate_keypair, build_signature_message
from arcoa.ws import ArcoaWebSocket
from arcoa.exceptions import ArcoaWebSocketError
from nacl.signing import VerifyKey
from nacl.encoding import HexEncoder


@pytest.fixture
def keys():
    return generate_keypair()


@pytest.fixture
def ws(keys):
    return ArcoaWebSocket("test-agent", keys[0], "https://api.staging.arcoa.ai")


class TestWSUrl:
    def test_https_to_wss(self, ws):
        assert ws._ws_url == "wss://api.staging.arcoa.ai/ws/agent"

    def test_http_to_ws(self, keys):
        ws = ArcoaWebSocket("a", keys[0], "http://localhost:8000")
        assert ws._ws_url == "ws://localhost:8000/ws/agent"

    def test_trailing_slash_stripped(self, keys):
        ws = ArcoaWebSocket("a", keys[0], "https://api.example.com/")
        assert ws._ws_url == "wss://api.example.com/ws/agent"


class TestEventHandlers:
    def test_register_handler(self, ws):
        @ws.on("job.proposed")
        def handler(payload):
            pass

        assert "job.proposed" in ws._handlers
        assert handler in ws._handlers["job.proposed"]

    def test_multiple_handlers(self, ws):
        @ws.on("job.proposed")
        def h1(payload):
            pass

        @ws.on("job.proposed")
        def h2(payload):
            pass

        assert len(ws._handlers["job.proposed"]) == 2

    def test_decorator_returns_original(self, ws):
        def my_func(payload):
            return "result"

        decorated = ws.on("test")(my_func)
        assert decorated is my_func


class TestAuth:
    async def test_auth_message_format(self, ws, keys):
        sent_messages = []

        mock_ws = AsyncMock()
        mock_ws.send = AsyncMock(side_effect=lambda m: sent_messages.append(m))
        mock_ws.recv = AsyncMock(return_value=json.dumps({"type": "auth_ok", "agent_id": "test-agent"}))

        await ws._auth(mock_ws)

        assert len(sent_messages) == 1
        msg = json.loads(sent_messages[0])
        assert msg["type"] == "auth"
        assert msg["agent_id"] == "test-agent"
        assert "timestamp" in msg
        assert "signature" in msg
        assert "nonce" in msg

    async def test_auth_signature_valid(self, ws, keys):
        sent_messages = []
        mock_ws = AsyncMock()
        mock_ws.send = AsyncMock(side_effect=lambda m: sent_messages.append(m))
        mock_ws.recv = AsyncMock(return_value=json.dumps({"type": "auth_ok", "agent_id": "test-agent"}))

        await ws._auth(mock_ws)

        msg = json.loads(sent_messages[0])
        vk = VerifyKey(keys[1].encode(), encoder=HexEncoder)
        message = build_signature_message(msg["timestamp"], "WS", "/ws/agent", b"")
        signature = bytes.fromhex(msg["signature"])
        vk.verify(message, signature)  # Should not raise

    async def test_auth_failure_raises(self, ws):
        mock_ws = AsyncMock()
        mock_ws.send = AsyncMock()
        mock_ws.recv = AsyncMock(return_value=json.dumps({"type": "error", "detail": "Invalid signature"}))

        with pytest.raises(ArcoaWebSocketError, match="Auth failed"):
            await ws._auth(mock_ws)


class TestListen:
    async def test_ping_pong(self, ws):
        sent = []
        mock_ws = AsyncMock()
        mock_ws.send = AsyncMock(side_effect=lambda m: sent.append(m))
        mock_ws.__aiter__ = lambda self: self
        messages = [json.dumps({"type": "ping"})]
        _iter = iter(messages)

        async def _anext(self):
            try:
                return next(_iter)
            except StopIteration:
                raise StopAsyncIteration

        mock_ws.__anext__ = _anext

        await ws._listen(mock_ws)
        assert len(sent) == 1
        assert json.loads(sent[0]) == {"type": "pong"}

    async def test_event_dispatch(self, ws):
        received = []

        @ws.on("job.proposed")
        def handler(payload):
            received.append(payload)

        mock_ws = AsyncMock()
        messages = [json.dumps({"type": "event", "event_type": "job.proposed", "payload": {"job_id": "j1"}})]
        _iter = iter(messages)

        async def _aiter(self):
            for m in messages:
                yield m

        mock_ws.__aiter__ = _aiter

        await ws._listen(mock_ws)
        assert len(received) == 1
        assert received[0]["job_id"] == "j1"

    async def test_async_event_handler(self, ws):
        received = []

        @ws.on("job.completed")
        async def handler(payload):
            received.append(payload)

        messages = [json.dumps({"type": "event", "event_type": "job.completed", "payload": {"id": "1"}})]
        mock_ws = AsyncMock()

        async def _aiter(self):
            for m in messages:
                yield m

        mock_ws.__aiter__ = _aiter

        await ws._listen(mock_ws)
        assert len(received) == 1

    async def test_unknown_event_ignored(self, ws):
        """Events with no handler should be silently ignored."""
        messages = [json.dumps({"type": "event", "event_type": "unknown.event", "payload": {}})]
        mock_ws = AsyncMock()

        async def _aiter(self):
            for m in messages:
                yield m

        mock_ws.__aiter__ = _aiter

        # Should not raise
        await ws._listen(mock_ws)


class TestReconnect:
    async def test_reconnect_backoff(self, ws):
        connect_count = 0
        backoff_sleeps = []

        async def mock_connect(url):
            nonlocal connect_count
            connect_count += 1
            if connect_count <= 3:
                raise ConnectionError("fail")
            # On 4th call, stop the loop
            ws._running = False
            raise ConnectionError("final")

        original_sleep = asyncio.sleep

        async def mock_sleep(duration):
            backoff_sleeps.append(duration)

        with patch("websockets.connect", side_effect=mock_connect):
            with patch("asyncio.sleep", side_effect=mock_sleep):
                await ws.connect()

        # 3 failures → 3 sleeps with exponential backoff (4th sets _running=False and exits)
        assert backoff_sleeps == [1, 2, 4]

    async def test_disconnect_stops_reconnect(self, ws):
        connect_called = False

        async def mock_connect(url):
            nonlocal connect_called
            connect_called = True
            await ws.disconnect()
            raise ConnectionError("should stop")

        with patch("websockets.connect", side_effect=mock_connect):
            await ws.connect()

        assert connect_called
        assert not ws._running
