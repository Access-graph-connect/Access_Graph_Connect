import json
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from app.db.models import ProviderConnection, Tenant
from app.db.session import session_scope
from app.enums import ConnectionStatus, Provider, SyncStatus
from app.main import app
from app.normalization.github import normalize_github_payload
from app.sync.persist import upsert_snapshot
from app.sync.service import run_sync

client = TestClient(app)
GITHUB_PAYLOAD = json.loads(
    (Path(__file__).parent / "fixtures" / "github_payload.json").read_text(
        encoding="utf-8"
    )
)


def test_dashboard_labels_live_and_simulated_data() -> None:
    tenant_id = uuid.uuid4()
    with session_scope() as db:
        db.add(Tenant(id=tenant_id, name=f"dashboard-{tenant_id.hex[:8]}"))
        live_connection = ProviderConnection(
            tenant_id=tenant_id,
            provider=Provider.GITHUB,
            external_workspace_id="dashboard-live-org",
            status=ConnectionStatus.ACTIVE,
        )
        fixture_connection = ProviderConnection(
            tenant_id=tenant_id,
            provider=Provider.NOTION,
            external_workspace_id="ws-fixture-001",
            status=ConnectionStatus.ACTIVE,
        )
        db.add_all([live_connection, fixture_connection])
        db.flush()

        upsert_snapshot(
            db,
            tenant_id,
            live_connection.id,
            normalize_github_payload(GITHUB_PAYLOAD),
        )
        run = run_sync(db, fixture_connection)
        assert run.status is SyncStatus.PARTIAL
        assert run.counts["coverage_notes"] == 1

    response = client.get("/dashboard", params={"tenant_id": str(tenant_id)})

    assert response.status_code == 200
    assert "Live provider data" in response.text
    assert "Simulated data" in response.text
    assert "AccessGraph Connect" in response.text


def test_dashboard_tenant_scope_excludes_other_tenant_data() -> None:
    tenant_id = uuid.uuid4()
    other_tenant_id = uuid.uuid4()
    with session_scope() as db:
        db.add_all(
            [
                Tenant(id=tenant_id, name=f"dashboard-{tenant_id.hex[:8]}"),
                Tenant(id=other_tenant_id, name=f"dashboard-{other_tenant_id.hex[:8]}"),
            ]
        )
        db.add(
            ProviderConnection(
                tenant_id=other_tenant_id,
                provider=Provider.NOTION,
                external_workspace_id="ws-fixture-001",
                status=ConnectionStatus.ACTIVE,
            )
        )

    response = client.get("/dashboard", params={"tenant_id": str(tenant_id)})

    assert response.status_code == 200
    assert "No apps connected yet." in response.text
    assert "Simulated data" not in response.text
