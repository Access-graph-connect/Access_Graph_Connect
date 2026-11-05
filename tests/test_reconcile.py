import json
import uuid
from pathlib import Path

from sqlalchemy import select

from app.db.models import AccessRecord, Identity, ProviderConnection, Resource, Tenant
from app.db.session import session_scope
from app.enums import ConnectionStatus, Provider
from app.normalization.github import normalize_github_payload
from app.sync.persist import upsert_snapshot
from app.sync.reconcile import reconcile

PAYLOAD = json.loads(
    (Path(__file__).parent / "fixtures" / "github_payload.json").read_text(
        encoding="utf-8"
    )
)


def _seed() -> tuple[uuid.UUID, uuid.UUID]:
    with session_scope() as db:
        tenant = Tenant(id=uuid.uuid4(), name=f"t-{uuid.uuid4().hex[:8]}")
        db.add(tenant)
        db.flush()
        conn = ProviderConnection(
            tenant_id=tenant.id,
            provider=Provider.GITHUB,
            external_workspace_id="acme-test-org",
            status=ConnectionStatus.ACTIVE,
        )
        db.add(conn)
        db.flush()
        return tenant.id, conn.id


def _stale_flags(db, model, connection_id) -> dict[str, bool]:
    rows = db.scalars(select(model).where(model.connection_id == connection_id)).all()
    return {r.external_id: r.is_stale for r in rows}


def test_partial_sync_never_marks_stale() -> None:
    tenant_id, conn_id = _seed()
    snapshot = normalize_github_payload(PAYLOAD)
    with session_scope() as db:
        upsert_snapshot(db, tenant_id, conn_id, snapshot)

    # A partial sync (complete=False) with an EMPTY snapshot must not stale anything.
    empty = normalize_github_payload({**PAYLOAD, "members": [], "repositories": [], "collaborators": {}})
    with session_scope() as db:
        counts = reconcile(db, conn_id, empty, complete=False)
        assert all(v == 0 for v in counts.values())
        assert all(not v for v in _stale_flags(db, Identity, conn_id).values())
        assert all(not v for v in _stale_flags(db, Resource, conn_id).values())


def test_complete_sync_marks_missing_stale() -> None:
    tenant_id, conn_id = _seed()
    snapshot = normalize_github_payload(PAYLOAD)
    with session_scope() as db:
        upsert_snapshot(db, tenant_id, conn_id, snapshot)

    # New snapshot drops one repo (2002) and one member (1002) entirely —
    # from members AND from all collaborator lists (collaborators are also
    # identities, so leaving 1002 as a collaborator would keep it alive).
    reduced = json.loads(json.dumps(PAYLOAD))
    reduced["repositories"] = [r for r in reduced["repositories"] if r["id"] != 2002]
    reduced["members"] = [m for m in reduced["members"] if m["id"] != 1002]
    reduced["collaborators"] = {
        k: [c for c in v if c["id"] != 1002]
        for k, v in reduced["collaborators"].items()
        if "web-app" not in k
    }
    new_snapshot = normalize_github_payload(reduced)

    with session_scope() as db:
        counts = reconcile(db, conn_id, new_snapshot, complete=True)
        assert counts["resources_staled"] == 1
        # Both 1002 (removed member) and 1004 (outside collaborator on the
        # dropped web-app repo) are gone from the reduced snapshot.
        assert counts["identities_staled"] == 2

        resources = _stale_flags(db, Resource, conn_id)
        assert resources["2002"] is True
        assert resources["2001"] is False

        identities = _stale_flags(db, Identity, conn_id)
        assert identities["1002"] is True
        assert identities["1004"] is True
        assert identities["1001"] is False


def test_revived_when_record_returns() -> None:
    tenant_id, conn_id = _seed()
    snapshot = normalize_github_payload(PAYLOAD)
    with session_scope() as db:
        upsert_snapshot(db, tenant_id, conn_id, snapshot)

    # Remove a member (from members and collaborators), reconcile -> stale.
    reduced = json.loads(json.dumps(PAYLOAD))
    reduced["members"] = [m for m in reduced["members"] if m["id"] != 1002]
    reduced["collaborators"] = {
        k: [c for c in v if c["id"] != 1002]
        for k, v in reduced["collaborators"].items()
    }
    with session_scope() as db:
        reconcile(db, conn_id, normalize_github_payload(reduced), complete=True)
        assert _stale_flags(db, Identity, conn_id)["1002"] is True

    # Member returns in a later complete sync -> revived.
    with session_scope() as db:
        upsert_snapshot(db, tenant_id, conn_id, snapshot)
        counts = reconcile(db, conn_id, snapshot, complete=True)
        assert counts["identities_revived"] == 1
        assert _stale_flags(db, Identity, conn_id)["1002"] is False
