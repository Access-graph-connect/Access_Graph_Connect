"""SQLAlchemy models for the unified access inventory.

Design rules encoded here:
- Every inventory row carries provenance: source, observed_at, and raw evidence.
- Unknown/unsupported attributes are stored explicitly (NULL or "unknown"),
  never inferred.
- Upsert identity is (connection_id, external_id) so re-imports stay one row.
- Column types are portable (sa.Uuid, sa.JSON, non-native enums) so the same
  migrations run on PostgreSQL in production and SQLite in tests.
"""

import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, utcnow
from app.enums import (
    AccessOrigin,
    ConnectionStatus,
    IdentityKind,
    Provider,
    RecordSource,
    ResourceType,
    SyncStatus,
    SyncTrigger,
    WebhookStatus,
)

DateTimeTz = sa.DateTime(timezone=True)


class Tenant(Base, TimestampMixin):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(sa.String(200), unique=True, nullable=False)

    connections: Mapped[list["ProviderConnection"]] = relationship(
        back_populates="tenant"
    )


class ProviderConnection(Base, TimestampMixin):
    __tablename__ = "provider_connections"
    __table_args__ = (
        sa.UniqueConstraint(
            "tenant_id", "provider", "external_workspace_id", name="uq_connection_workspace"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("tenants.id"), index=True, nullable=False
    )
    provider: Mapped[Provider] = mapped_column(
        sa.Enum(Provider, native_enum=False, validate_strings=True), nullable=False
    )
    external_workspace_id: Mapped[str | None] = mapped_column(sa.String(200))
    # OAuth scopes the integration token was granted (scope inventory).
    scopes: Mapped[list[str]] = mapped_column(sa.JSON, default=list, nullable=False)
    status: Mapped[ConnectionStatus] = mapped_column(
        sa.Enum(ConnectionStatus, native_enum=False, validate_strings=True),
        default=ConnectionStatus.ACTIVE,
        nullable=False,
    )
    # Reference into the secret store. Secret material is never stored here.
    credential_ref: Mapped[str | None] = mapped_column(sa.String(200))

    tenant: Mapped[Tenant] = relationship(back_populates="connections")


class Identity(Base, TimestampMixin):
    __tablename__ = "identities"
    __table_args__ = (
        sa.UniqueConstraint("connection_id", "external_id", name="uq_identity_external"),
    )

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("tenants.id"), index=True, nullable=False
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("provider_connections.id"), index=True, nullable=False
    )
    provider: Mapped[Provider] = mapped_column(
        sa.Enum(Provider, native_enum=False, validate_strings=True), nullable=False
    )
    external_id: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    kind: Mapped[IdentityKind] = mapped_column(
        sa.Enum(IdentityKind, native_enum=False, validate_strings=True),
        default=IdentityKind.UNKNOWN,
        nullable=False,
    )
    display_name: Mapped[str] = mapped_column(sa.String(300), nullable=False)
    email: Mapped[str | None] = mapped_column(sa.String(300))
    # NULL means "activity not observable by this provider" — never guessed.
    is_active: Mapped[bool | None] = mapped_column(sa.Boolean)
    source: Mapped[RecordSource] = mapped_column(
        sa.Enum(RecordSource, native_enum=False, validate_strings=True), nullable=False
    )
    observed_at: Mapped[datetime] = mapped_column(DateTimeTz, nullable=False)
    raw: Mapped[dict[str, Any] | None] = mapped_column(sa.JSON)


class Application(Base, TimestampMixin):
    __tablename__ = "applications"
    __table_args__ = (
        sa.UniqueConstraint("connection_id", "external_id", name="uq_application_external"),
    )

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("tenants.id"), index=True, nullable=False
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("provider_connections.id"), index=True, nullable=False
    )
    provider: Mapped[Provider] = mapped_column(
        sa.Enum(Provider, native_enum=False, validate_strings=True), nullable=False
    )
    external_id: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(300), nullable=False)
    app_type: Mapped[str | None] = mapped_column(sa.String(100))
    installed_at: Mapped[datetime | None] = mapped_column(DateTimeTz)
    source: Mapped[RecordSource] = mapped_column(
        sa.Enum(RecordSource, native_enum=False, validate_strings=True), nullable=False
    )
    observed_at: Mapped[datetime] = mapped_column(DateTimeTz, nullable=False)
    raw: Mapped[dict[str, Any] | None] = mapped_column(sa.JSON)


