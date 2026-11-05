"""Webhook receiver: verify signature, dedupe, record in the inbox.

- Signature is verified against the raw body before anything is stored.
- (provider, delivery_id) is unique, so a replayed delivery is recorded as
  a duplicate and processed at most once.
- Actual ingestion/enqueueing into the sync engine arrives with Phase 3/4;
  for now valid deliveries are marked received and acknowledged.
"""

import hashlib

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.config import get_settings
from app.db.models import WebhookInbox
from app.enums import Provider, WebhookStatus
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
