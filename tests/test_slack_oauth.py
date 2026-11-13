from urllib.parse import parse_qs, urlparse
import uuid
from types import SimpleNamespace

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import get_settings
from app.db.models import CredentialVault, ProviderConnection
from app.db.session import session_scope
from app.enums import Provider
from app.main import app
from app.security.credentials import retrieve_token
from app.sync.service import _build_connector

client = TestClient(app)


def test_slack_oauth_installs_connection_with_encrypted_token(monkeypatch) -> None:
    monkeypatch.setenv("SLACK_CLIENT_ID", "client-id")
    monkeypatch.setenv("SLACK_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv(
        "SLACK_REDIRECT_URI", "http://localhost:8000/connections/slack/callback"
    )
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    get_settings.cache_clear()
    tenant_id = uuid.uuid4()

    from app.api.routes import slack

    monkeypatch.setattr(
        slack,
        "exchange_oauth_code",
        lambda settings, code: {
            "ok": True,
            "access_token": "xoxb-test-token",
            "scope": "users:read,channels:read,groups:read",
            "team": {"id": "T-slack-test", "name": "Test workspace"},
        },
    )

    try:
        started = client.post(
            "/connections/slack/start", headers={"X-Tenant-ID": str(tenant_id)}
        )
        assert started.status_code == 200
        authorize_url = urlparse(started.json()["authorize_url"])
        query = parse_qs(authorize_url.query)
        assert authorize_url.netloc == "slack.com"
        assert query["client_id"] == ["client-id"]
        assert "users:read" in query["scope"][0].split(",")

        callback = client.get(
            "/connections/slack/callback",
            params={"state": started.json()["state"], "code": "oauth-code"},
        )
        assert callback.status_code == 200
        body = callback.json()
        assert body["provider"] == "slack"
        assert body["external_workspace_id"] == "T-slack-test"
        assert "credential_ref" not in body
        assert "access_token" not in body

        with session_scope() as db:
            connection = db.scalar(
                select(ProviderConnection).where(
                    ProviderConnection.tenant_id == tenant_id,
                    ProviderConnection.provider == Provider.SLACK,
                    ProviderConnection.external_workspace_id == "T-slack-test",
                )
            )
            assert connection is not None
            vault_entry = db.get(
                CredentialVault, uuid.UUID(connection.credential_ref)
            )
            assert vault_entry is not None
            assert vault_entry.encrypted is True
            assert "xoxb-test-token" not in vault_entry.ciphertext
            connector = _build_connector(
                SimpleNamespace(
                    provider=Provider.SLACK,
                    credential_ref=str(vault_entry.id),
                ),
                db,
            )
            assert connector._token == retrieve_token(db, str(vault_entry.id))
    finally:
        get_settings.cache_clear()
