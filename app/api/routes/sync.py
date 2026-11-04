"""Sync triggers and run history, tenant-scoped."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_tenant_id
from app.api.schemas import SyncRunOut
from app.db.models import ProviderConnection, SyncRun
from app.enums import SyncTrigger
from app.sync.service import run_sync

router = APIRouter(tags=["sync"])


@router.post("/sync/{connection_id}", response_model=SyncRunOut)
def trigger_sync(
    connection_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> SyncRun:
    connection = db.get(ProviderConnection, connection_id)
    if connection is None or connection.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="connection not found"
        )
    return run_sync(db, connection, trigger=SyncTrigger.MANUAL)


@router.get("/sync-runs", response_model=list[SyncRunOut])
def list_sync_runs(
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> list[SyncRun]:
    return list(
        db.scalars(
            select(SyncRun)
            .where(SyncRun.tenant_id == tenant_id)
            .order_by(SyncRun.started_at.desc())
        ).all()
    )
