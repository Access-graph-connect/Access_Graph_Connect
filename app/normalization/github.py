"""Mapping rules from GitHub API payloads to the unified schema.

GitHub-specific honesty rules:
- `role_name` on a collaborator is the provider role (admin/maintain/write/
  triage/read). It is recorded as the observed permission; whether it was
  granted directly on the repo or inherited from org/team membership is
  often not exposed, so origin is UNKNOWN unless the payload says otherwise.
- GitHub users do not expose "active" employment state -> is_active=None.
- Bots are identified via the provider's explicit `type: Bot`, never by
  name heuristics.
"""

from datetime import datetime, timezone
from typing import Any, Mapping

from app.enums import (
    AccessOrigin,
    IdentityKind,
    Provider,
    RecordSource,
    ResourceType,
)
from app.normalization.models import (
    NormalizedAccessRecord,
    NormalizedIdentity,
    NormalizedResource,
    NormalizedSnapshot,
)

_SOURCE = RecordSource.API


def _parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return datetime.now(timezone.utc)


def _identity_kind(user_type: str | None) -> IdentityKind:
    if user_type == "Bot":
        return IdentityKind.BOT
    if user_type == "User":
        return IdentityKind.HUMAN
    return IdentityKind.UNKNOWN


def _user_identity(user: Mapping[str, Any]) -> NormalizedIdentity:
    return NormalizedIdentity(
        external_id=str(user["id"]),
        kind=_identity_kind(user.get("type")),
        display_name=str(user.get("login") or user["id"]),
        email=user.get("email"),
        is_active=None,  # not observable via the GitHub API
        source=_SOURCE,
        observed_at=datetime.now(timezone.utc),
        raw=dict(user),
    )


def normalize_github_payload(payload: Mapping[str, Any]) -> NormalizedSnapshot:
    org = payload.get("org") or {}
    coverage_notes = list(payload.get("coverage_notes") or [])

    identities: dict[str, NormalizedIdentity] = {}
    for member in payload.get("members", []):
        identity = _user_identity(member)
        identities[identity.external_id] = identity

    resources: list[NormalizedResource] = []
    access_records: list[NormalizedAccessRecord] = []
    collaborators = payload.get("collaborators") or {}

    for repo in payload.get("repositories", []):
        repo_id = str(repo["id"])
        resources.append(
            NormalizedResource(
                external_id=repo_id,
                resource_type=ResourceType.REPOSITORY,
                name=str(repo.get("full_name") or repo.get("name") or repo_id),
                source=_SOURCE,
                observed_at=_parse_dt(repo.get("updated_at")),
                raw=dict(repo),
            )
        )
        for collab in collaborators.get(repo.get("full_name"), []):
            collab_id = str(collab["id"])
            if collab_id not in identities:
                identities[collab_id] = _user_identity(collab)
            role = collab.get("role_name")
            if not role:
                coverage_notes.append(
                    f"Permission role not exposed for collaborator "
                    f"{collab.get('login')!r} on {repo.get('full_name')!r}."
                )
                continue
            access_records.append(
                NormalizedAccessRecord(
                    subject_external_id=collab_id,
                    resource_external_id=repo_id,
                    permission=str(role),
                    # GitHub does not expose whether the role was granted
                    # directly on the repo or inherited from org/teams.
                    origin=AccessOrigin.UNKNOWN,
                    source=_SOURCE,
                    observed_at=datetime.now(timezone.utc),
                    evidence={
                        "repo": repo.get("full_name"),
                        "collaborator": collab.get("login"),
                        "role_name": role,
                        "permissions": collab.get("permissions"),
                    },
                )
            )

    return NormalizedSnapshot(
        provider=Provider.GITHUB,
        workspace_external_id=org.get("login"),
        source=_SOURCE,
        identities=list(identities.values()),
        applications=[],
        resources=resources,
        access_records=access_records,
        coverage_notes=coverage_notes,
    )
