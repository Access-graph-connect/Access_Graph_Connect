import uuid

import httpx

from app.connectors.base import ConnectionContext
from app.connectors.slack import SlackConnector
from app.normalization.models import NormalizedSnapshot


def test_slack_connector_fetches_users_channels_and_memberships() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/auth.test"):
            return httpx.Response(
                200,
                json={"ok": True, "team_id": "T1", "team": "Test workspace"},
            )
        if request.url.path.endswith("/users.list"):
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "members": [
                        {
                            "id": "U1",
                            "name": "alice",
                            "is_bot": False,
                            "deleted": False,
                            "profile": {},
                        }
                    ],
                },
            )
        if request.url.path.endswith("/conversations.list"):
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "channels": [
                        {"id": "C1", "name": "general", "is_private": False}
                    ],
                },
            )
        if request.url.path.endswith("/conversations.members"):
            assert request.url.params["channel"] == "C1"
            return httpx.Response(200, json={"ok": True, "members": ["U1"]})
        raise AssertionError(f"unexpected Slack API call: {request.url}")

    connector = SlackConnector(
        "xoxb-test-token", transport=httpx.MockTransport(handler)
    )
    context = ConnectionContext(
        tenant_id=uuid.uuid4(),
        connection_id=uuid.uuid4(),
    )

    snapshot = connector.normalize(connector.fetch_snapshot(context))

    assert isinstance(snapshot, NormalizedSnapshot)
    assert snapshot.workspace_external_id == "T1"
    assert [resource.external_id for resource in snapshot.resources] == ["C1"]
    assert [
        (record.subject_external_id, record.resource_external_id)
        for record in snapshot.access_records
    ] == [("U1", "C1")]
    assert any("private channels" in note for note in snapshot.coverage_notes)
