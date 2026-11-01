import json
from pathlib import Path

from app.connectors.base import ConnectionContext
from app.connectors.fixture import FixtureConnector
from app.enums import AccessOrigin, IdentityKind, Provider, RecordSource, ResourceType
from app.normalization.mapping import normalize_fixture_payload

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "notion_fixture.json"


def _load() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_fixture_normalizes_into_unified_schema() -> None:
    snapshot = normalize_fixture_payload(_load())

    assert snapshot.provider is Provider.NOTION
    assert snapshot.workspace_external_id == "ws-fixture-001"
    assert snapshot.source is RecordSource.FIXTURE

    assert len(snapshot.identities) == 3
    kinds = {i.external_id: i.kind for i in snapshot.identities}
    assert kinds == {
        "user-001": IdentityKind.HUMAN,
        "user-002": IdentityKind.HUMAN,
        "bot-001": IdentityKind.BOT,
    }

    assert len(snapshot.applications) == 1
    assert snapshot.applications[0].external_id == "int-001"
    assert snapshot.applications[0].installed_at is not None

    assert len(snapshot.resources) == 2
    assert all(r.resource_type is ResourceType.PAGE for r in snapshot.resources)

    assert len(snapshot.access_records) == 3


def test_unknowns_are_explicit_never_inferred() -> None:
    snapshot = normalize_fixture_payload(_load())
    by_subject = {a.subject_external_id: a for a in snapshot.access_records}

    # Grant without an origin in the payload must be marked unknown.
    assert by_subject["bot-001"].origin is AccessOrigin.UNKNOWN
    assert by_subject["user-001"].origin is AccessOrigin.DIRECT
    assert by_subject["user-002"].origin is AccessOrigin.INHERITED

    # Activity not observable stays None, not guessed.
    user2 = next(i for i in snapshot.identities if i.external_id == "user-002")
    assert user2.is_active is None

    # Coverage limitations are surfaced, not silently dropped.
    assert any("simulated" in note for note in snapshot.coverage_notes)
    assert any("unknown" in note for note in snapshot.coverage_notes)


def test_access_record_targets_resource_or_app() -> None:
    snapshot = normalize_fixture_payload(_load())
    by_subject = {a.subject_external_id: a for a in snapshot.access_records}

    assert by_subject["user-001"].resource_external_id == "page-001"
    assert by_subject["user-001"].app_external_id == ""
    assert by_subject["user-002"].app_external_id == "int-001"
    assert by_subject["user-002"].resource_external_id == ""


def test_fixture_connector_satisfies_protocol() -> None:
    connector = FixtureConnector(FIXTURE_PATH)
    assert connector.provider is Provider.NOTION

    context = ConnectionContext(
        tenant_id="00000000-0000-0000-0000-000000000001",
        connection_id="00000000-0000-0000-0000-000000000002",
    )
    payload = connector.fetch_snapshot(context)
    snapshot = connector.normalize(payload)
    assert len(snapshot.identities) == 3
