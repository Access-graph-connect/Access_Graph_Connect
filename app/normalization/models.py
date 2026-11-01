"""Normalized (provider-agnostic) schema produced by every connector.

Rules:
- Unknown or unsupported attributes are explicit: kind=UNKNOWN,
  origin=UNKNOWN, is_active=None. Never inferred from names or heuristics.
- Every record carries provenance: source and observed_at.
- OAuth scope, provider role, and observed grant stay separate concepts;
  only observed grants appear in NormalizedAccessRecord.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.enums import (
    AccessOrigin,
    IdentityKind,
    Provider,
    RecordSource,
    ResourceType,
)


class NormalizedIdentity(BaseModel):
    external_id: str
    kind: IdentityKind = IdentityKind.UNKNOWN
    display_name: str
    email: str | None = None
    is_active: bool | None = None
    source: RecordSource
    observed_at: datetime
    raw: dict[str, Any] = Field(default_factory=dict)


class NormalizedApplication(BaseModel):
    external_id: str
    name: str
    app_type: str | None = None
    installed_at: datetime | None = None
    source: RecordSource
    observed_at: datetime
    raw: dict[str, Any] = Field(default_factory=dict)


class NormalizedResource(BaseModel):
    external_id: str
    resource_type: ResourceType = ResourceType.OTHER
    name: str
    source: RecordSource
    observed_at: datetime
    raw: dict[str, Any] = Field(default_factory=dict)


class NormalizedAccessRecord(BaseModel):
    subject_external_id: str
    resource_external_id: str = ""
    app_external_id: str = ""
    permission: str
    origin: AccessOrigin = AccessOrigin.UNKNOWN
    source: RecordSource
    observed_at: datetime
    evidence: dict[str, Any] = Field(default_factory=dict)


class NormalizedSnapshot(BaseModel):
    provider: Provider
    workspace_external_id: str | None = None
    source: RecordSource = RecordSource.FIXTURE
    identities: list[NormalizedIdentity] = Field(default_factory=list)
    applications: list[NormalizedApplication] = Field(default_factory=list)
    resources: list[NormalizedResource] = Field(default_factory=list)
    access_records: list[NormalizedAccessRecord] = Field(default_factory=list)
    # Visibility/coverage limitations, e.g. "permission origin not exposed".
    coverage_notes: list[str] = Field(default_factory=list)
