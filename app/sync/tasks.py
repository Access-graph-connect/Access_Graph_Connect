"""Celery tasks.

The sync engine (checkpoints, retry budget, idempotent upserts,
reconciliation) is implemented in Phase 3; webhook-triggered ingestion
arrives in Phase 4.
"""

from app.sync.celery_app import celery_app


@celery_app.task
def ping() -> str:
    return "pong"
