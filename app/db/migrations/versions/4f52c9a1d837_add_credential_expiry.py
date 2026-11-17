"""track provider credential expiry

Revision ID: 4f52c9a1d837
Revises: 5b91e4c28a17
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "4f52c9a1d837"
down_revision: Union[str, None] = "5b91e4c28a17"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "provider_connections",
        sa.Column("credential_expires_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("provider_connections", "credential_expires_at")
