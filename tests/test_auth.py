import hashlib

from nacl.signing import SigningKey, VerifyKey
from nacl.encoding import HexEncoder

from arcoa.auth import generate_keypair, sign_request, build_signature_message


class TestGenerateKeypair:
    def test_returns_hex_strings(self):
        private_key, public_key = generate_keypair()
        assert isinstance(private_key, str)
        assert isinstance(public_key, str)
        # Both should be valid hex
        bytes.fromhex(private_key)
        bytes.fromhex(public_key)

    def test_keys_are_valid_ed25519(self):
        private_key, public_key = generate_keypair()
        sk = SigningKey(private_key.encode(), encoder=HexEncoder)
        vk = VerifyKey(public_key.encode(), encoder=HexEncoder)
        # The signing key's verify key should match
        assert sk.verify_key.encode(encoder=HexEncoder) == vk.encode(encoder=HexEncoder)

    def test_generates_unique_keys(self):
        k1 = generate_keypair()
        k2 = generate_keypair()
        assert k1[0] != k2[0]
        assert k1[1] != k2[1]


class TestBuildSignatureMessage:
    def test_format(self):
        msg = build_signature_message("2024-01-01T00:00:00", "GET", "/test", b"")
        expected_hash = hashlib.sha256(b"").hexdigest()
        expected = f"2024-01-01T00:00:00\nGET\n/test\n{expected_hash}"
        assert msg == expected.encode()

    def test_body_hash_changes_with_body(self):
        msg_empty = build_signature_message("ts", "POST", "/p", b"")
        msg_body = build_signature_message("ts", "POST", "/p", b'{"key":"val"}')
        assert msg_empty != msg_body

    def test_returns_bytes(self):
        msg = build_signature_message("ts", "GET", "/", b"")
        assert isinstance(msg, bytes)


class TestSignRequest:
    def test_returns_required_headers(self):
        private_key, _ = generate_keypair()
        headers = sign_request("agent-123", private_key, "GET", "/test")
        assert "Authorization" in headers
        assert "X-Timestamp" in headers
        assert "X-Nonce" in headers

    def test_authorization_format(self):
        private_key, _ = generate_keypair()
        headers = sign_request("agent-123", private_key, "GET", "/test")
        assert headers["Authorization"].startswith("AgentSig agent-123:")
        sig_hex = headers["Authorization"].split(":")[1]
        bytes.fromhex(sig_hex)

    def test_signature_is_verifiable(self):
        private_key, public_key = generate_keypair()
        headers = sign_request("agent-123", private_key, "POST", "/data", b'{"x":1}')
        sig_hex = headers["Authorization"].split(":")[1]
        timestamp = headers["X-Timestamp"]

        vk = VerifyKey(public_key.encode(), encoder=HexEncoder)
        message = build_signature_message(timestamp, "POST", "/data", b'{"x":1}')
        signature = bytes.fromhex(sig_hex)
        # Should not raise
        vk.verify(message, signature)

    def test_nonce_is_unique(self):
        private_key, _ = generate_keypair()
        h1 = sign_request("a", private_key, "GET", "/")
        h2 = sign_request("a", private_key, "GET", "/")
        assert h1["X-Nonce"] != h2["X-Nonce"]
