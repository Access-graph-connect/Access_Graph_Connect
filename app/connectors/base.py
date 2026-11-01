"""Connector protocol.

Every provider adapter (GitHub, Slack, fixture providers) implements this
protocol. Connectors are read-only: they fetch provider data and normalize
it into the unified schema. They never write back to the provider.

Engineering principle: one connector complete and trustworthy is better
than many superficial adapters.
"""

import uuid
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, runtime_checkable

from app.enums import Provider
from app.normalization.models import NormalizedSnapshot


@dataclass(frozen=True)
class ConnectionContext:
    tenant_id: uuid.UUID
    connection_id: uuid.UUID
    # Reference to secret material in the credential store — never the
    # token itself. Resolved only at the point of the provider API call.
    credential_ref: str | None = None
    settings: Mapping[str, Any] = field(default_factory=dict)


@runtime_checkable
class Connector(Protocol):
    provider: Provider

    def fetch_snapshot(self, context: ConnectionContext) -> Mapping[str, Any]:
        """Fetch the raw provider payload (API responses or fixture data)."""
        ...

    def normalize(self, payload: Mapping[str, Any]) -> NormalizedSnapshot:
        """Map a raw payload into the unified schema with explicit unknowns."""
        ...
