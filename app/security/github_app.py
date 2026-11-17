"""GitHub App authentication: JWT signing and installation token exchange."""

import time
from datetime import UTC, datetime
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


def parse_token_expiry(token_response: dict[str, Any]) -> datetime:
    """Parse GitHub's non-secret installation-token expiry metadata."""
    value = token_response.get("expires_at")
    if not isinstance(value, str):
        raise ValueError("GitHub did not return an installation token expiry")
    try:
        expiry = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("GitHub returned an invalid installation token expiry") from exc
    if expiry.tzinfo is None:
        raise ValueError("GitHub returned a timezone-naive installation token expiry")
    return expiry.astimezone(UTC)
