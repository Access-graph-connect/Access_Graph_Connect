"""GitHub App installation flow.

POST /connections/github/start    -> redirect URL with signed state
GET  /connections/github/callback -> validate state, exchange installation
                                     token, persist connection + credential
                                     reference (never the token itself)
"""

import uuid
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_tenant_id
from app.api.schemas import ConnectionOut, GitHubStartOut
from app.config import get_settings
from app.db.models import ProviderConnection, Tenant
from app.enums import ConnectionStatus, Provider
from app.security.credentials import store_token
from app.security.github_app import exchange_installation_token
from app.security.oauth_state import InvalidStateError, sign_state, verify_state

router = APIRouter(tags=["github"])


@router.post("/connections/github/start", response_model=GitHubStartOut)
def start_github_installation(
    tenant_id: uuid.UUID = Depends(get_tenant_id),
) -> GitHubStartOut:
    settings = get_settings()
    if not settings.github_app_slug:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GitHub App is not configured (GITHUB_APP_SLUG missing)",
        )
    state = sign_state(tenant_id)
    query = urlencode({"state": state})
    return GitHubStartOut(
        install_url=(
            f"{settings.github_web_base}/apps/{settings.github_app_slug}"
            f"/installations/new?{query}"
        ),
        state=state,
    )


@router.get("/connections/github/callback", response_model=ConnectionOut)
def github_callback(
    state: str = Query(...),
    installation_id: int = Query(...),
    setup_action: str = Query(default="install"),
    db: Session = Depends(get_db),
) -> ProviderConnection:
    try:
        tenant_id = verify_state(state)
    except InvalidStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    settings = get_settings()
    try:
        token_response = exchange_installation_token(settings, installation_id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="installation token exchange failed",
        ) from exc

    token = token_response.get("token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="provider did not return an installation token",
        )

    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        tenant = Tenant(id=tenant_id, name=str(tenant_id))
        db.add(tenant)
        db.flush()

    credential_ref = store_token(db, token)
    scopes = sorted((token_response.get("permissions") or {}).keys())

    connection = db.scalar(
        select(ProviderConnection).where(
            ProviderConnection.tenant_id == tenant_id,
            ProviderConnection.provider == Provider.GITHUB,
            ProviderConnection.external_workspace_id == str(installation_id),
        )
    )
    if connection is None:
        connection = ProviderConnection(
            tenant_id=tenant_id,
            provider=Provider.GITHUB,
            external_workspace_id=str(installation_id),
        )
        db.add(connection)
    connection.scopes = scopes
    connection.status = ConnectionStatus.ACTIVE
    connection.credential_ref = credential_ref
    db.flush()

    return connection
