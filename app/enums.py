"""Shared vocabulary for providers, statuses, and access semantics.

These enums are intentionally shared by the persistence layer and the
normalization layer so that "unknown" states have one canonical spelling.
"""

from enum import StrEnum


class Provider(StrEnum):
    GITHUB = "github"
    SLACK = "slack"
    NOTION = "notion"


class ConnectionStatus(StrEnum):
    ACTIVE = "active"
    DEGRADED = "degraded"
    RECONNECT_REQUIRED = "reconnect_required"
    DISABLED = "disabled"


class IdentityKind(StrEnum):
    HUMAN = "human"
    BOT = "bot"
    SERVICE = "service"
    UNKNOWN = "unknown"


class ResourceType(StrEnum):
    REPOSITORY = "repository"
    CHANNEL = "channel"
    WORKSPACE = "workspace"
    PAGE = "page"
    OTHER = "other"


class AccessOrigin(StrEnum):
    DIRECT = "direct"
    INHERITED = "inherited"
    UNKNOWN = "unknown"


class RecordSource(StrEnum):
    API = "api"
    WEBHOOK = "webhook"
    FIXTURE = "fixture"


class SyncStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PARTIAL = "partial"


class SyncTrigger(StrEnum):
    MANUAL = "manual"
    SCHEDULE = "schedule"
    WEBHOOK = "webhook"


class WebhookStatus(StrEnum):
    RECEIVED = "received"
    PROCESSED = "processed"
    DUPLICATE = "duplicate"
    REJECTED = "rejected"
