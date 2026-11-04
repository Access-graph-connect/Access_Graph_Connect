"""GitHub read-only connector.

Discovers, with an installation access token:
- the installed organization/workspace and app installation metadata
- organization members (when the Members permission allows)
- repositories visible to the installation
- per-repository collaborators and their permission roles

Boundaries (surfaced as coverage notes, never silently dropped):
- Permission origin may be inherited (org-level vs repo-level); GitHub does
  not always expose which, so origin is UNKNOWN unless explicit.
- Discovery depends on the app's permissions and org settings; a 403 on an
  endpoint narrows coverage rather than failing the whole snapshot.
"""

from typing import Any, Iterator, Mapping

import httpx

from app.config import Settings, get_settings
from app.connectors.base import ConnectionContext
from app.connectors.errors import AuthError, ProviderDataError, RateLimitError
from app.enums import Provider
from app.normalization.github import normalize_github_payload
from app.normalization.models import NormalizedSnapshot

_API_VERSION = "2022-11-28"


class GitHubClient:
    """Minimal httpx wrapper: installation-token auth + Link pagination."""

    def __init__(
        self,
        token: str,
        settings: Settings | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._client = httpx.Client(
            base_url=self._settings.github_api_base,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": _API_VERSION,
            },
            transport=transport,
            timeout=30.0,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "GitHubClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _check(self, response: httpx.Response) -> None:
        if response.status_code in (401, 403):
            remaining = response.headers.get("x-ratelimit-remaining")
            if response.status_code == 403 and remaining == "0":
                raise RateLimitError(
                    "github rate limit exceeded",
                    retry_after=_retry_after(response),
                )
            raise AuthError(f"github auth failed: {response.status_code}")
        if response.status_code == 429:
            raise RateLimitError(
                "github secondary rate limit", retry_after=_retry_after(response)
            )
        response.raise_for_status()

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        response = self._client.get(path, params=params)
        self._check(response)
        return response.json()

    def paginate(self, path: str, params: dict[str, Any] | None = None) -> Iterator[dict[str, Any]]:
        """Yield items across all pages, following Link: rel="next"."""
        url: str | None = path
        merged = {"per_page": 100, **(params or {})}
        while url:
            response = self._client.get(url, params=merged if url == path else None)
            self._check(response)
            body = response.json()
            # List endpoints return arrays; some wrap items in a key
            # (e.g. /installation/repositories -> {"repositories": [...]}).
            if isinstance(body, list):
                items = body
            elif isinstance(body, dict):
                items = next(
                    (v for v in body.values() if isinstance(v, list)), None
                )
                if items is None:
                    raise ProviderDataError(f"no list payload at {path}")
            else:
                raise ProviderDataError(f"unexpected payload at {path}")
            yield from items
            url = _next_link(response.headers.get("link"))


def _next_link(link_header: str | None) -> str | None:
    if not link_header:
        return None
    for part in link_header.split(","):
        segments = part.split(";")
        if len(segments) == 2 and 'rel="next"' in segments[1]:
            return segments[0].strip().strip("<>")
    return None


def _retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get("retry-after")
    if value and value.isdigit():
        return float(value)
    reset = response.headers.get("x-ratelimit-reset")
    return float(reset) if reset and reset.isdigit() else None


class GitHubConnector:
    provider = Provider.GITHUB

    def __init__(
        self,
        token: str,
        settings: Settings | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._token = token
        self._settings = settings or get_settings()
        self._transport = transport

    def fetch_snapshot(self, context: ConnectionContext) -> Mapping[str, Any]:
        coverage_notes: list[str] = []
        with GitHubClient(
            self._token, settings=self._settings, transport=self._transport
        ) as client:
            installation = client.get("/installation/repositories", params={"per_page": 1})
            repos = list(client.paginate("/installation/repositories"))

            org_login = None
            if repos:
                owner = repos[0].get("owner") or {}
                if owner.get("type") == "Organization":
                    org_login = owner.get("login")

            members: list[dict[str, Any]] = []
            if org_login:
                try:
                    members = list(client.paginate(f"/orgs/{org_login}/members"))
                except AuthError:
                    coverage_notes.append(
                        "Org members not visible to this installation; "
                        "member discovery skipped."
                    )

            collaborators: dict[str, list[dict[str, Any]]] = {}
            for repo in repos:
                full_name = repo.get("full_name")
                if not full_name:
                    continue
                try:
                    collaborators[full_name] = list(
                        client.paginate(
                            f"/repos/{full_name}/collaborators",
                            params={"affiliation": "all"},
                        )
                    )
                except AuthError:
                    coverage_notes.append(
                        f"Collaborators not visible for {full_name}; "
                        "access records for this repo are incomplete."
                    )

        return {
            "provider": "github",
            "installation": {
                "repositories_total": installation.get("total_count"),
                "repository_selection": installation.get("repository_selection"),
            },
            "org": {"login": org_login},
            "members": members,
            "repositories": repos,
            "collaborators": collaborators,
            "coverage_notes": coverage_notes,
        }

    def normalize(self, payload: Mapping[str, Any]) -> NormalizedSnapshot:
        return normalize_github_payload(payload)
