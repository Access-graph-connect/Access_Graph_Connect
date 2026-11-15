import uuid

import pytest
from cryptography.fernet import Fernet

from app.config import get_settings
from app.db.models import CredentialVault, ProviderConnection, Tenant
from app.db.session import session_scope
from app.enums import ConnectionStatus, Provider
from app.security.credentials import (
    CredentialError,
    replace_connection_token,
    retrieve_token,
    store_token,
)


@pytest.fixture
def encryption_key(monkeypatch):
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_token_round_trip_encrypted(encryption_key) -> None:
    with session_scope() as db:
        ref = store_token(db, "gho_secret_token")
        assert retrieve_token(db, ref) == "gho_secret_token"


def test_ciphertext_is_not_plaintext(encryption_key) -> None:
    with session_scope() as db:
        ref = store_token(db, "gho_secret_token")
        entry = db.get(CredentialVault, uuid.UUID(ref))
        assert entry.encrypted is True
        assert "gho_secret_token" not in entry.ciphertext


def test_unknown_reference_raises() -> None:
    with session_scope() as db, pytest.raises(CredentialError):
        retrieve_token(db, str(uuid.uuid4()))


def test_storing_credentials_requires_encryption_key(monkeypatch) -> None:
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", "")
    get_settings.cache_clear()
    try:
        with (
            session_scope() as db,
            pytest.raises(CredentialError, match="TOKEN_ENCRYPTION_KEY"),
        ):
            store_token(db, "secret")
    finally:
        get_settings.cache_clear()


def test_replacing_token_revokes_previous_reference(encryption_key) -> None:
    with session_scope() as db:
        tenant = Tenant(name=f"credential-{uuid.uuid4().hex}")
        db.add(tenant)
        db.flush()
        connection = ProviderConnection(
            tenant_id=tenant.id,
            provider=Provider.SLACK,
            external_workspace_id=f"T-{uuid.uuid4().hex}",
            status=ConnectionStatus.ACTIVE,
        )
        db.add(connection)
        db.flush()

        old_ref = store_token(db, "old-secret")
        connection.credential_ref = old_ref
        new_ref = replace_connection_token(db, connection, "new-secret")

        with pytest.raises(CredentialError, match="revoked"):
            retrieve_token(db, old_ref)
        assert retrieve_token(db, new_ref) == "new-secret"
        assert connection.credential_ref == new_ref
