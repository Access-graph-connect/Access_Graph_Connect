"""GitHub App authentication: JWT signing and installation token exchange."""

import time
from typing import Any

import httpx
import jwt

from app.config import Settings


def create_app_jwt(settings: Settings) -> str:
    now = int(time.time())
    payload = {
        "iat": now - 60,  # clock-skew allowance
        "exp": now + 540,  # GitHub allows at most 10 minutes
        "iss": settings.github_app_id,
    }
    return jwt.encode(
        payload, settings.github_app_private_key_pem, algorithm="RS256"
    )


def exchange_installation_token(
    settings: Settings,
    installation_id: int,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Exchange an installation id for an installation access token.

    Returns the provider response containing `token`, `expires_at`, and the
    granted `permissions` (scope inventory).
    """
    app_jwt = create_app_jwt(settings)
    owns_client = client is None
    client = client or httpx.Client(base_url=settings.github_api_base)
    try:
        response = client.post(
            f"/app/installations/{installation_id}/access_tokens",
            headers={
                "Authorization": f"Bearer {app_jwt}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        response.raise_for_status()
        return response.json()
    finally:
        if owns_client:
            client.close()
