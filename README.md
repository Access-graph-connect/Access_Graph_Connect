# AccessGraph Connect

A read-only SaaS access-discovery and connector-operations platform.
It connects to third-party SaaS services, imports identities and access
metadata, normalizes differences between providers, keeps the inventory
synchronized, and makes connector failures visible.

**Out of scope by design:** AI security agents, risk scoring, graph
reasoning, approval workflows, revocation, suspension, and automated
remediation.

## Quickstart (Docker)

```sh
cp .env.example .env
docker compose up --build
# API: http://localhost:8000/healthz  (docs at /docs)
```

Compose starts PostgreSQL, Redis, runs `alembic upgrade head`, then boots
the API and Celery worker.

## Local development

```sh
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -e .[dev]

# Point at a database (SQLite works for tests; Postgres for real runs)
set DATABASE_URL=sqlite:///./local.db
alembic upgrade head
uvicorn app.main:app --reload
pytest
```

## Connecting GitHub

1. Create a GitHub App with read-only permissions (Members, Contents) and
   note its id, slug, and private key.
2. Set `GITHUB_APP_ID`, `GITHUB_APP_SLUG`, `GITHUB_APP_PRIVATE_KEY`, and
   `TOKEN_ENCRYPTION_KEY` in `.env`.
3. `POST /connections/github/start` (header `X-Tenant-ID`) → open the
   returned `install_url` and install the app into your test org.
4. GitHub redirects to `GET /connections/github/callback`, which validates
   the signed state, exchanges the installation token, and stores it
   encrypted in the credential vault (only a reference is kept on the
   connection).
5. `POST /sync/{connection_id}` runs a read-only sync; inspect results via
   `GET /inventory/identities`, `GET /inventory/resources`,
   `GET /inventory/access`, and `GET /sync-runs`.

## Layout

```
app/api/            FastAPI routes (read-only, tenant-scoped via X-Tenant-ID)
app/connectors/     base.py protocol, fixture.py; github.py (P2), slack.py (P4)
app/normalization/  unified schema and provider mapping rules
app/sync/           Celery workers, cursors, reconciliation (P3)
app/security/       OAuth state, token references, webhook verification (P2/P4/P5)
app/db/             SQLAlchemy models, Alembic migrations
app/dashboard/      read-only ops UI (P6)
tests/              fixtures and failure cases
docs/               architecture, design decisions, provider matrix, demo script
```

## Build phases

| Phase | Day | Focus | Definition of done |
| --- | --- | --- | --- |
| 1 | Oct 31 | Architecture, environment, schema | ✅ API boots; migrations run; one sample fixture normalized |
| 2 | Nov 1 | GitHub connector end-to-end | ✅ Live GitHub inventory with source timestamps |
| 3 | Nov 2 | Sync engine and reconciliation | Reruns don't duplicate; partial sync can't erase known data |
| 4 | Nov 3 | Slack connector and webhooks | Slack data loads; invalid signatures rejected |
| 5 | Nov 4 | Credential lifecycle and failure handling | Degraded / reconnect-required states accurate |
| 6 | Nov 5 | Operations dashboard + fixture provider | Dashboard distinguishes live vs mock data |
| 7 | Nov 6 | Hardening, documentation, demo | Reproducible Docker demo + documented limitations |

See `docs/design-decisions.md` for the engineering rules (explicit unknowns,
idempotent upserts, credentials by reference, webhook deduplication).
