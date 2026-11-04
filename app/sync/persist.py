"""Idempotent upsert of a NormalizedSnapshot into the inventory tables.

Upsert keys:
- identities/applications/resources: (connection_id, external_id)
- access_records: (connection_id, subject, resource, app, permission)

Re-importing the same record updates provenance in place — it never
creates a second row. Deletion/stale marking is reconciliation (Phase 3)
and deliberately does not happen here.
"""

import uuid
from typing import TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    AccessRecord,
    Application,
    Identity,
    Resource,
)
from app.normalization.models import NormalizedSnapshot

ModelT = TypeVar("T", Identity, Application, Resource)


def _upsert(
    db: Session,
    model: type[ModelT],
    connection_id: uuid.UUID,
    external_id: str,
    values: dict,
    counts: dict[str, int],
    counter: str,
) -> None:
    existing = db.scalar(
        select(model).where(
            model.connection_id == connection_id,
            model.external_id == external_id,
        )
    )
    if existing is None:
        db.add(model(connection_id=connection_id, external_id=external_id, **values))
        counts[f"{counter}_created"] += 1
    else:
        for key, value in values.items():
            setattr(existing, key, value)
        counts[f"{counter}_updated"] += 1


def upsert_snapshot(
    db: Session,
    tenant_id: uuid.UUID,
    connection_id: uuid.UUID,
    snapshot: NormalizedSnapshot,
) -> dict[str, int]:
    counts: dict[str, int] = {
        "identities_created": 0,
        "identities_updated": 0,
        "applications_created": 0,
        "applications_updated": 0,
        "resources_created": 0,
        "resources_updated": 0,
        "access_records_created": 0,
        "access_records_updated": 0,
    }
    common = {"tenant_id": tenant_id, "provider": snapshot.provider}

    for item in snapshot.identities:
        _upsert(
            db,
            Identity,
            connection_id,
            item.external_id,
            {
                **common,
                "kind": item.kind,
                "display_name": item.display_name,
                "email": item.email,
                "is_active": item.is_active,
                "source": item.source,
                "observed_at": item.observed_at,
                "raw": item.raw,
            },
            counts,
            "identities",
        )

    for item in snapshot.applications:
        _upsert(
            db,
            Application,
            connection_id,
            item.external_id,
            {
                **common,
                "name": item.name,
                "app_type": item.app_type,
                "installed_at": item.installed_at,
                "source": item.source,
                "observed_at": item.observed_at,
                "raw": item.raw,
            },
            counts,
            "applications",
        )

    for item in snapshot.resources:
        _upsert(
            db,
            Resource,
            connection_id,
            item.external_id,
            {
                **common,
                "resource_type": item.resource_type,
                "name": item.name,
                "source": item.source,
                "observed_at": item.observed_at,
                "raw": item.raw,
            },
            counts,
            "resources",
        )

    for item in snapshot.access_records:
        existing = db.scalar(
            select(AccessRecord).where(
                AccessRecord.connection_id == connection_id,
                AccessRecord.subject_external_id == item.subject_external_id,
                AccessRecord.resource_external_id == item.resource_external_id,
                AccessRecord.app_external_id == item.app_external_id,
                AccessRecord.permission == item.permission,
            )
        )
        values = {
            **common,
            "subject_external_id": item.subject_external_id,
            "resource_external_id": item.resource_external_id,
            "app_external_id": item.app_external_id,
            "permission": item.permission,
            "origin": item.origin,
            "source": item.source,
            "observed_at": item.observed_at,
            "evidence": item.evidence,
        }
        if existing is None:
            db.add(AccessRecord(connection_id=connection_id, **values))
            counts["access_records_created"] += 1
        else:
            for key, value in values.items():
                setattr(existing, key, value)
            counts["access_records_updated"] += 1

    db.flush()
    return counts
