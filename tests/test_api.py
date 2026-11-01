import uuid

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


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
