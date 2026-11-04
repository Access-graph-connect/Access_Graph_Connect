import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.enums import (
    AccessOrigin,
    ConnectionStatus,
    IdentityKind,
    Provider,
    RecordSource,
    ResourceType,
    SyncStatus,
    SyncTrigger,
)


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


class GitHubStartOut(BaseModel):
    install_url: str
    state: str


class IdentityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider: Provider
    external_id: str
    kind: IdentityKind
    display_name: str
    email: str | None
    is_active: bool | None
    source: RecordSource
    observed_at: datetime


class ResourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider: Provider
    external_id: str
    resource_type: ResourceType
    name: str
    source: RecordSource
    observed_at: datetime


class AccessRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider: Provider
    subject_external_id: str
    resource_external_id: str
    app_external_id: str
    permission: str
    origin: AccessOrigin
    source: RecordSource
    observed_at: datetime
    evidence: dict[str, Any] | None


class SyncRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    connection_id: uuid.UUID
    provider: Provider
    status: SyncStatus
    trigger: SyncTrigger
    started_at: datetime
    finished_at: datetime | None
    counts: dict[str, int]
    error_code: str | None
    error_detail: str | None
