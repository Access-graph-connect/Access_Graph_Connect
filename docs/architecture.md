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
| Worker queue | `app/sync/` | Celery app + sync engine for GitHub, Slack, and the Notion fixture |
| Security | `app/security/` | Signed OAuth state, credential vault, GitHub/Slack webhook verification |
| Dashboard | `app/dashboard/` | Tenant-scoped operations view with live/simulated provenance labels |

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

## Security and demo limitations

The Compose setup is for local demonstration only: its API port binds to
`127.0.0.1`, access logging is disabled to avoid recording OAuth callback
query parameters, and its fallback signing key is explicitly non-production.
Set a unique `SECRET_KEY` and a valid Fernet `TOKEN_ENCRYPTION_KEY` before
running with `ENVIRONMENT=production`; startup rejects missing or invalid
production keys. Generate these values with:

```sh
python -c "import secrets; print(secrets.token_urlsafe(32))"
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

The API currently takes `X-Tenant-ID` directly from the request and does not
authenticate users or authorize tenant membership. Loopback binding limits
the demo's network exposure but is not a substitute for authentication.
Do not expose this service to a network or use it for multi-user or
production workloads until authentication, tenant authorization, TLS
termination, and production secret management are provided. Slack OAuth
requires an HTTPS callback and is not part of the HTTP-only Compose demo.

The Notion adapter is a deterministic fixture, not a live provider
integration. Its synthetic records are labeled simulated, and any unknown
permission origin remains a coverage limitation.

The `Compose demo` GitHub Actions workflow builds and starts the Compose
stack, checks API health/readiness, runs the fixture seeder twice to verify
idempotency, and checks that the tenant dashboard labels its records as
simulated. The local Compose demo itself remains intended for development,
not production deployment.
