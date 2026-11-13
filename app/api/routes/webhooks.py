"""Webhook receiver: verify signature, dedupe, record in the inbox.

- Signature is verified against the raw body before anything is stored.
- (provider, delivery_id) is unique, so a replayed delivery is recorded as
  a duplicate and processed at most once.
- Actual ingestion/enqueueing into the sync engine arrives with Phase 3/4;
  for now valid deliveries are marked received and acknowledged.
"""

import hashlib
import json

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.config import get_settings
from app.db.models import ProviderConnection, WebhookInbox
from app.enums import Provider, WebhookStatus
from app.security.slack_webhook import verify_slack_signature
from app.security.webhook_verify import verify_github_signature

router = APIRouter(tags=["webhooks"])


@router.post("/webhooks/github")
async def github_webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(default=None),
    x_github_delivery: str | None = Header(default=None),
    x_github_event: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    body = await request.body()
    settings = get_settings()

    if not x_github_delivery:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="missing X-GitHub-Delivery header",
        )

    valid = verify_github_signature(
        settings.github_webhook_secret, body, x_hub_signature_256
    )
    if not valid:
        # Invalid signature never changes state.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid signature"
        )

    inbox = WebhookInbox(
        provider=Provider.GITHUB,
        delivery_id=x_github_delivery,
        signature_valid=True,
        payload_hash=hashlib.sha256(body).hexdigest(),
        status=WebhookStatus.RECEIVED,
    )
    db.add(inbox)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        # Delivery id already recorded -> replay; processed at most once.
        return {"status": WebhookStatus.DUPLICATE.value}

    # Phase 3/4: enqueue ingestion into the sync engine here.
    return {"status": WebhookStatus.RECEIVED.value, "event": x_github_event or ""}


@router.post("/webhooks/slack")
async def slack_webhook(
    request: Request,
    x_slack_signature: str | None = Header(default=None),
    x_slack_request_timestamp: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    body = await request.body()
    settings = get_settings()
    if not verify_slack_signature(
        settings.slack_signing_secret,
        body,
        x_slack_signature,
        x_slack_request_timestamp,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid signature"
        )

    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="invalid JSON body"
        ) from exc
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="invalid event payload"
        )

    if payload.get("type") == "url_verification":
        challenge = payload.get("challenge")
        if not isinstance(challenge, str):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="missing Slack URL verification challenge",
            )
        return {"challenge": challenge}
    if payload.get("type") != "event_callback":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="unsupported Slack event"
        )

    event_id = payload.get("event_id")
    if not isinstance(event_id, str) or not event_id or len(event_id) > 200:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="missing Slack event id"
        )

    connection = None
    team_id = payload.get("team_id")
    if isinstance(team_id, str):
        matching_connections = db.scalars(
            select(ProviderConnection)
            .where(
                ProviderConnection.provider == Provider.SLACK,
                ProviderConnection.external_workspace_id == team_id,
            )
            .limit(2)
        ).all()
        if len(matching_connections) == 1:
            connection = matching_connections[0]
    inbox = WebhookInbox(
        tenant_id=connection.tenant_id if connection else None,
        connection_id=connection.id if connection else None,
        provider=Provider.SLACK,
        delivery_id=event_id,
        signature_valid=True,
        payload_hash=hashlib.sha256(body).hexdigest(),
        status=WebhookStatus.RECEIVED,
    )
    db.add(inbox)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return {"status": WebhookStatus.DUPLICATE.value}

    return {"status": WebhookStatus.RECEIVED.value}
