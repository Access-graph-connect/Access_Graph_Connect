"""Slack request signature verification with a five-minute replay window."""

import hashlib
import hmac
import time

_MAX_AGE_SECONDS = 300


def verify_slack_signature(
    secret: str,
    body: bytes,
    signature: str | None,
    timestamp: str | None,
    now: float | None = None,
) -> bool:
    if not secret or not signature or not timestamp:
        return False
    try:
        request_time = int(timestamp)
    except ValueError:
        return False
    if abs((time.time() if now is None else now) - request_time) > _MAX_AGE_SECONDS:
        return False
    base = b"v0:" + timestamp.encode() + b":" + body
    expected = "v0=" + hmac.new(
        secret.encode(), base, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)
