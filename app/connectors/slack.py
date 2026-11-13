"""Read-only Slack workspace connector."""

from typing import Any, Iterator, Mapping

import httpx

from app.connectors.base import ConnectionContext
from app.connectors.errors import (
    AuthError,
    ConnectorError,
    ProviderDataError,
    RateLimitError,
)
from app.enums import Provider
from app.normalization.models import NormalizedSnapshot
from app.normalization.slack import normalize_slack_payload

_INACCESSIBLE_CONVERSATION_ERRORS = {
    "access_denied",
    "channel_not_found",
    "not_in_channel",
    "restricted_action",
}
_AUTH_ERRORS = {
    "account_inactive",
    "invalid_auth",
    "not_authed",
    "token_revoked",
}


class SlackAPIError(ConnectorError):
    def __init__(self, code: str) -> None:
        super().__init__(f"Slack API error: {code}")
        self.code = code


class SlackClient:
    """Slack Web API client with cursor pagination and error classification."""

    def __init__(
        self,
        token: str,
        api_base: str = "https://slack.com/api",
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.Client(
            base_url=api_base.rstrip("/") + "/",
            headers={"Authorization": f"Bearer {token}"},
            transport=transport,
            timeout=30.0,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "SlackClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def call(self, method: str, params: Mapping[str, Any] | None = None) -> dict[str, Any]:
        try:
            response = self._client.get(method, params=params)
        except httpx.HTTPError as exc:
            raise ConnectorError("Slack API request failed") from exc
        if response.status_code == 429:
            retry_after = _retry_after(response.headers.get("retry-after"))
            raise RateLimitError("Slack rate limit exceeded", retry_after=retry_after)
        if response.status_code in (401, 403):
            raise AuthError(f"Slack authentication failed: {response.status_code}")
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ConnectorError(
                f"Slack API returned HTTP {response.status_code}"
            ) from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderDataError(f"invalid JSON from Slack method {method}") from exc
        if not isinstance(payload, dict):
            raise ProviderDataError(f"unexpected response from Slack method {method}")
        if payload.get("ok") is not True:
            code = str(payload.get("error") or "unknown_error")
            if code in _AUTH_ERRORS or code == "missing_scope":
                raise AuthError(f"Slack authorization failed: {code}")
            if code == "ratelimited":
                raise RateLimitError(
                    "Slack rate limit exceeded",
                    retry_after=_retry_after(response.headers.get("retry-after")),
                )
            raise SlackAPIError(code)
        return payload

    def paginate(
        self,
        method: str,
        result_key: str,
        params: Mapping[str, Any] | None = None,
        item_type: type | tuple[type, ...] = dict,
    ) -> Iterator[Any]:
        cursor: str | None = None
        while True:
            request_params = {"limit": 200, **(params or {})}
            if cursor:
                request_params["cursor"] = cursor
            payload = self.call(method, request_params)
            items = payload.get(result_key)
            if not isinstance(items, list):
                raise ProviderDataError(
                    f"missing {result_key!r} list from Slack method {method}"
                )
            if any(not isinstance(item, item_type) for item in items):
                raise ProviderDataError(
                    f"unexpected item in {result_key!r} from Slack method {method}"
                )
            yield from items
            metadata = payload.get("response_metadata") or {}
            next_cursor = metadata.get("next_cursor") if isinstance(metadata, dict) else None
            cursor = str(next_cursor) if next_cursor else None
            if not cursor:
                return


class SlackConnector:
    provider = Provider.SLACK

    def __init__(
        self,
        token: str,
        api_base: str = "https://slack.com/api",
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._token = token
        self._api_base = api_base
        self._transport = transport

    def fetch_snapshot(self, context: ConnectionContext) -> Mapping[str, Any]:
        coverage_notes = [
            "Slack only exposes conversations available to the installed app; "
            "private channels the app has not joined are not covered."
        ]
        with SlackClient(
            self._token, api_base=self._api_base, transport=self._transport
        ) as client:
            auth = client.call("auth.test")
            team_id = auth.get("team_id")
            if not team_id:
                raise ProviderDataError("Slack auth.test did not return a team id")

            users = list(client.paginate("users.list", "members"))
            channels = list(
                client.paginate(
                    "conversations.list",
                    "channels",
                    params={
                        "types": "public_channel,private_channel",
                        "exclude_archived": "false",
                    },
                )
            )
            memberships: dict[str, list[str]] = {}
            for channel in channels:
                channel_id = channel.get("id")
                if not channel_id or channel.get("is_archived"):
                    continue
                try:
                    memberships[str(channel_id)] = list(
                        client.paginate(
                            "conversations.members",
                            "members",
                            params={"channel": str(channel_id)},
                            item_type=str,
                        )
                    )
                except SlackAPIError as exc:
                    if exc.code not in _INACCESSIBLE_CONVERSATION_ERRORS:
                        raise
                    coverage_notes.append(
                        f"Memberships are not visible for channel "
                        f"{channel.get('name') or channel_id}."
                    )

        return {
            "provider": "slack",
            "workspace": {"id": str(team_id), "name": auth.get("team")},
            "users": users,
            "channels": channels,
            "memberships": memberships,
            "coverage_notes": coverage_notes,
        }

    def normalize(self, payload: Mapping[str, Any]) -> NormalizedSnapshot:
        return normalize_slack_payload(payload)


def _retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None
