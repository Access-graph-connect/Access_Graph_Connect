import json
from pathlib import Path

from app.enums import AccessOrigin, IdentityKind, Provider, RecordSource, ResourceType
from app.normalization.github import normalize_github_payload

PAYLOAD = json.loads(
    (Path(__file__).parent / "fixtures" / "github_payload.json").read_text(
        encoding="utf-8"
    )
)


def test_github_payload_normalizes() -> None:
    snapshot = normalize_github_payload(PAYLOAD)

    assert snapshot.provider is Provider.GITHUB
    assert snapshot.workspace_external_id == "acme-test-org"
    assert snapshot.source is RecordSource.API

    # 3 org members + 1 outside collaborator discovered via repo listing
    assert len(snapshot.identities) == 4
    by_id = {i.external_id: i for i in snapshot.identities}
    assert by_id["1001"].kind is IdentityKind.HUMAN
    assert by_id["1003"].kind is IdentityKind.BOT
    assert by_id["1004"].display_name == "outside-collab"

    assert len(snapshot.resources) == 2
    assert all(r.resource_type is ResourceType.REPOSITORY for r in snapshot.resources)

    # 3 grants on api-service; web-app has 1 (collaborator without role skipped)
    assert len(snapshot.access_records) == 4


def test_permission_origin_is_unknown_not_direct() -> None:
    snapshot = normalize_github_payload(PAYLOAD)
    # GitHub does not expose grant origin -> never claim direct.
    assert all(a.origin is AccessOrigin.UNKNOWN for a in snapshot.access_records)
    assert all(a.is_active is None for a in snapshot.identities)


def test_missing_role_surfaces_coverage_note() -> None:
    snapshot = normalize_github_payload(PAYLOAD)
    assert any("outside-collab" in note for note in snapshot.coverage_notes)


def test_access_records_carry_evidence() -> None:
    snapshot = normalize_github_payload(PAYLOAD)
    grant = next(
        a for a in snapshot.access_records if a.subject_external_id == "1001"
        and a.resource_external_id == "2001"
    )
    assert grant.permission == "admin"
    assert grant.evidence["repo"] == "acme-test-org/api-service"
    assert grant.observed_at is not None
