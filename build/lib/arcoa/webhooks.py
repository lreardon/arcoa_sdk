"""Webhook signature verification helpers."""

from __future__ import annotations

import hashlib
import hmac
import time


def verify_signature(secret: str, timestamp: str, body: str, signature: str) -> bool:
    """Verify an HMAC-SHA256 webhook signature.

    Computes HMAC-SHA256 of ``'{timestamp}.{body}'`` keyed with *secret*
    and compares to *signature* using constant-time comparison.
    """
    expected = hmac.new(secret.encode(), f"{timestamp}.{body}".encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def verify_webhook(secret: str, headers: dict, body: str, max_age_seconds: int = 300) -> bool:
    """Verify a webhook request's signature and freshness.

    Parameters
    ----------
    secret:
        The shared webhook secret.
    headers:
        Request headers (case-insensitive lookup supported).
    body:
        Raw request body as a string.
    max_age_seconds:
        Maximum allowed age of the timestamp (default 300s / 5 min).

    Returns ``True`` only if the signature is valid *and* the timestamp
    is within *max_age_seconds* of the current time.
    """
    # Normalise header keys to lowercase for case-insensitive lookup
    lower_headers = {k.lower(): v for k, v in headers.items()}
    signature = lower_headers.get("x-webhook-signature")
    timestamp = lower_headers.get("x-webhook-timestamp")

    if not signature or not timestamp:
        return False

    # Verify timestamp freshness
    try:
        ts = int(timestamp)
    except (ValueError, TypeError):
        return False

    if abs(time.time() - ts) > max_age_seconds:
        return False

    return verify_signature(secret, timestamp, body, signature)
