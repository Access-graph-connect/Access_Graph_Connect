"""Credential vault: provider tokens stored encrypted, referenced by id.

`ProviderConnection.credential_ref` holds the vault entry id — never token
material. Provider credentials must be encrypted with Fernet. Replaced and
revoked vault entries cannot be retrieved.
"""

import uuid
from datetime import UTC, datetime

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import CredentialVault, ProviderConnection


class CredentialError(RuntimeError):
    pass


def _fernet() -> Fernet:
    key = get_settings().token_encryption_key
    if not key:
        raise CredentialError("TOKEN_ENCRYPTION_KEY is not configured")
    try:
        return Fernet(key.encode())
    except (TypeError, ValueError) as exc:
        raise CredentialError("TOKEN_ENCRYPTION_KEY is invalid") from exc


def store_token(db: Session, token: str) -> str:
    """Encrypt and persist a token; return the credential reference."""
    fernet = _fernet()
    entry = CredentialVault(
        id=uuid.uuid4(),
        ciphertext=fernet.encrypt(token.encode()).decode(),
        encrypted=True,
    )
    db.add(entry)
    db.flush()
    return str(entry.id)


def revoke_token(db: Session, credential_ref: str) -> None:
    """Revoke a vault reference without deleting its audit record."""
    try:
        entry_id = uuid.UUID(credential_ref)
    except ValueError as exc:
        raise CredentialError("invalid credential reference") from exc
    entry = db.get(CredentialVault, entry_id)
    if entry is None:
        raise CredentialError("unknown credential reference")
    if entry.revoked_at is None:
        entry.revoked_at = datetime.now(UTC)
        db.flush()


def replace_connection_token(
    db: Session, connection: ProviderConnection, token: str
) -> str:
    """Store the new token and revoke the connection's previous vault entry."""
    credential_ref = store_token(db, token)
    previous_ref = connection.credential_ref
    if previous_ref and previous_ref != credential_ref:
        revoke_token(db, previous_ref)
    connection.credential_ref = credential_ref
    return credential_ref


def retrieve_token(db: Session, credential_ref: str) -> str:
    try:
        entry_id = uuid.UUID(credential_ref)
    except ValueError as exc:
        raise CredentialError("invalid credential reference") from exc
    entry = db.get(CredentialVault, entry_id)
    if entry is None:
        raise CredentialError("unknown credential reference")
    if entry.revoked_at is not None:
        raise CredentialError("credential has been revoked")
    if not entry.encrypted:
        raise CredentialError("credential is stored unencrypted and must be replaced")
    fernet = _fernet()
    try:
        return fernet.decrypt(entry.ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise CredentialError("credential cannot be decrypted") from exc
