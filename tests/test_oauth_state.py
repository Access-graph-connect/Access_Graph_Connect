import time
import uuid

import pytest

from app.security.oauth_state import InvalidStateError, sign_state, verify_state


def test_state_round_trip() -> None:
    tenant_id = uuid.uuid4()
    assert verify_state(sign_state(tenant_id)) == tenant_id


def test_tampered_state_rejected() -> None:
    state = sign_state(uuid.uuid4())
    payload_b64, _ = state.split(".", 1)
    forged = f"{payload_b64}.{'A' * 43}"
    with pytest.raises(InvalidStateError):
        verify_state(forged)


def test_expired_state_rejected() -> None:
    state = sign_state(uuid.uuid4())
    with pytest.raises(InvalidStateError):
        verify_state(state, max_age_seconds=-1)


def test_malformed_state_rejected() -> None:
    with pytest.raises(InvalidStateError):
        verify_state("not-a-state")
