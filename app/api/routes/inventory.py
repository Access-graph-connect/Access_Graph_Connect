"""Read-only unified inventory endpoints, always tenant-scoped."""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_tenant_id
from app.api.schemas import AccessRecordOut, IdentityOut, ResourceOut
from app.db.models import AccessRecord, Identity, Resource

router = APIRouter(prefix="/inventory", tags=["inventory"])


@router.get("/identities", response_model=list[IdentityOut])
def list_identities(
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> list[Identity]:
    return list(
        db.scalars(select(Identity).where(Identity.tenant_id == tenant_id)).all()
    )


@router.get("/resources", response_model=list[ResourceOut])
def list_resources(
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> list[Resource]:
    return list(
        db.scalars(select(Resource).where(Resource.tenant_id == tenant_id)).all()
    )


@router.get("/access", response_model=list[AccessRecordOut])
def list_access(
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> list[AccessRecord]:
    return list(
        db.scalars(
            select(AccessRecord).where(AccessRecord.tenant_id == tenant_id)
        ).all()
    )
