# Design decisions

## Phase 1 — architecture, environment, schema

- **D1 — Read-only scope.** The platform discovers and inventories access; it
  never writes back to providers. Revocation, suspension, approvals, and
  AI-driven remediation belong to Project 1 (Guardian AI) and are
  intentionally absent.
- **D2 — One connector complete and trustworthy.** GitHub is the primary
  connector, Slack secondary, Notion fixture-only. Depth (pagination,
  recovery, honest coverage) beats adapter count.
- **D3 — Unknowns are explicit, never inferred.** `IdentityKind.UNKNOWN`,
  `AccessOrigin.UNKNOWN`, and `is_active = NULL` are first-class states. We
  never merge identities across apps because names look similar, and never
  claim a permission is direct when the provider does not expose its origin.
- **D4 — Scope, role, and grant stay separate.** OAuth scope = what a token
  may request (stored on `ProviderConnection.scopes`); role = a
  provider-defined permission bundle; grant = observed access
  (`AccessRecord`). They are never conflated.
- **D5 — Credentials by reference only.** `ProviderConnection.credential_ref`
  points at a secret store; token material is never stored in the database,
  logged, or returned by the API. Encryption at rest arrives in Phase 5.
- **D6 — Idempotent upsert keys.** Inventory rows are keyed by
  `(connection_id, external_id)`; access records by
  `(connection_id, subject, resource, app, permission)`. Re-importing the
  same record keeps one row. Resource/app ids use `""` rather than NULL so
  the composite unique constraint actually deduplicates.
- **D7 — Portable column types.** `sa.Uuid`, `sa.JSON`, and non-native enums
  let the same Alembic migrations run on PostgreSQL (deployment) and SQLite
  (tests), so migration behavior is testable without Docker.
- **D8 — Webhook inbox deduplicates.** `(provider, delivery_id)` is unique;
  signatures are verified against the raw body before any state change
  (Phase 4). Replays are processed at most once.
- **D9 — Provenance on every row.** `source` (api/webhook/fixture),
  `observed_at`, and raw evidence travel with each record so the UI can show
  freshness and distinguish live data from simulated data.
- **D10 — Async sync via Celery + Redis.** The API stays read-only and thin;
  polling, reconciliation, and webhook-triggered ingestion run as tasks
  (Phase 3+).
