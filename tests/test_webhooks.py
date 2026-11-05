import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app

client = TestClient(app)

SECRET = "test-webhook-secret"


@pytest.fixture(autouse=True)
def webhook_secret(monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", SECRET)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _signature(body: bytes) -> str:
    return "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()


def _post(body: dict, delivery_id: str, signature: str | None = None):
    raw = json.dumps(body).encode()
    headers = {"X-GitHub-Delivery": delivery_id, "X-GitHub-Event": "push"}
    if signature is not None:
        headers["X-Hub-Signature-256"] = signature
    return client.post("/webhooks/github", content=raw, headers=headers)


def test_valid_signature_accepted() -> None:
    body = {"zen": "keep it logically awesome"}
    raw = json.dumps(body).encode()
    response = _post(body, "delivery-1", signature=_signature(raw))
    assert response.status_code == 200
    assert response.json()["status"] == "received"


def test_invalid_signature_rejected_and_changes_no_state() -> None:
    body = {"zen": "keep it logically awesome"}
    response = _post(body, "delivery-2", signature="sha256=deadbeef")
    assert response.status_code == 401

    # Nothing was recorded for this delivery.
    from app.db.models import WebhookInbox
    from app.db.session import session_scope
    from sqlalchemy import select

    with session_scope() as db:
        row = db.scalar(
            select(WebhookInbox).where(WebhookInbox.delivery_id == "delivery-2")
        )
        assert row is None


def test_missing_signature_rejected() -> None:
    response = _post({"zen": "x"}, "delivery-3", signature=None)
    assert response.status_code == 401


def test_missing_delivery_id_rejected() -> None:
    raw = json.dumps({"zen": "x"}).encode()
    response = client.post(
        "/webhooks/github",
        content=raw,
        headers={"X-Hub-Signature-256": _signature(raw)},
    )
    assert response.status_code == 400


def test_replay_processed_at_most_once() -> None:
    body = {"zen": "replayed"}
    raw = json.dumps(body).encode()
    sig = _signature(raw)

    first = _post(body, "delivery-dup", signature=sig)
    assert first.status_code == 200
    assert first.json()["status"] == "received"

    second = _post(body, "delivery-dup", signature=sig)
    assert second.status_code == 200
    assert second.json()["status"] == "duplicate"

    from app.db.models import WebhookInbox
    from app.db.session import session_scope
    from sqlalchemy import func, select

    with session_scope() as db:
        count = db.scalar(
            select(func.count())
            .select_from(WebhookInbox)
            .where(WebhookInbox.delivery_id == "delivery-dup")
        )
        assert count == 1
