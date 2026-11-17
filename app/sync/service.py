"""Sync engine: fetch -> normalize -> upsert -> reconcile, with checkpoints.

Phase 3 behavior:
- Bounded retry with backoff around the provider fetch (never a tight loop).
- A SyncCursor records the last successful checkpoint per connection.
- Reconciliation marks genuinely-missing records stale ONLY on a complete
  sync (no coverage gaps). A partial/interrupted sync never erases known
  data.
- Every run is recorded as a SyncRun with counts, status, and error class.
"""

from datetime import UTC, datetime, timedelta

import httpx
from jwt.exceptions import PyJWTError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.connectors.base import ConnectionContext
from app.connectors.errors import AuthError, ConnectorError, RateLimitError
from app.connectors.fixture import FixtureConnector
from app.connectors.github import GitHubConnector
from app.connectors.slack import SlackConnector
from app.db.models import ProviderConnection, SyncCursor, SyncRun
from app.enums import ConnectionStatus, Provider, SyncStatus, SyncTrigger
from app.normalization.models import NormalizedSnapshot
from app.security.credentials import (
    CredentialError,
    replace_connection_token,
    retrieve_token,
)
from app.security.github_app import exchange_installation_token, parse_token_expiry
from app.sync.persist import upsert_snapshot
from app.sync.reconcile import reconcile
from app.sync.retry import RetryPolicy, run_with_retry


class SyncError(RuntimeError):
    pass


_GITHUB_TOKEN_RENEWAL_WINDOW = timedelta(minutes=5)


def _retry_after_seconds(response: httpx.Response) -> float | None:
    value = response.headers.get("retry-after")
    return float(value) if value and value.isdigit() else None


def _github_connector(connection: ProviderConnection, db: Session) -> GitHubConnector:
    if not connection.credential_ref:
        raise CredentialError("connection has no credential reference")

    token = retrieve_token(db, connection.credential_ref)
    expires_at = connection.credential_expires_at
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if (
        expires_at is None
        or expires_at <= datetime.now(UTC) + _GITHUB_TOKEN_RENEWAL_WINDOW
    ):
        try:
            installation_id = int(connection.external_workspace_id or "")
        except ValueError as exc:
            raise SyncError("GitHub connection has an invalid installation id") from exc

        try:
            response = exchange_installation_token(get_settings(), installation_id)
        except httpx.HTTPStatusError as exc:
            if (
                exc.response.status_code == 403
                and exc.response.headers.get("x-ratelimit-remaining") == "0"
            ):
                raise RateLimitError(
                    "GitHub token renewal was rate limited",
                    retry_after=_retry_after_seconds(exc.response),
                ) from exc
            if exc.response.status_code in (401, 403):
                raise AuthError(
                    "GitHub App authentication failed during token renewal"
                ) from exc
            if exc.response.status_code == 429:
                raise RateLimitError(
                    "GitHub token renewal was rate limited",
                    retry_after=_retry_after_seconds(exc.response),
                ) from exc
            raise ConnectorError("GitHub installation token renewal failed") from exc
        except (httpx.HTTPError, PyJWTError, TypeError, ValueError) as exc:
            raise ConnectorError("GitHub installation token renewal failed") from exc

        replacement = response.get("token") if isinstance(response, dict) else None
        if not isinstance(replacement, str) or not replacement:
            raise ConnectorError("GitHub token renewal returned no installation token")
        try:
            expires_at = parse_token_expiry(response)
        except ValueError as exc:
            raise ConnectorError("GitHub token renewal returned an invalid expiry") from exc

        replace_connection_token(db, connection, replacement)
        connection.credential_expires_at = expires_at
        token = replacement

    return GitHubConnector(token)


def _build_connector(connection: ProviderConnection, db: Session):
    if connection.provider is Provider.NOTION:
        return FixtureConnector()
    if connection.provider is Provider.GITHUB:
        return _github_connector(connection, db)
    if connection.provider is Provider.SLACK:
        if not connection.credential_ref:
            raise CredentialError("connection has no credential reference")
        token = retrieve_token(db, connection.credential_ref)
        return SlackConnector(token, api_base=get_settings().slack_api_base)
    raise SyncError(f"no live connector for provider {connection.provider!r}")


def _get_or_create_cursor(db: Session, connection: ProviderConnection) -> SyncCursor:
    cursor = db.scalar(
        select(SyncCursor).where(SyncCursor.connection_id == connection.id)
    )
    if cursor is None:
        cursor = SyncCursor(connection_id=connection.id, provider=connection.provider)
        db.add(cursor)
        db.flush()
    return cursor


def run_sync(
    db: Session,
    connection: ProviderConnection,
    trigger: SyncTrigger = SyncTrigger.MANUAL,
    retry_policy: RetryPolicy | None = None,
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

    cursor = _get_or_create_cursor(db, connection)

    try:
        connector = _build_connector(connection, db)
        context = ConnectionContext(
            tenant_id=connection.tenant_id,
            connection_id=connection.id,
            credential_ref=connection.credential_ref,
            settings=connection.settings or {},
        )

        # Bounded retry around the fetch; auth errors surface immediately.
        payload = run_with_retry(
            lambda: connector.fetch_snapshot(context), policy=retry_policy
        )
        snapshot: NormalizedSnapshot = connector.normalize(payload)

        counts = upsert_snapshot(db, connection.tenant_id, connection.id, snapshot)

        # A sync is "complete" only when there were no coverage gaps.
        complete = not snapshot.coverage_notes
        recon_counts = reconcile(db, connection.id, snapshot, complete=complete)
        counts.update(recon_counts)

        run.counts = {**counts, "coverage_notes": len(snapshot.coverage_notes)}
        run.status = SyncStatus.SUCCEEDED if complete else SyncStatus.PARTIAL
        if complete:
            cursor.last_success_at = datetime.now(UTC)
            cursor.cursor = snapshot.workspace_external_id
            connection.status = ConnectionStatus.ACTIVE
        else:
            connection.status = ConnectionStatus.DEGRADED
    except AuthError as exc:
        run.status = SyncStatus.FAILED
        run.error_code = "auth"
        run.error_detail = str(exc)[:1000]
        connection.status = ConnectionStatus.RECONNECT_REQUIRED
    except CredentialError as exc:
        run.status = SyncStatus.FAILED
        run.error_code = "credential"
        run.error_detail = str(exc)[:1000]
        connection.status = ConnectionStatus.RECONNECT_REQUIRED
    except SyncError as exc:
        run.status = SyncStatus.FAILED
        run.error_code = "connector"
        run.error_detail = str(exc)[:1000]
        connection.status = ConnectionStatus.DEGRADED
    except RateLimitError as exc:
        run.status = SyncStatus.FAILED
        run.error_code = "rate_limit"
        run.error_detail = str(exc)[:1000]
        connection.status = ConnectionStatus.DEGRADED
    except ConnectorError as exc:
        run.status = SyncStatus.FAILED
        run.error_code = "connector"
        run.error_detail = str(exc)[:1000]
        connection.status = ConnectionStatus.DEGRADED
    finally:
        run.finished_at = datetime.now(UTC)
        db.flush()

    return run
