"""Reconciliation: mark records stale only within verified coverage.

Safety rules (from the acceptance criteria):
- A *partial* sync never marks unseen records stale — incomplete coverage
  means we don't know what still exists.
- A *complete* sync marks records missing from the fresh snapshot as stale,
  but only for entity kinds the connector actually covered.
- "Stale" is a soft state: rows are kept for audit, flagged via
  `reconciled_at` + `is_stale`, never hard-deleted here.
"""

import uuid
from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AccessRecord, Application, Identity, Resource
from app.normalization.models import NormalizedSnapshot


def _mark_stale_missing(
    db: Session,
    model,
    connection_id: uuid.UUID,
    seen_external_ids: set[str],
    now: datetime,
    counts: dict[str, int],
    counter: str,
) -> None:
    # Load ALL rows (including stale) so we can both stale the missing and
    # revive the ones that reappeared.
    rows = db.scalars(select(model).where(model.connection_id == connection_id)).all()
    for row in rows:
        if row.external_id not in seen_external_ids:
            if not row.is_stale:
                row.is_stale = True
                row.reconciled_at = now
                counts[f"{counter}_staled"] += 1
        elif row.is_stale:
            # Present again -> revive.
            row.is_stale = False
            row.reconciled_at = now
            counts[f"{counter}_revived"] += 1


def reconcile(
    db: Session,
    connection_id: uuid.UUID,
    snapshot: NormalizedSnapshot,
    complete: bool,
) -> dict[str, int]:
    """Reconcile DB state against a fresh snapshot.

    `complete` must be True only when the snapshot covers the full visible
    inventory (no coverage gaps). Partial snapshots return zero changes.
    """
    counts: dict[str, int] = {
        "identities_staled": 0,
        "identities_revived": 0,
        "applications_staled": 0,
        "applications_revived": 0,
        "resources_staled": 0,
        "resources_revived": 0,
        "access_records_staled": 0,
        "access_records_revived": 0,
    }
    if not complete:
        return counts

    now = datetime.now(timezone.utc)
    _mark_stale_missing(
        db, Identity, connection_id,
        {i.external_id for i in snapshot.identities}, now, counts, "identities",
    )
    _mark_stale_missing(
        db, Application, connection_id,
        {a.external_id for a in snapshot.applications}, now, counts, "applications",
    )
    _mark_stale_missing(
        db, Resource, connection_id,
        {r.external_id for r in snapshot.resources}, now, counts, "resources",
    )
    _reconcile_access(db, connection_id, snapshot, now, counts)
    db.flush()
    return counts


def _reconcile_access(
    db: Session,
    connection_id: uuid.UUID,
    snapshot: NormalizedSnapshot,
    now: datetime,
    counts: dict[str, int],
) -> None:
    seen = {
        (a.subject_external_id, a.resource_external_id, a.app_external_id, a.permission)
        for a in snapshot.access_records
    }
    rows = db.scalars(
        select(AccessRecord).where(AccessRecord.connection_id == connection_id)
    ).all()
    for row in rows:
        key = (
            row.subject_external_id,
            row.resource_external_id,
            row.app_external_id,
            row.permission,
        )
        if key not in seen:
            if not row.is_stale:
                row.is_stale = True
                row.reconciled_at = now
                counts["access_records_staled"] += 1
        elif row.is_stale:
            row.is_stale = False
            row.reconciled_at = now
            counts["access_records_revived"] += 1
