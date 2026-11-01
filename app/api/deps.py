import uuid
from typing import Annotated

from fastapi import Header

from app.db.session import get_db

__all__ = ["get_db", "get_tenant_id"]


def get_tenant_id(
    x_tenant_id: Annotated[uuid.UUID, Header(alias="X-Tenant-ID")],
) -> uuid.UUID:
    """Resolve the tenancy isolation key from the request header.

    Every inventory/operations endpoint is tenant-scoped; cross-tenant
    queries must never return another tenant's objects.
    """
    return x_tenant_id
