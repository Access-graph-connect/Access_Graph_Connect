# Architecture

```
Provider APIs (GitHub, Slack; optional Notion fixtures)
  →  OAuth installation and provider-specific connector adapters
  →  Worker queue / polling scheduler / verified webhook receiver
  →  Normalization and reconciliation engine
  →  PostgreSQL: provider connections, identities, apps, resources,
     grants, sync runs, event inbox
  →  FastAPI read-only inventory API and operations dashboard
```

## Components

| Component | Module | Status |
| --- | --- | --- |
| Read-only API | `app/api/` | Health/readiness + tenant-scoped `GET /connections` |
| Connectors | `app/connectors/` | GitHub and Slack read-only adapters + fixture connector |
| Fixture connector | `app/connectors/fixture.py` | JSON fixture → normalized snapshot |
| Normalization | `app/normalization/` | Unified schema + GitHub, Slack, and fixture mappings |
| Persistence | `app/db/` | SQLAlchemy models + Alembic migrations |
| Worker queue | `app/sync/` | Celery app + sync engine for GitHub and Slack |
| Security | `app/security/` | Signed OAuth state, credential vault, GitHub/Slack webhook verification |
| Dashboard | `app/dashboard/` | Placeholder (Phase 6) |

## Schema

`tenants` → `provider_connections` → inventory tables (`identities`,
`applications`, `resources`, `access_records`) and operations tables
(`sync_runs`, `sync_cursors`, `webhook_inbox`, `connector_events`).

Every inventory row carries `tenant_id` (isolation key), `provider`,
`external_id`, `source`, `observed_at`, and raw evidence. Upserts are
idempotent on `(connection_id, external_id)`.

## Deployment

`docker-compose.yml` runs PostgreSQL, Redis, a one-shot `migrate` service
(`alembic upgrade head`), the FastAPI `api`, and a Celery `worker`.
