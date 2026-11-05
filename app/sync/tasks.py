"""Celery tasks: scheduled/triggered syncs run through the sync engine."""

import uuid

from app.db.models import ProviderConnection
from app.db.session import session_scope
from app.enums import SyncTrigger
from app.sync.celery_app import celery_app
from app.sync.service import run_sync


@celery_app.task
def ping() -> str:
    return "pong"


@celery_app.task(name="sync.run_connection")
def run_connection_sync(connection_id: str, trigger: str = "schedule") -> str:
    """Run a sync for one connection. Returns the resulting SyncRun status."""
    with session_scope() as db:
        connection = db.get(ProviderConnection, uuid.UUID(connection_id))
        if connection is None:
            return "connection_not_found"
        run = run_sync(db, connection, trigger=SyncTrigger(trigger))
        return run.status.value
