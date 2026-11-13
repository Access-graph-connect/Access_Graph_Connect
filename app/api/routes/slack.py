"""Slack OAuth installation flow."""

import uuid
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_tenant_id
from app.api.schemas import ConnectionOut, SlackStartOut
from app.config import get_settings
from app.db.models import ProviderConnection, Tenant
from app.enums import ConnectionStatus, Provider
from app.security.credentials import store_token
from app.security.oauth_state import InvalidStateError, sign_state, verify_state
from app.security.slack_oauth import SlackOAuthError, exchange_oauth_code

router = APIRouter(tags=["slack"])
_BOT_SCOPES = "users:read,users:read.email,channels:read,groups:read"


@router.post("/connections/slack/start", response_model=SlackStartOut)
def start_slack_installation(
    tenant_id: uuid.UUID = Depends(get_tenant_id),
) -> SlackStartOut:
    settings = get_settings()
    if not settings.slack_client_id or not settings.slack_redirect_uri:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Slack app is not configured "
                "(SLACK_CLIENT_ID or SLACK_REDIRECT_URI missing)"
            ),
        )
    state = sign_state(tenant_id, purpose="slack")
    query = urlencode(
        {
            "client_id": settings.slack_client_id,
            "scope": _BOT_SCOPES,
            "redirect_uri": settings.slack_redirect_uri,
            "state": state,
        }
    )
    return SlackStartOut(
        authorize_url=f"https://slack.com/oauth/v2/authorize?{query}",
        state=state,
    )


@router.get("/connections/slack/callback", response_model=ConnectionOut)
def slack_callback(
    state: str = Query(...),
    code: str | None = Query(default=None),
    error: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> ProviderConnection:
    try:
        tenant_id = verify_state(state, purpose="slack")
    except InvalidStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="invalid OAuth state"
        ) from exc
    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Slack installation denied"
        )
    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="missing OAuth code"
        )

    settings = get_settings()
    if not settings.slack_client_secret or not settings.token_encryption_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Slack OAuth requires SLACK_CLIENT_SECRET and "
                "TOKEN_ENCRYPTION_KEY to be configured"
            ),
        )
    try:
        token_response = exchange_oauth_code(settings, code)
    except (SlackOAuthError, httpx.HTTPError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Slack OAuth token exchange failed",
        ) from exc

    token = token_response.get("access_token")
    team = token_response.get("team") or {}
    team_id = team.get("id")
    if not token or not team_id:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Slack did not return a bot token and workspace id",
        )

    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        tenant = Tenant(id=tenant_id, name=str(tenant_id))
        db.add(tenant)
        db.flush()

    connection = db.scalar(
        select(ProviderConnection).where(
            ProviderConnection.tenant_id == tenant_id,
            ProviderConnection.provider == Provider.SLACK,
            ProviderConnection.external_workspace_id == str(team_id),
        )
    )
    if connection is None:
        connection = ProviderConnection(
            tenant_id=tenant_id,
            provider=Provider.SLACK,
            external_workspace_id=str(team_id),
        )
        db.add(connection)
    connection.scopes = sorted(
        scope for scope in str(token_response.get("scope") or "").split(",") if scope
    )
    connection.settings = {"workspace_name": team.get("name")}
    connection.status = ConnectionStatus.ACTIVE
    connection.credential_ref = store_token(db, token)
    db.flush()
    return connection
