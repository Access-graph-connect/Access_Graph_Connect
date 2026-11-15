"""Provision the built-in simulated Notion connection for a local demo."""

import argparse
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import ProviderConnection, Tenant
from app.db.session import session_scope
from app.enums import ConnectionStatus, Provider
from app.sync.service import run_sync

_FIXTURE_WORKSPACE_ID = "ws-fixture-001"
_DEMO_TENANT_NAME = "AccessGraph demo"


def _get_or_create_fixture_connection(
    db: Session, tenant_id: uuid.UUID
) -> tuple[ProviderConnection, bool]:
    connection = db.scalar(
        select(ProviderConnection).where(
            ProviderConnection.tenant_id == tenant_id,
            ProviderConnection.provider == Provider.NOTION,
            ProviderConnection.external_workspace_id == _FIXTURE_WORKSPACE_ID,
        )
    )
    if connection is not None:
        return connection, False

    connection = ProviderConnection(
        tenant_id=tenant_id,
        provider=Provider.NOTION,
        external_workspace_id=_FIXTURE_WORKSPACE_ID,
        status=ConnectionStatus.ACTIVE,
    )
    db.add(connection)
    db.flush()
    return connection, True


def ensure_fixture_connection(tenant_id: uuid.UUID) -> tuple[uuid.UUID, bool]:
    with session_scope() as db:
        if db.get(Tenant, tenant_id) is None:
            raise ValueError(f"tenant {tenant_id} does not exist")
        connection, created = _get_or_create_fixture_connection(db, tenant_id)
        return connection.id, created


def provision_demo(
    tenant_id: uuid.UUID | None = None,
) -> tuple[uuid.UUID, uuid.UUID, str]:
    with session_scope() as db:
        if tenant_id is None:
            tenant = db.scalar(select(Tenant).where(Tenant.name == _DEMO_TENANT_NAME))
            if tenant is None:
                tenant = Tenant(name=_DEMO_TENANT_NAME)
                db.add(tenant)
                db.flush()
        else:
            tenant = db.get(Tenant, tenant_id)
            if tenant is None:
                raise ValueError(f"tenant {tenant_id} does not exist")

        connection, _ = _get_or_create_fixture_connection(db, tenant.id)
        run = run_sync(db, connection)
        return tenant.id, connection.id, run.status.value


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed and sync the built-in simulated Notion demo."
    )
    parser.add_argument(
        "--tenant-id",
        type=uuid.UUID,
        help="Use an existing tenant instead of the stable local demo tenant.",
    )
    args = parser.parse_args()
    get_settings()

    try:
        tenant_id, connection_id, sync_status = provision_demo(args.tenant_id)
    except ValueError as exc:
        parser.error(str(exc))

    print("Data source: simulated Notion fixture")
    print(f"Tenant ID: {tenant_id}")
    print(f"Connection ID: {connection_id}")
    print(f"Sync status: {sync_status}")
    print(f"Dashboard: http://127.0.0.1:8000/dashboard?tenant_id={tenant_id}")


if __name__ == "__main__":
    main()
