"""Fixture-backed connector.

Reads a provider-shaped JSON document from disk and normalizes it. Used for
the simulated Notion adapter and for reproducible tests. Fixture data must
always be labeled as simulated, never presented as live provider data.
"""

import json
from pathlib import Path
from typing import Any, Mapping

from app.connectors.base import ConnectionContext
from app.enums import Provider
from app.normalization.mapping import normalize_fixture_payload
from app.normalization.models import NormalizedSnapshot


class FixtureConnector:
    def __init__(self, fixture_path: str | Path) -> None:
        self._fixture_path = Path(fixture_path)

    @property
    def provider(self) -> Provider:
        payload = json.loads(self._fixture_path.read_text(encoding="utf-8"))
        return Provider(payload["provider"])

    def fetch_snapshot(self, context: ConnectionContext) -> Mapping[str, Any]:
        return json.loads(self._fixture_path.read_text(encoding="utf-8"))

    def normalize(self, payload: Mapping[str, Any]) -> NormalizedSnapshot:
        return normalize_fixture_payload(payload)
