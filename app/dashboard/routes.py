"""Read-only operations dashboard (server-rendered).

Designed for non-technical viewers: plain-language labels, no jargon.
Every number is tenant-scoped and traceable to a provider source.
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from pathlib import Path

from app.api.deps import get_db
from app.db.models import (
    AccessRecord,
    Identity,
    ProviderConnection,
    Resource,
    SyncRun,
)

_TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
# Disable the template cache: its LRU key can break on unhashable context.
_TEMPLATES.env.cache = None

router = APIRouter(tags=["dashboard"])


def _time_ago(dt: datetime | None) -> str:
    if dt is None:
        return "never"
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    seconds = int((now - dt).total_seconds())
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{seconds // 60} min ago"
    if seconds < 86400:
        return f"{seconds // 3600} hr ago"
    return f"{seconds // 86400} days ago"


_TEMPLATES.env.filters["time_ago"] = _time_ago


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(
    request: Request,
    tenant_id: uuid.UUID = Query(..., description="Tenant to view"),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    connections = list(
        db.scalars(
            select(ProviderConnection).where(ProviderConnection.tenant_id == tenant_id)
        ).all()
    )

    # Latest sync run per connection for freshness/status display.
    # Keyed by str(id) so Jinja2 dict lookups work cleanly.
    latest_runs: dict[str, SyncRun] = {}
    for run in db.scalars(
        select(SyncRun)
        .where(SyncRun.tenant_id == tenant_id)
        .order_by(SyncRun.started_at.desc())
    ).all():
        latest_runs.setdefault(str(run.connection_id), run)

    def count(model, stale: bool = False) -> int:
        return db.scalar(
            select(func.count())
            .select_from(model)
            .where(model.tenant_id == tenant_id, model.is_stale.is_(stale))
        ) or 0

    stats = {
        "people": count(Identity),
        "resources": count(Resource),
        "access_rules": count(AccessRecord),
        "stale": (
            count(Identity, stale=True)
            + count(Resource, stale=True)
            + count(AccessRecord, stale=True)
        ),
    }

    recent_runs = list(
        db.scalars(
            select(SyncRun)
            .where(SyncRun.tenant_id == tenant_id)
            .order_by(SyncRun.started_at.desc())
            .limit(10)
        ).all()
    )

    return _TEMPLATES.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "tenant_id": tenant_id,
            "connections": connections,
            "latest_runs": latest_runs,
            "stats": stats,
            "recent_runs": recent_runs,
        },
    )