class Resource(Base, TimestampMixin):
    __tablename__ = "resources"
    __table_args__ = (
        sa.UniqueConstraint("connection_id", "external_id", name="uq_resource_external"),
    )

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("tenants.id"), index=True, nullable=False
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("provider_connections.id"), index=True, nullable=False
    )
    provider: Mapped[Provider] = mapped_column(
        sa.Enum(Provider, native_enum=False, validate_strings=True), nullable=False
    )
    external_id: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    resource_type: Mapped[ResourceType] = mapped_column(
        sa.Enum(ResourceType, native_enum=False, validate_strings=True),
        default=ResourceType.OTHER,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(sa.String(300), nullable=False)
    source: Mapped[RecordSource] = mapped_column(
        sa.Enum(RecordSource, native_enum=False, validate_strings=True), nullable=False
    )
    observed_at: Mapped[datetime] = mapped_column(DateTimeTz, nullable=False)
    raw: Mapped[dict[str, Any] | None] = mapped_column(sa.JSON)


class AccessRecord(Base, TimestampMixin):
    """An observed grant: subject -> permission on resource/app.

    `origin` distinguishes direct vs inherited grants; UNKNOWN when the
    provider does not expose the origin. Empty string (not NULL) is used for
    resource/app external ids so the composite unique key enforces
    idempotent upserts.
    """

    __tablename__ = "access_records"
    __table_args__ = (
        sa.UniqueConstraint(
            "connection_id",
            "subject_external_id",
            "resource_external_id",
            "app_external_id",
            "permission",
            name="uq_access_record_grant",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("tenants.id"), index=True, nullable=False
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("provider_connections.id"), index=True, nullable=False
    )
    provider: Mapped[Provider] = mapped_column(
        sa.Enum(Provider, native_enum=False, validate_strings=True), nullable=False
    )
    subject_external_id: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    resource_external_id: Mapped[str] = mapped_column(
        sa.String(200), default="", nullable=False
    )
    app_external_id: Mapped[str] = mapped_column(
        sa.String(200), default="", nullable=False
    )
    permission: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    origin: Mapped[AccessOrigin] = mapped_column(
        sa.Enum(AccessOrigin, native_enum=False, validate_strings=True),
        default=AccessOrigin.UNKNOWN,
        nullable=False,
    )
    source: Mapped[RecordSource] = mapped_column(
        sa.Enum(RecordSource, native_enum=False, validate_strings=True), nullable=False
    )
    observed_at: Mapped[datetime] = mapped_column(DateTimeTz, nullable=False)
    evidence: Mapped[dict[str, Any] | None] = mapped_column(sa.JSON)


class SyncRun(Base):
    __tablename__ = "sync_runs"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("tenants.id"), index=True, nullable=False
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("provider_connections.id"), index=True, nullable=False
    )
    provider: Mapped[Provider] = mapped_column(
        sa.Enum(Provider, native_enum=False, validate_strings=True), nullable=False
    )
    status: Mapped[SyncStatus] = mapped_column(
        sa.Enum(SyncStatus, native_enum=False, validate_strings=True),
        default=SyncStatus.RUNNING,
        nullable=False,
    )
    trigger: Mapped[SyncTrigger] = mapped_column(
        sa.Enum(SyncTrigger, native_enum=False, validate_strings=True),
        default=SyncTrigger.MANUAL,
        nullable=False,
    )
    started_at: Mapped[datetime] = mapped_column(DateTimeTz, default=utcnow, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTimeTz)
    cursor: Mapped[str | None] = mapped_column(sa.String(500))
    counts: Mapped[dict[str, int]] = mapped_column(sa.JSON, default=dict, nullable=False)
    # Redacted error classification only — never tokens or payloads.
    error_code: Mapped[str | None] = mapped_column(sa.String(100))
    error_detail: Mapped[str | None] = mapped_column(sa.String(1000))


class SyncCursor(Base):
    __tablename__ = "sync_cursors"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    connection_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("provider_connections.id"), unique=True, nullable=False
    )
    provider: Mapped[Provider] = mapped_column(
        sa.Enum(Provider, native_enum=False, validate_strings=True), nullable=False
    )
    cursor: Mapped[str | None] = mapped_column(sa.String(500))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTimeTz)
    updated_at: Mapped[datetime] = mapped_column(
        DateTimeTz, default=utcnow, onupdate=utcnow, nullable=False
    )


class WebhookInbox(Base):
    """Deduplicating inbox for provider webhook deliveries."""

    __tablename__ = "webhook_inbox"
    __table_args__ = (
        sa.UniqueConstraint("provider", "delivery_id", name="uq_webhook_delivery"),
    )

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("tenants.id"), index=True
    )
    connection_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("provider_connections.id"), index=True
    )
    provider: Mapped[Provider] = mapped_column(
        sa.Enum(Provider, native_enum=False, validate_strings=True), nullable=False
    )
    delivery_id: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    signature_valid: Mapped[bool] = mapped_column(sa.Boolean, nullable=False)
    payload_hash: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    status: Mapped[WebhookStatus] = mapped_column(
        sa.Enum(WebhookStatus, native_enum=False, validate_strings=True),
        default=WebhookStatus.RECEIVED,
        nullable=False,
    )
    received_at: Mapped[datetime] = mapped_column(DateTimeTz, default=utcnow, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTimeTz)


class ConnectorEvent(Base):
    """Redacted audit event for connector actions (correlation-id keyed)."""

    __tablename__ = "connector_events"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("tenants.id"), index=True
    )
    connection_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("provider_connections.id"), index=True
    )
    provider: Mapped[Provider | None] = mapped_column(
        sa.Enum(Provider, native_enum=False, validate_strings=True)
    )
    correlation_id: Mapped[str] = mapped_column(sa.String(100), index=True, nullable=False)
    action: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    outcome: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    error: Mapped[str | None] = mapped_column(sa.String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTimeTz, default=utcnow, nullable=False)
