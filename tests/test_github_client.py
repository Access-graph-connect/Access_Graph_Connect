import httpx
import pytest

from app.connectors.errors import AuthError, RateLimitError
from app.connectors.github import GitHubClient


def _client(handler) -> GitHubClient:
    return GitHubClient(token="test-token", transport=httpx.MockTransport(handler))


def test_pagination_follows_next_links_and_dedupes_nothing() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("page") == "2":
            return httpx.Response(
                200, json=[{"id": 3}, {"id": 2}]  # repeated item across pages
            )
        return httpx.Response(
            200,
            json=[{"id": 1}, {"id": 2}],
            headers={
                "link": '<https://api.github.com/items?page=2>; rel="next", '
                '<https://api.github.com/items?page=2>; rel="last"'
            },
        )

    with _client(handler) as client:
        items = list(client.paginate("/items"))

    # All pages loaded; dedup of repeated items is a persistence concern.
    assert [i["id"] for i in items] == [1, 2, 3, 2]


def test_pagination_unwraps_envelope_payloads() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"total_count": 2, "repositories": [{"id": 1}, {"id": 2}]}
        )

    with _client(handler) as client:
        items = list(client.paginate("/installation/repositories"))

    assert [i["id"] for i in items] == [1, 2]


def test_401_raises_auth_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "bad credentials"})

    with _client(handler) as client, pytest.raises(AuthError):
        list(client.paginate("/items"))


def test_403_with_exhausted_rate_limit_raises_rate_limit() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={"message": "API rate limit exceeded"},
            headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1730000000"},
        )

    with _client(handler) as client, pytest.raises(RateLimitError) as exc_info:
        list(client.paginate("/items"))
    assert exc_info.value.retry_after == 1730000000.0


def test_429_carries_retry_after() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429, json={"message": "secondary rate limit"}, headers={"retry-after": "30"}
        )

    with _client(handler) as client, pytest.raises(RateLimitError) as exc_info:
        list(client.paginate("/items"))
    assert exc_info.value.retry_after == 30.0
