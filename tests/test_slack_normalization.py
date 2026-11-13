from app.enums import AccessOrigin, IdentityKind, Provider, RecordSource, ResourceType
from app.normalization.slack import normalize_slack_payload


def test_slack_payload_normalizes_users_channels_and_memberships() -> None:
    payload = {
        "workspace": {"id": "T123", "name": "Test workspace"},
        "users": [
            {
                "id": "U1",
                "name": "alice",
                "real_name": "Alice Example",
                "deleted": False,
                "is_bot": False,
                "profile": {"email": "alice@example.test"},
            },
            {
                "id": "B1",
                "name": "helper",
                "deleted": True,
                "is_bot": True,
                "profile": {},
            },
        ],
        "channels": [
            {"id": "C1", "name": "general", "is_private": False},
        ],
        "memberships": {"C1": ["U1", "B1"]},
    }

    snapshot = normalize_slack_payload(payload)

    assert snapshot.provider is Provider.SLACK
    assert snapshot.workspace_external_id == "T123"
    assert snapshot.source is RecordSource.API
    users = {user.external_id: user for user in snapshot.identities}
    assert users["U1"].kind is IdentityKind.HUMAN
    assert users["U1"].display_name == "Alice Example"
    assert users["U1"].email == "alice@example.test"
    assert users["U1"].is_active is True
    assert users["B1"].kind is IdentityKind.BOT
    assert users["B1"].is_active is False
    assert snapshot.resources[0].resource_type is ResourceType.CHANNEL
    assert snapshot.resources[0].name == "general"
    assert len(snapshot.access_records) == 2
    assert snapshot.access_records[0].permission == "member"
    assert snapshot.access_records[0].origin is AccessOrigin.UNKNOWN


def test_membership_for_unknown_user_is_explicit_and_partial() -> None:
    snapshot = normalize_slack_payload(
        {
            "workspace": {"id": "T123"},
            "channels": [{"id": "C1", "name": "private-room"}],
            "memberships": {"C1": ["U-missing"]},
        }
    )

    assert snapshot.identities[0].kind is IdentityKind.UNKNOWN
    assert snapshot.identities[0].display_name == "U-missing"
    assert len(snapshot.access_records) == 1
    assert any("not returned by users.list" in note for note in snapshot.coverage_notes)
