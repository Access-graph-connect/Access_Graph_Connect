"""Read-only operations dashboard (server-rendered).

Designed for non-technical viewers: plain-language labels, no jargon.
Every number is tenant-scoped and traceable to a provider source.
"""

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.db.models import (
    AccessRecord,
    Application,
    Identity,
    ProviderConnection,
    Resource,
    SyncRun,
)
from app.enums import RecordSource

_TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
# Disable the template cache: its LRU key can break on unhashable context.
_TEMPLATES.env.cache = None

router = APIRouter(tags=["dashboard"])


def _time_ago(dt: datetime | None) -> str:
    if dt is None:
        return "never"
    now = datetime.now(UTC)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
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
    tenant_id: Annotated[uuid.UUID, Query(description="Tenant to view")],
    db: Annotated[Session, Depends(get_db)],
) -> HTMLResponse:
    connections = list(
        db.scalars(
            select(ProviderConnection).where(ProviderConnection.tenant_id == tenant_id)
        ).all()
    )

    sources_by_connection: dict[str, set[RecordSource]] = {}
    for model in (Identity, Application, Resource, AccessRecord):
        for connection_id, source in db.execute(
            select(model.connection_id, model.source).where(
                model.tenant_id == tenant_id
            )
        ):
            sources_by_connection.setdefault(str(connection_id), set()).add(source)

    data_sources: dict[str, str] = {}
    for connection in connections:
        sources = sources_by_connection.get(str(connection.id), set())
        has_fixture = RecordSource.FIXTURE in sources
        has_live = bool(sources - {RecordSource.FIXTURE})
        if has_fixture and has_live:
            data_sources[str(connection.id)] = "Mixed sources"
        elif has_fixture:
            data_sources[str(connection.id)] = "Simulated data"
        elif has_live:
            data_sources[str(connection.id)] = "Live provider data"
        else:
            data_sources[str(connection.id)] = "No inventory yet"

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
        "applications": count(Application),
        "resources": count(Resource),
        "access_rules": count(AccessRecord),
        "stale": (
            count(Identity, stale=True)
            + count(Application, stale=True)
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
            "data_sources": data_sources,
            "latest_runs": latest_runs,
            "stats": stats,
            "recent_runs": recent_runs,
        },
    )
