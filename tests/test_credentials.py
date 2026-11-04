import pytest
from cryptography.fernet import Fernet

from app.config import get_settings
from app.db.session import session_scope
from app.security.credentials import CredentialError, retrieve_token, store_token


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
    from app.db.models import CredentialVault

    with session_scope() as db:
        ref = store_token(db, "gho_secret_token")
        import uuid

        entry = db.get(CredentialVault, uuid.UUID(ref))
        assert entry.encrypted is True
        assert "gho_secret_token" not in entry.ciphertext


def test_unknown_reference_raises() -> None:
    import uuid

    with session_scope() as db, pytest.raises(CredentialError):
        retrieve_token(db, str(uuid.uuid4()))
