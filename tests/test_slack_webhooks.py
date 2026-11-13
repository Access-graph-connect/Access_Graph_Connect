import hashlib
import hmac
import json
import time

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.db.models import WebhookInbox
from app.db.session import session_scope
from app.main import app
from app.enums import Provider
from sqlalchemy import func, select

client = TestClient(app)
SECRET = "slack-test-signing-secret"


@pytest.fixture(autouse=True)
def slack_signing_secret(monkeypatch):
    monkeypatch.setenv("SLACK_SIGNING_SECRET", SECRET)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _signature(body: bytes, timestamp: str) -> str:
    base = b"v0:" + timestamp.encode() + b":" + body
    digest = hmac.new(SECRET.encode(), base, hashlib.sha256).hexdigest()
    return "v0=" + digest


def _post(payload: dict, event_timestamp: str | None = None):
    body = json.dumps(payload).encode()
    timestamp = event_timestamp or str(int(time.time()))
    return client.post(
        "/webhooks/slack",
        content=body,
        headers={
            "X-Slack-Request-Timestamp": timestamp,
            "X-Slack-Signature": _signature(body, timestamp),
        },
    )


def test_url_verification_returns_challenge() -> None:
    response = _post({"type": "url_verification", "challenge": "challenge-value"})
    assert response.status_code == 200
    assert response.json() == {"challenge": "challenge-value"}


def test_event_callback_is_verified_and_deduplicated() -> None:
    payload = {
        "type": "event_callback",
        "event_id": "Ev-slack-test-1",
        "team_id": "T-no-installed-connection",
        "event": {"type": "member_joined_channel"},
    }

    first = _post(payload)
    second = _post(payload)

    assert first.status_code == 200
    assert first.json()["status"] == "received"
    assert second.status_code == 200
    assert second.json()["status"] == "duplicate"
    with session_scope() as db:
        count = db.scalar(
            select(func.count())
            .select_from(WebhookInbox)
            .where(
                WebhookInbox.provider == Provider.SLACK,
                WebhookInbox.delivery_id == "Ev-slack-test-1",
            )
        )
        assert count == 1


def test_invalid_or_expired_slack_signature_rejected() -> None:
    body = json.dumps(
        {"type": "event_callback", "event_id": "Ev-slack-expired"}
    ).encode()
    old_timestamp = str(int(time.time()) - 301)
    response = client.post(
        "/webhooks/slack",
        content=body,
        headers={
            "X-Slack-Request-Timestamp": old_timestamp,
            "X-Slack-Signature": _signature(body, old_timestamp),
        },
    )
    assert response.status_code == 401
