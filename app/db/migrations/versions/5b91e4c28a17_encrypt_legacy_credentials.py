"""encrypt legacy credential vault entries

Revision ID: 5b91e4c28a17
Revises: ded29c766a20
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from cryptography.fernet import Fernet

from app.config import get_settings

revision: str = "5b91e4c28a17"
down_revision: Union[str, None] = "ded29c766a20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    connection = op.get_bind()
    vault = sa.table(
        "credential_vault",
        sa.column("id", sa.Uuid()),
        sa.column("ciphertext", sa.Text()),
        sa.column("encrypted", sa.Boolean()),
    )
    entries = connection.execute(
        sa.select(vault.c.id, vault.c.ciphertext).where(vault.c.encrypted.is_(False))
    ).all()
    if not entries:
        return

    key = get_settings().token_encryption_key
    if not key:
        raise RuntimeError(
            "TOKEN_ENCRYPTION_KEY is required to encrypt legacy credentials"
        )
    try:
        fernet = Fernet(key.encode())
    except (TypeError, ValueError) as exc:
        raise RuntimeError("TOKEN_ENCRYPTION_KEY is invalid") from exc

    for entry_id, plaintext in entries:
        connection.execute(
            vault.update()
            .where(vault.c.id == entry_id)
            .values(
                ciphertext=fernet.encrypt(plaintext.encode()).decode(),
                encrypted=True,
            )
        )


def downgrade() -> None:
    pass
