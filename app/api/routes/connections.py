import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_tenant_id
from app.api.schemas import ConnectionOut
from app.db.models import ProviderConnection

router = APIRouter(tags=["connections"])


@router.get("/connections", response_model=list[ConnectionOut])
def list_connections(
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> list[ProviderConnection]:
    """Connection health and scope inventory for the requesting tenant."""
    return list(
        db.scalars(
            select(ProviderConnection).where(ProviderConnection.tenant_id == tenant_id)
        ).all()
    )
