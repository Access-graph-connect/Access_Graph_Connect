import httpx
import pytest

from app.connectors.errors import AuthError, ConnectorError, RateLimitError
from app.connectors.slack import SlackAPIError, SlackClient


def test_pagination_uses_slack_cursor_metadata() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("cursor") == "next":
            return httpx.Response(200, json={"ok": True, "members": [{"id": "U2"}]})
        return httpx.Response(
            200,
            json={
                "ok": True,
                "members": [{"id": "U1"}],
                "response_metadata": {"next_cursor": "next"},
            },
        )

    with SlackClient(
        "xoxb-test-token", transport=httpx.MockTransport(handler)
    ) as client:
        members = list(client.paginate("users.list", "members"))

    assert [member["id"] for member in members] == ["U1", "U2"]


def test_api_auth_error_raises_auth_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": False, "error": "missing_scope"})

    with SlackClient("xoxb-test-token", transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(AuthError):
            client.call("users.list")


def test_conversation_error_keeps_provider_error_code() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": False, "error": "not_in_channel"})

    with SlackClient("xoxb-test-token", transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(SlackAPIError, match="not_in_channel") as exc_info:
            client.call("conversations.members")
    assert exc_info.value.code == "not_in_channel"


def test_http_rate_limit_carries_retry_after() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "30"})

    with SlackClient("xoxb-test-token", transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(RateLimitError) as exc_info:
            client.call("users.list")
    assert exc_info.value.retry_after == 30


def test_http_server_error_is_classified_as_connector_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    with SlackClient("xoxb-test-token", transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ConnectorError, match="Slack API returned HTTP 503"):
            client.call("users.list")
