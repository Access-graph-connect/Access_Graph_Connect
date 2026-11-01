import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.enums import ConnectionStatus, Provider


class ConnectionOut(BaseModel):
    """Connection health and scope inventory.

    Deliberately excludes credential_ref and any token material.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider: Provider
    status: ConnectionStatus
    external_workspace_id: str | None
    scopes: list[str]
    created_at: datetime
    updated_at: datetime
