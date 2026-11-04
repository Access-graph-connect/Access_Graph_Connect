import json
import uuid
from pathlib import Path

from sqlalchemy import func, select

from app.db.models import AccessRecord, Identity, ProviderConnection, Resource, Tenant
from app.db.session import session_scope
from app.enums import ConnectionStatus, Provider
from app.normalization.github import normalize_github_payload
from app.sync.persist import upsert_snapshot

PAYLOAD = json.loads(
    (Path(__file__).parent / "fixtures" / "github_payload.json").read_text(
        encoding="utf-8"
    )
)


def _seed_connection() -> tuple[uuid.UUID, uuid.UUID]:
    with session_scope() as db:
        tenant = Tenant(id=uuid.uuid4(), name=f"tenant-{uuid.uuid4().hex[:8]}")
        db.add(tenant)
        db.flush()
        connection = ProviderConnection(
            tenant_id=tenant.id,
            provider=Provider.GITHUB,
            external_workspace_id="acme-test-org",
            status=ConnectionStatus.ACTIVE,
        )
        db.add(connection)
        db.flush()
        return tenant.id, connection.id


def _count(db, model, connection_id) -> int:
    return db.scalar(
        select(func.count()).select_from(model).where(
            model.connection_id == connection_id
        )
    )


def test_upsert_imports_snapshot() -> None:
    tenant_id, connection_id = _seed_connection()
    snapshot = normalize_github_payload(PAYLOAD)

    with session_scope() as db:
        counts = upsert_snapshot(db, tenant_id, connection_id, snapshot)
        assert counts["identities_created"] == 4
        assert counts["resources_created"] == 2
        assert counts["access_records_created"] == 4

        assert _count(db, Identity, connection_id) == 4
        assert _count(db, Resource, connection_id) == 2
        assert _count(db, AccessRecord, connection_id) == 4


def test_reimport_stays_one_row_per_record() -> None:
    tenant_id, connection_id = _seed_connection()
    snapshot = normalize_github_payload(PAYLOAD)

    with session_scope() as db:
        upsert_snapshot(db, tenant_id, connection_id, snapshot)
    with session_scope() as db:
        counts = upsert_snapshot(db, tenant_id, connection_id, snapshot)

        assert counts["identities_created"] == 0
        assert counts["identities_updated"] == 4
        assert counts["access_records_created"] == 0
        assert counts["access_records_updated"] == 4

        # Same record imported twice stays one row (stable provider IDs).
        assert _count(db, Identity, connection_id) == 4
        assert _count(db, Resource, connection_id) == 2
        assert _count(db, AccessRecord, connection_id) == 4
