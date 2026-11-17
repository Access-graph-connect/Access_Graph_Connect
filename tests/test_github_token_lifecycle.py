import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from cryptography.fernet import Fernet

from app.api.routes.github import github_callback
from app.config import get_settings
from app.connectors.errors import AuthError
from app.db.models import ProviderConnection, Tenant
from app.db.session import session_scope
from app.enums import ConnectionStatus, Provider
from app.security.credentials import CredentialError, retrieve_token, store_token
from app.security.github_app import parse_token_expiry
from app.security.oauth_state import sign_state
from app.sync import service


def _seed_github_connection(expires_at: datetime | None) -> tuple[uuid.UUID, str]:
    with session_scope() as db:
        tenant = Tenant(name=f"github-token-{uuid.uuid4().hex}")
        db.add(tenant)
        db.flush()
        connection = ProviderConnection(
            tenant_id=tenant.id,
            provider=Provider.GITHUB,
            external_workspace_id="12345",
            status=ConnectionStatus.ACTIVE,
            credential_expires_at=expires_at,
        )
        db.add(connection)
        db.flush()
        connection.credential_ref = store_token(db, "old-installation-token")
        return connection.id, connection.credential_ref


def test_github_token_is_renewed_before_expiry(monkeypatch) -> None:
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", key)
    get_settings.cache_clear()
    connection_id, old_ref = _seed_github_connection(
        datetime.now(UTC) + timedelta(minutes=4)
    )
    renewed_expiry = datetime.now(UTC) + timedelta(hours=1)
    calls: list[int] = []

    def exchange(_settings, installation_id):
        calls.append(installation_id)
        return {
            "token": "new-installation-token",
            "expires_at": renewed_expiry.isoformat(),
        }

    monkeypatch.setattr(service, "exchange_installation_token", exchange)
    try:
        with session_scope() as db:
            connection = db.get(ProviderConnection, connection_id)
            connector = service._build_connector(connection, db)
            new_ref = connection.credential_ref
            saved_expiry = connection.credential_expires_at

        assert calls == [12345]
        assert connector._token == "new-installation-token"
        assert new_ref != old_ref
        assert saved_expiry.replace(tzinfo=UTC) == renewed_expiry
        with session_scope() as db:
            with pytest.raises(CredentialError, match="revoked"):
                retrieve_token(db, old_ref)
            assert retrieve_token(db, new_ref) == "new-installation-token"
    finally:
        get_settings.cache_clear()


def test_github_token_is_not_renewed_while_valid(monkeypatch) -> None:
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", key)
    get_settings.cache_clear()
    connection_id, credential_ref = _seed_github_connection(
        datetime.now(UTC) + timedelta(minutes=30)
    )

    def unexpected_exchange(*_args):
        raise AssertionError("a valid token should not be renewed")

    monkeypatch.setattr(service, "exchange_installation_token", unexpected_exchange)
    try:
        with session_scope() as db:
            connection = db.get(ProviderConnection, connection_id)
            connector = service._build_connector(connection, db)

        assert connector._token == "old-installation-token"
        with session_scope() as db:
            assert retrieve_token(db, credential_ref) == "old-installation-token"
    finally:
        get_settings.cache_clear()


def test_legacy_github_token_without_expiry_is_renewed(monkeypatch) -> None:
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", key)
    get_settings.cache_clear()
    connection_id, _ = _seed_github_connection(None)
    monkeypatch.setattr(
        service,
        "exchange_installation_token",
        lambda *_args: {
            "token": "renewed-legacy-token",
            "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        },
    )
    try:
        with session_scope() as db:
            connection = db.get(ProviderConnection, connection_id)
            connector = service._build_connector(connection, db)
        assert connector._token == "renewed-legacy-token"
    finally:
        get_settings.cache_clear()


def test_token_expiry_requires_timezone_aware_iso_datetime() -> None:
    expiry = parse_token_expiry({"expires_at": "2026-11-17T00:00:00Z"})
    assert expiry.tzinfo is UTC
    with pytest.raises(ValueError, match="timezone-naive"):
        parse_token_expiry({"expires_at": "2026-11-17T00:00:00"})
    with pytest.raises(ValueError, match="did not return"):
        parse_token_expiry({})


def test_github_callback_persists_token_expiry(monkeypatch) -> None:
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", key)
    get_settings.cache_clear()
    tenant_id = uuid.uuid4()
    expiry = datetime.now(UTC) + timedelta(hours=1)
    monkeypatch.setattr(
        "app.api.routes.github.exchange_installation_token",
        lambda *_args: {
            "token": "callback-installation-token",
            "expires_at": expiry.isoformat(),
            "permissions": {"metadata": "read"},
        },
    )
    try:
        with session_scope() as db:
            connection = github_callback(
                state=sign_state(tenant_id, purpose="github"),
                installation_id=12345,
                setup_action="install",
                db=db,
            )
            assert connection.credential_expires_at == expiry
            assert retrieve_token(db, connection.credential_ref) == (
                "callback-installation-token"
            )
    finally:
        get_settings.cache_clear()


def test_github_renewal_auth_failure_is_classified(monkeypatch) -> None:
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", key)
    get_settings.cache_clear()
    connection_id, _ = _seed_github_connection(
        datetime.now(UTC) - timedelta(minutes=1)
    )
    request = httpx.Request("POST", "https://api.github.com")
    response = httpx.Response(401, request=request)

    def unauthorized(*_args):
        raise httpx.HTTPStatusError(
            "unauthorized", request=response.request, response=response
        )

    monkeypatch.setattr(service, "exchange_installation_token", unauthorized)
    try:
        with session_scope() as db:
            connection = db.get(ProviderConnection, connection_id)
            with pytest.raises(AuthError, match="authentication failed"):
                service._build_connector(connection, db)
    finally:
        get_settings.cache_clear()
