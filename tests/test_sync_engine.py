import json
import uuid
from pathlib import Path

from sqlalchemy import select

from app.db.models import ProviderConnection, SyncCursor, Tenant
from app.db.session import session_scope
from app.enums import ConnectionStatus, Provider, SyncStatus
from app.sync.retry import RetryPolicy
from app.sync.service import run_sync

PAYLOAD = json.loads(
    (Path(__file__).parent / "fixtures" / "github_payload.json").read_text(
        encoding="utf-8"
    )
)


class _StubConnector:
    """Returns a fixed payload; lets us drive run_sync without network."""

    def __init__(self, payload):
        self._payload = payload

    def fetch_snapshot(self, context):
        return self._payload

    def normalize(self, payload):
        from app.normalization.github import normalize_github_payload

        return normalize_github_payload(payload)


def _seed_connection() -> tuple[uuid.UUID, uuid.UUID]:
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


def _run_with_stub(monkeypatch, connection_id, payload):
    from app.sync import service

    stub = _StubConnector(payload)
    monkeypatch.setattr(service, "_build_connector", lambda conn, db: stub)

    with session_scope() as db:
        conn = db.get(ProviderConnection, connection_id)
        return run_sync(db, conn, retry_policy=RetryPolicy(max_attempts=1))


def test_complete_sync_sets_cursor_and_succeeds(monkeypatch) -> None:
    _, conn_id = _seed_connection()
    # Give every collaborator a role so there are no coverage gaps.
    complete = json.loads(json.dumps(PAYLOAD))
    for collabs in complete["collaborators"].values():
        for c in collabs:
            c.setdefault("role_name", "read")
    run = _run_with_stub(monkeypatch, conn_id, complete)

    assert run.status == SyncStatus.SUCCEEDED
    with session_scope() as db:
        conn = db.get(ProviderConnection, conn_id)
        assert conn.status is ConnectionStatus.ACTIVE
        cursor = db.scalar(
            select(SyncCursor).where(SyncCursor.connection_id == conn_id)
        )
        assert cursor is not None
        assert cursor.last_success_at is not None
        assert cursor.cursor == "acme-test-org"


def test_partial_sync_does_not_advance_cursor(monkeypatch) -> None:
    _, conn_id = _seed_connection()
    partial = {**PAYLOAD, "coverage_notes": ["members not visible"]}
    run = _run_with_stub(monkeypatch, conn_id, partial)

    assert run.status == SyncStatus.PARTIAL
    with session_scope() as db:
        conn = db.get(ProviderConnection, conn_id)
        assert conn.status is ConnectionStatus.DEGRADED
        cursor = db.scalar(
            select(SyncCursor).where(SyncCursor.connection_id == conn_id)
        )
        assert cursor.last_success_at is None


def test_interrupted_sync_keeps_known_data(monkeypatch) -> None:
    _tenant_id, conn_id = _seed_connection()
    # First: a complete successful sync.
    _run_with_stub(monkeypatch, conn_id, PAYLOAD)

    # Second: a failing sync (empty payload would stale everything if reconciled).
    from app.connectors.errors import ConnectorError
    from app.sync import service

    def boom(conn, db):
        raise ConnectorError("network down")

    monkeypatch.setattr(service, "_build_connector", boom)
    with session_scope() as db:
        conn = db.get(ProviderConnection, conn_id)
        run = run_sync(db, conn, retry_policy=RetryPolicy(max_attempts=1))
        assert run.status == SyncStatus.FAILED
        assert run.error_code == "connector"
        assert conn.status is ConnectionStatus.DEGRADED

    # Known data must be intact (not staled, not deleted).
    from app.db.models import Identity, Resource

    with session_scope() as db:
        identities = db.scalars(
            select(Identity).where(Identity.connection_id == conn_id)
        ).all()
        resources = db.scalars(
            select(Resource).where(Resource.connection_id == conn_id)
        ).all()
        assert len(identities) == 4
        assert len(resources) == 2
        assert all(not i.is_stale for i in identities)
        assert all(not r.is_stale for r in resources)


def test_auth_failure_requires_reconnect(monkeypatch) -> None:
    _, conn_id = _seed_connection()
    from app.connectors.errors import AuthError
    from app.sync import service

    def auth_failure(conn, db):
        raise AuthError("provider rejected token")

    monkeypatch.setattr(service, "_build_connector", auth_failure)
    with session_scope() as db:
        conn = db.get(ProviderConnection, conn_id)
        run = run_sync(db, conn, retry_policy=RetryPolicy(max_attempts=1))
        assert run.status is SyncStatus.FAILED
        assert run.error_code == "auth"
        assert conn.status is ConnectionStatus.RECONNECT_REQUIRED


def test_missing_credential_requires_reconnect(monkeypatch) -> None:
    _, conn_id = _seed_connection()
    with session_scope() as db:
        conn = db.get(ProviderConnection, conn_id)
        run = run_sync(db, conn, retry_policy=RetryPolicy(max_attempts=1))
        assert run.status is SyncStatus.FAILED
        assert run.error_code == "credential"
        assert conn.status is ConnectionStatus.RECONNECT_REQUIRED


def test_credential_resolution_failure_requires_reconnect(monkeypatch) -> None:
    _, conn_id = _seed_connection()
    from app.security.credentials import CredentialError
    from app.sync import service

    def credential_failure(conn, db):
        raise CredentialError("credential cannot be decrypted")

    monkeypatch.setattr(service, "_build_connector", credential_failure)
    with session_scope() as db:
        conn = db.get(ProviderConnection, conn_id)
        run = run_sync(db, conn, retry_policy=RetryPolicy(max_attempts=1))
        assert run.status is SyncStatus.FAILED
        assert run.error_code == "credential"
        assert conn.status is ConnectionStatus.RECONNECT_REQUIRED


def test_rerun_does_not_duplicate(monkeypatch) -> None:
    _, conn_id = _seed_connection()
    _run_with_stub(monkeypatch, conn_id, PAYLOAD)
    run2 = _run_with_stub(monkeypatch, conn_id, PAYLOAD)

    assert run2.counts["identities_created"] == 0
    assert run2.counts["identities_updated"] == 4

    from app.db.models import Identity

    with session_scope() as db:
        count = len(
            db.scalars(select(Identity).where(Identity.connection_id == conn_id)).all()
        )
        assert count == 4
