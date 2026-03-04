"""Tests for webhook signature verification."""

import hashlib
import hmac
import time

import pytest

from arcoa.webhooks import verify_signature, verify_webhook


def _sign(secret: str, timestamp: str, body: str) -> str:
    """Produce a valid HMAC-SHA256 signature."""
    return hmac.new(secret.encode(), f"{timestamp}.{body}".encode(), hashlib.sha256).hexdigest()


class TestVerifySignature:
    def test_valid_signature(self):
        secret = "s3cret"
        ts = "1700000000"
        body = '{"event":"job.completed"}'
        sig = _sign(secret, ts, body)
        assert verify_signature(secret, ts, body, sig) is True

    def test_invalid_signature(self):
        assert verify_signature("secret", "123", "body", "badsig") is False

    def test_wrong_secret(self):
        ts = "123"
        body = "hello"
        sig = _sign("correct", ts, body)
        assert verify_signature("wrong", ts, body, sig) is False

    def test_tampered_body(self):
        secret = "k"
        ts = "1"
        sig = _sign(secret, ts, "original")
        assert verify_signature(secret, ts, "tampered", sig) is False


class TestVerifyWebhook:
    def test_valid_webhook(self):
        secret = "webhook_secret_123"
        ts = str(int(time.time()))
        body = '{"event":"job.completed","job_id":"abc"}'
        sig = _sign(secret, ts, body)
        headers = {
            "X-Webhook-Signature": sig,
            "X-Webhook-Timestamp": ts,
        }
        assert verify_webhook(secret, headers, body) is True

    def test_case_insensitive_headers(self):
        secret = "s"
        ts = str(int(time.time()))
        body = "{}"
        sig = _sign(secret, ts, body)
        headers = {
            "x-webhook-signature": sig,
            "x-webhook-timestamp": ts,
        }
        assert verify_webhook(secret, headers, body) is True

    def test_replay_protection_expired(self):
        secret = "s"
        old_ts = str(int(time.time()) - 600)  # 10 minutes ago
        body = "{}"
        sig = _sign(secret, old_ts, body)
        headers = {
            "X-Webhook-Signature": sig,
            "X-Webhook-Timestamp": old_ts,
        }
        assert verify_webhook(secret, headers, body, max_age_seconds=300) is False

    def test_replay_protection_custom_max_age(self):
        secret = "s"
        ts = str(int(time.time()) - 10)
        body = "{}"
        sig = _sign(secret, ts, body)
        headers = {
            "X-Webhook-Signature": sig,
            "X-Webhook-Timestamp": ts,
        }
        # 10 seconds old, but max_age is 5 — should fail
        assert verify_webhook(secret, headers, body, max_age_seconds=5) is False
        # 10 seconds old, but max_age is 60 — should pass
        assert verify_webhook(secret, headers, body, max_age_seconds=60) is True

    def test_missing_signature_header(self):
        headers = {"X-Webhook-Timestamp": str(int(time.time()))}
        assert verify_webhook("s", headers, "{}") is False

    def test_missing_timestamp_header(self):
        headers = {"X-Webhook-Signature": "abc"}
        assert verify_webhook("s", headers, "{}") is False

    def test_invalid_timestamp(self):
        headers = {
            "X-Webhook-Signature": "abc",
            "X-Webhook-Timestamp": "not-a-number",
        }
        assert verify_webhook("s", headers, "{}") is False
