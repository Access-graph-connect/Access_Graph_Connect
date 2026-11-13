"""Map Slack workspace users, channels, and memberships to the shared schema."""

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


def normalize_slack_payload(payload: Mapping[str, Any]) -> NormalizedSnapshot:
    workspace = payload.get("workspace") or {}
    observed_at = datetime.now(timezone.utc)
    coverage_notes = list(payload.get("coverage_notes") or [])

    identities: dict[str, NormalizedIdentity] = {}
    for user in payload.get("users", []):
        user_id = str(user["id"])
        profile = user.get("profile") or {}
        is_bot = user.get("is_bot")
        if is_bot is not True and user.get("is_app_user") is True:
            is_bot = True
        kind = (
            IdentityKind.BOT
            if is_bot is True
            else IdentityKind.HUMAN
            if is_bot is False
            else IdentityKind.UNKNOWN
        )
        deleted = user.get("deleted")
        is_active = not deleted if isinstance(deleted, bool) else None
        identities[user_id] = NormalizedIdentity(
            external_id=user_id,
            kind=kind,
            display_name=str(
                user.get("real_name")
                or profile.get("real_name")
                or profile.get("display_name")
                or user.get("name")
                or user_id
            ),
            email=profile.get("email"),
            is_active=is_active,
            source=RecordSource.API,
            observed_at=observed_at,
            raw=dict(user),
        )

    resources: list[NormalizedResource] = []
    access_records: list[NormalizedAccessRecord] = []
    for channel in payload.get("channels", []):
        channel_id = str(channel["id"])
        resources.append(
            NormalizedResource(
                external_id=channel_id,
                resource_type=ResourceType.CHANNEL,
                name=str(channel.get("name") or channel_id),
                source=RecordSource.API,
                observed_at=observed_at,
                raw=dict(channel),
            )
        )
        for member_id in (payload.get("memberships") or {}).get(channel_id, []):
            member_id = str(member_id)
            if member_id not in identities:
                coverage_notes.append(
                    f"Channel membership references user {member_id!r}, "
                    "which was not returned by users.list."
                )
                identities[member_id] = NormalizedIdentity(
                    external_id=member_id,
                    kind=IdentityKind.UNKNOWN,
                    display_name=member_id,
                    source=RecordSource.API,
                    observed_at=observed_at,
                    raw={},
                )
            access_records.append(
                NormalizedAccessRecord(
                    subject_external_id=member_id,
                    resource_external_id=channel_id,
                    permission="member",
                    origin=AccessOrigin.UNKNOWN,
                    source=RecordSource.API,
                    observed_at=observed_at,
                    evidence={
                        "channel_id": channel_id,
                        "channel_name": channel.get("name"),
                        "is_private": channel.get("is_private"),
                    },
                )
            )

    return NormalizedSnapshot(
        provider=Provider.SLACK,
        workspace_external_id=(
            str(workspace["id"]) if workspace.get("id") is not None else None
        ),
        source=RecordSource.API,
        identities=list(identities.values()),
        resources=resources,
        access_records=access_records,
        coverage_notes=coverage_notes,
    )
