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

## Phase 2 — GitHub connector

- **D11 — GitHub App, not OAuth app/PAT.** Installation tokens are
  short-lived, scoped, and carry their own permission inventory
  (`permissions` from the token exchange is stored as
  `ProviderConnection.scopes`).
- **D12 — Installation state is HMAC-signed and short-lived** (10 min),
  binding the callback to the tenant that started the install.
- **D13 — Tokens live in `credential_vault`, referenced by id.** Ciphertext
  never appears in API responses, logs, or `ProviderConnection` rows.
- **D14 — Permission origin is UNKNOWN on GitHub.** `role_name` is recorded
  as the observed permission, but GitHub does not expose whether it was
  granted directly on the repo or inherited from org/teams — we never claim
  `direct`.
- **D15 — Coverage degrades, not fails.** A 403 on org members or repo
  collaborators narrows the snapshot and adds a coverage note (SyncRun
  becomes `partial`); it does not fail the whole sync.
- **D16 — Error classification at the client boundary.** 401/403 →
  `AuthError`; 429 / 403-with-exhausted-quota → `RateLimitError` carrying
  `Retry-After`. Phases 3 and 5 branch on these categories.

## Phase 3 — sync engine and reconciliation

- **D17 — Bounded retry, never a tight loop.** Provider fetches retry at
  most `max_attempts` with exponential backoff + full jitter; `Retry-After`
  from the provider takes precedence. Auth errors are never retried.
- **D18 — Partial sync never erases known data.** Reconciliation only marks
  records stale when the snapshot is *complete* (zero coverage gaps). An
  interrupted or degraded sync leaves existing rows untouched.
- **D19 — Stale is soft, never hard-deleted.** Reconciled-away records get
  `is_stale=True` + `reconciled_at`; they stay in the DB for audit and can
  be *revived* if they reappear in a later complete sync.
- **D20 — Checkpoint per connection.** `SyncCursor.last_success_at` advances
  only on a complete successful sync, so a later partial sync can't mask a
  gap as progress.

## Phase 4 — Slack connector

- **D21 — Slack bot-token scopes stay read-only and narrow.** The connector
  requests users and public/private channel metadata plus channel membership;
  it never reads messages or joins channels.
- **D22 — Slack visibility gaps remain partial.** Slack only returns
  conversations available to the installed app. Private channels the app
  cannot see are called out as a coverage limitation, preventing incomplete
  snapshots from staling previously observed records.
- **D23 — Slack Events API verifies the raw signed request.** Request
  timestamps are limited to a five-minute window, and event IDs use the
  shared webhook inbox uniqueness key to deduplicate retries.
