"""HMAC-signed OAuth/installation state tokens.

State binds an installation redirect to a tenant and expires quickly, so
callbacks cannot be forged or replayed across tenants.
"""

import base64
import hashlib
import hmac
import json
import time
import uuid

from app.config import get_settings

_MAX_AGE_SECONDS = 600


class InvalidStateError(ValueError):
    pass


def _signature(payload_b64: str) -> str:
    key = get_settings().secret_key.encode()
    digest = hmac.new(key, payload_b64.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def sign_state(tenant_id: uuid.UUID) -> str:
    payload = {"tid": str(tenant_id), "iat": int(time.time())}
    payload_b64 = (
        base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    )
    return f"{payload_b64}.{_signature(payload_b64)}"


def verify_state(state: str, max_age_seconds: int = _MAX_AGE_SECONDS) -> uuid.UUID:
    try:
        payload_b64, sig = state.split(".", 1)
    except ValueError as exc:
        raise InvalidStateError("malformed state") from exc
    if not hmac.compare_digest(sig, _signature(payload_b64)):
        raise InvalidStateError("bad state signature")
    try:
        payload = json.loads(base64.urlsafe_b64decode(payload_b64 + "=="))
        issued_at = int(payload["iat"])
        tenant_id = uuid.UUID(payload["tid"])
    except Exception as exc:
        raise InvalidStateError("undecodable state") from exc
    if time.time() - issued_at > max_age_seconds:
        raise InvalidStateError("expired state")
    return tenant_id
