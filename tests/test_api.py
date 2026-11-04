import json
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from app.db.models import ProviderConnection, Tenant
from app.db.session import session_scope
from app.enums import ConnectionStatus, Provider
from app.main import app
from app.normalization.github import normalize_github_payload
from app.sync.persist import upsert_snapshot

client = TestClient(app)

PAYLOAD = json.loads(
    (Path(__file__).parent / "fixtures" / "github_payload.json").read_text(
        encoding="utf-8"
    )
)


def test_healthz() -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readyz() -> None:
    response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"


def test_connections_requires_tenant_header() -> None:
    response = client.get("/connections")
    assert response.status_code == 422


def test_connections_scoped_to_tenant() -> None:
    response = client.get("/connections", headers={"X-Tenant-ID": str(uuid.uuid4())})
    assert response.status_code == 200
    assert response.json() == []


def _seed_inventory() -> tuple[uuid.UUID, uuid.UUID]:
    tenant_id = uuid.uuid4()
    with session_scope() as db:
        db.add(Tenant(id=tenant_id, name=f"tenant-{tenant_id.hex[:8]}"))
        connection = ProviderConnection(
            tenant_id=tenant_id,
            provider=Provider.GITHUB,
            external_workspace_id="acme-test-org",
            status=ConnectionStatus.ACTIVE,
        )
        db.add(connection)
        db.flush()
        upsert_snapshot(
            db, tenant_id, connection.id, normalize_github_payload(PAYLOAD)
        )
        return tenant_id, connection.id


def test_inventory_endpoints_return_tenant_data() -> None:
    tenant_id, _ = _seed_inventory()
    headers = {"X-Tenant-ID": str(tenant_id)}

    identities = client.get("/inventory/identities", headers=headers)
    assert identities.status_code == 200
    assert len(identities.json()) == 4
    assert all("observed_at" in row for row in identities.json())

    resources = client.get("/inventory/resources", headers=headers)
    assert resources.status_code == 200
    assert {r["name"] for r in resources.json()} == {
        "acme-test-org/api-service",
        "acme-test-org/web-app",
    }

    access = client.get("/inventory/access", headers=headers)
    assert access.status_code == 200
    assert len(access.json()) == 4
    assert all(row["origin"] == "unknown" for row in access.json())


def test_inventory_never_leaks_across_tenants() -> None:
    tenant_id, _ = _seed_inventory()
    other = {"X-Tenant-ID": str(uuid.uuid4())}

    for path in ("/inventory/identities", "/inventory/resources", "/inventory/access"):
        response = client.get(path, headers=other)
        assert response.status_code == 200
        assert response.json() == []


def test_sync_trigger_unknown_connection_404() -> None:
    response = client.post(
        f"/sync/{uuid.uuid4()}", headers={"X-Tenant-ID": str(uuid.uuid4())}
    )
    assert response.status_code == 404


def test_sync_trigger_cross_tenant_connection_404() -> None:
    tenant_id, connection_id = _seed_inventory()
    response = client.post(
        f"/sync/{connection_id}", headers={"X-Tenant-ID": str(uuid.uuid4())}
    )
    assert response.status_code == 404


def test_sync_without_credential_records_failed_run() -> None:
    tenant_id, connection_id = _seed_inventory()
    headers = {"X-Tenant-ID": str(tenant_id)}

    response = client.post(f"/sync/{connection_id}", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["error_code"] == "connector"

    runs = client.get("/sync-runs", headers=headers)
    assert runs.status_code == 200
    assert len(runs.json()) == 1
    assert runs.json()[0]["error_code"] == "connector"
