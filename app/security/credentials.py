"""Credential vault: provider tokens stored encrypted, referenced by id.

`ProviderConnection.credential_ref` holds the vault entry id — never token
material. Tokens are encrypted with Fernet when TOKEN_ENCRYPTION_KEY is
configured; full lifecycle handling (expiry, revocation, reconnect states)
is built out in Phase 5.
"""

import uuid

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import CredentialVault


class CredentialError(RuntimeError):
    pass


def _fernet() -> Fernet | None:
    key = get_settings().token_encryption_key
    return Fernet(key.encode()) if key else None


def store_token(db: Session, token: str) -> str:
    """Encrypt and persist a token; return the credential reference."""
    fernet = _fernet()
    ciphertext = fernet.encrypt(token.encode()).decode() if fernet else token
    entry = CredentialVault(
        id=uuid.uuid4(), ciphertext=ciphertext, encrypted=fernet is not None
    )
    db.add(entry)
    db.flush()
    return str(entry.id)


def retrieve_token(db: Session, credential_ref: str) -> str:
    entry = db.get(CredentialVault, uuid.UUID(credential_ref))
    if entry is None:
        raise CredentialError("unknown credential reference")
    if entry.encrypted:
        fernet = _fernet()
        if fernet is None:
            raise CredentialError("TOKEN_ENCRYPTION_KEY is not configured")
        try:
            return fernet.decrypt(entry.ciphertext.encode()).decode()
        except InvalidToken as exc:
            raise CredentialError("credential cannot be decrypted") from exc
    return entry.ciphertext
