"""Synchronous sync runner for Phase 2.

Runs fetch -> normalize -> upsert inside one SyncRun lifecycle. The Celery
worker, checkpoints, retry budget, backoff, and reconciliation arrive in
Phase 3; this service is the seam they will plug into.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.connectors.errors import AuthError, ConnectorError, RateLimitError
from app.connectors.github import GitHubConnector
from app.db.models import ProviderConnection, SyncRun
from app.enums import Provider, SyncStatus, SyncTrigger
from app.normalization.models import NormalizedSnapshot
from app.security.credentials import retrieve_token
from app.sync.persist import upsert_snapshot


class SyncError(RuntimeError):
    pass


def _build_connector(connection: ProviderConnection, db: Session):
    if connection.provider is Provider.GITHUB:
        if not connection.credential_ref:
            raise SyncError("connection has no credential reference")
        token = retrieve_token(db, connection.credential_ref)
        return GitHubConnector(token)
    raise SyncError(f"no live connector for provider {connection.provider!r}")


def run_sync(
    db: Session,
    connection: ProviderConnection,
    trigger: SyncTrigger = SyncTrigger.MANUAL,
) -> SyncRun:
    run = SyncRun(
        tenant_id=connection.tenant_id,
        connection_id=connection.id,
        provider=connection.provider,
        status=SyncStatus.RUNNING,
        trigger=trigger,
    )
    db.add(run)
    db.flush()

    try:
        connector = _build_connector(connection, db)
        from app.connectors.base import ConnectionContext

        context = ConnectionContext(
            tenant_id=connection.tenant_id,
            connection_id=connection.id,
            credential_ref=connection.credential_ref,
        )
        payload = connector.fetch_snapshot(context)
        snapshot: NormalizedSnapshot = connector.normalize(payload)
        counts = upsert_snapshot(db, connection.tenant_id, connection.id, snapshot)
        run.counts = {**counts, "coverage_notes": len(snapshot.coverage_notes)}
        run.status = (
            SyncStatus.PARTIAL if snapshot.coverage_notes else SyncStatus.SUCCEEDED
        )
    except AuthError as exc:
        run.status = SyncStatus.FAILED
        run.error_code = "auth"
        run.error_detail = str(exc)[:1000]
    except RateLimitError as exc:
        run.status = SyncStatus.FAILED
        run.error_code = "rate_limit"
        run.error_detail = str(exc)[:1000]
    except (ConnectorError, SyncError) as exc:
        run.status = SyncStatus.FAILED
        run.error_code = "connector"
        run.error_detail = str(exc)[:1000]
    finally:
        run.finished_at = datetime.now(timezone.utc)
        db.flush()

    return run
