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
docker compose up --build -d
docker compose run --rm api python -m app.demo
# API: http://127.0.0.1:8000/healthz
# Dashboard URL and tenant ID are printed by the demo command.
```

Compose starts PostgreSQL, Redis, runs `alembic upgrade head`, then boots
the API and Celery worker. The demo command creates a stable local demo
tenant, seeds the simulated Notion fixture, and runs its first sync. Re-run
it safely to refresh the fixture inventory. The API port is published only
on loopback. GitHub Actions builds this Compose stack, checks health and
readiness, repeats the seed command, and verifies the dashboard label.

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

## Connecting Slack

1. Create a Slack app in your free workspace. Add the bot token scopes
   `users:read`, `users:read.email`, `channels:read`, and `groups:read`.
2. Provide an HTTPS redirect URL ending in `/connections/slack/callback`.
   Add it to the app's OAuth settings and set the identical URL as
   `SLACK_REDIRECT_URI` in `.env`. Slack requires HTTPS; a plain HTTP
   localhost URL is not sufficient.
3. Set `SLACK_CLIENT_ID`, `SLACK_CLIENT_SECRET`, `SLACK_SIGNING_SECRET`,
   `SECRET_KEY`, and `TOKEN_ENCRYPTION_KEY` in `.env`, then start or restart
   the API. Generate the encryption key as shown in `.env.example`.
4. Call `POST /connections/slack/start` with `X-Tenant-ID`, open the returned
   `authorize_url`, and approve installation. The callback stores only an
   encrypted bot token reference.
5. Run `POST /sync/{connection_id}` for the Slack connection and inspect
   identities, channels, memberships, and sync coverage notes as above.

The connector reads workspace users and visible public/private channels; it
does not read messages or join channels. Private channels the app cannot see
are reported as a coverage limitation, so those syncs remain partial and
won't stale previously known inventory. To enable Events API delivery, expose
`POST /webhooks/slack` over HTTPS and configure it as the app's event request
URL. Incoming events are signature-verified and deduplicated; scheduled/manual
sync remains the source of inventory updates.

For local development, an HTTPS tunnel or reverse proxy can forward the
callback to the API. The API trusts `X-Tenant-ID` and does not authenticate
requests, so do not expose the whole API publicly; restrict public access to
the OAuth callback (and, if needed, the webhook endpoint). Treat a tunnel
provider as a third party that can see the requests it forwards.

## Dashboard and simulated fixture

The operations dashboard is available at
`/dashboard?tenant_id=<TENANT_UUID>`. It shows inventory totals, connection
health, recent syncs, and whether each connection's inventory came from live
provider APIs or simulated fixture data.

The local demo command above prints a ready-to-open dashboard URL. To seed
the fixture into an existing tenant instead, pass
`--tenant-id <TENANT_UUID>` to `python -m app.demo`. The fixture is not a live
Notion integration, and its unknown permission origin may make the sync
status partial by design.

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
| 3 | Nov 2 | Sync engine and reconciliation | ✅ Reruns don't duplicate; partial sync can't erase known data |
| 4 | Nov 3 | Slack connector and webhooks | ✅ Live workspace sync; signed webhook receiver and deduplication tested |
| 5 | Nov 4 | Credential lifecycle and failure handling | In progress: encrypted vault and connection health transitions implemented |
| 6 | Nov 5 | Operations dashboard + fixture provider | ✅ Dashboard distinguishes live vs mock data |
| 7 | Nov 6 | Hardening, documentation, demo | ✅ Compose stack built and smoke-tested locally; limitations documented |

See `docs/design-decisions.md` for the engineering rules (explicit unknowns,
idempotent upserts, credentials by reference, webhook deduplication).
