"""Slack OAuth v2 code exchange."""

from typing import Any

import httpx

from app.config import Settings


class SlackOAuthError(RuntimeError):
    """Slack rejected an OAuth code exchange."""


def exchange_oauth_code(
    settings: Settings,
    code: str,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    owns_client = client is None
    client = client or httpx.Client(
        base_url=settings.slack_api_base.rstrip("/") + "/", timeout=30.0
    )
    try:
        response = client.post(
            "oauth.v2.access",
            data={
                "client_id": settings.slack_client_id,
                "client_secret": settings.slack_client_secret,
                "code": code,
                "redirect_uri": settings.slack_redirect_uri,
            },
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or payload.get("ok") is not True:
            error = payload.get("error", "invalid_response") if isinstance(payload, dict) else "invalid_response"
            raise SlackOAuthError(f"Slack OAuth exchange failed: {error}")
        return payload
    finally:
        if owns_client:
            client.close()
