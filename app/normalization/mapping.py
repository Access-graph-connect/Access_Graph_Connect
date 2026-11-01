"""Mapping rules from fixture-shaped provider payloads to the unified schema.

Real provider connectors (GitHub in Phase 2, Slack in Phase 4) get their own
mapping modules; this one handles the fixture document format shared by the
simulated Notion adapter and tests.
"""

from datetime import datetime, timezone
from typing import Any, Mapping

from app.enums import (
    AccessOrigin,
    IdentityKind,
    Provider,
    RecordSource,
    ResourceType,
)
from app.normalization.models import (
    NormalizedAccessRecord,
    NormalizedApplication,
    NormalizedIdentity,
    NormalizedResource,
    NormalizedSnapshot,
)

_SOURCE = RecordSource.FIXTURE


def _parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return datetime.now(timezone.utc)


def _parse_origin(value: Any) -> AccessOrigin:
    try:
        return AccessOrigin(value)
    except ValueError:
        return AccessOrigin.UNKNOWN


def normalize_fixture_payload(payload: Mapping[str, Any]) -> NormalizedSnapshot:
    provider = Provider(str(payload["provider"]))
    workspace = payload.get("workspace") or {}
    coverage_notes: list[str] = []
    if payload.get("simulated"):
        coverage_notes.append(
            "Fixture data is simulated; it is not live provider data."
        )

    identities: list[NormalizedIdentity] = []
    for user in payload.get("users", []):
        identities.append(
            NormalizedIdentity(
                external_id=str(user["id"]),
                kind=IdentityKind.HUMAN,
                display_name=str(user.get("name") or user["id"]),
                email=user.get("email"),
                is_active=user.get("active"),
                source=_SOURCE,
                observed_at=_parse_dt(user.get("observed_at")),
                raw=dict(user),
            )
        )
    for bot in payload.get("bots", []):
        identities.append(
            NormalizedIdentity(
                external_id=str(bot["id"]),
                kind=IdentityKind.BOT,
                display_name=str(bot.get("name") or bot["id"]),
                is_active=bot.get("active"),
                source=_SOURCE,
                observed_at=_parse_dt(bot.get("observed_at")),
                raw=dict(bot),
            )
        )

    applications = [
        NormalizedApplication(
            external_id=str(integration["id"]),
            name=str(integration.get("name") or integration["id"]),
            app_type=integration.get("type"),
            installed_at=(
                _parse_dt(integration["installed_at"])
                if integration.get("installed_at")
                else None
            ),
            source=_SOURCE,
            observed_at=_parse_dt(integration.get("observed_at")),
            raw=dict(integration),
        )
        for integration in payload.get("integrations", [])
    ]

    resources = [
        NormalizedResource(
            external_id=str(page["id"]),
            resource_type=ResourceType.PAGE,
            name=str(page.get("title") or page["id"]),
            source=_SOURCE,
            observed_at=_parse_dt(page.get("observed_at")),
            raw=dict(page),
        )
        for page in payload.get("pages", [])
    ]

    access_records: list[NormalizedAccessRecord] = []
    for grant in payload.get("grants", []):
        origin = _parse_origin(grant.get("origin"))
        if origin is AccessOrigin.UNKNOWN:
            coverage_notes.append(
                f"Permission origin not exposed for grant on subject "
                f"{grant.get('subject_id')!r}; marked unknown."
            )
        access_records.append(
            NormalizedAccessRecord(
                subject_external_id=str(grant["subject_id"]),
                resource_external_id=str(grant.get("page_id") or ""),
                app_external_id=str(grant.get("integration_id") or ""),
                permission=str(grant["permission"]),
                origin=origin,
                source=_SOURCE,
                observed_at=_parse_dt(grant.get("observed_at")),
                evidence=dict(grant),
            )
        )

    return NormalizedSnapshot(
        provider=provider,
        workspace_external_id=workspace.get("id"),
        source=_SOURCE,
        identities=identities,
        applications=applications,
        resources=resources,
        access_records=access_records,
        coverage_notes=coverage_notes,
    )
