import uuid

import pytest

from app.db.models import Tenant
from app.db.session import session_scope
from app.demo import ensure_fixture_connection, provision_demo
from app.enums import SyncStatus


def test_fixture_connection_creation_is_idempotent() -> None:
    tenant_id = uuid.uuid4()
    with session_scope() as db:
        db.add(Tenant(id=tenant_id, name=f"demo-{tenant_id.hex[:8]}"))

    connection_id, created = ensure_fixture_connection(tenant_id)
    repeated_id, repeated_created = ensure_fixture_connection(tenant_id)

    assert created is True
    assert repeated_created is False
    assert repeated_id == connection_id


def test_fixture_connection_requires_existing_tenant() -> None:
    with pytest.raises(ValueError, match="does not exist"):
        ensure_fixture_connection(uuid.uuid4())


def test_demo_provisioning_is_repeatable_and_syncs_fixture() -> None:
    tenant_id, connection_id, status = provision_demo()
    repeated_tenant_id, repeated_connection_id, repeated_status = provision_demo()

    assert tenant_id == repeated_tenant_id
    assert connection_id == repeated_connection_id
    assert status == SyncStatus.PARTIAL.value
    assert repeated_status == SyncStatus.PARTIAL.value
