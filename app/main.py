from fastapi import FastAPI

from app.api.routes import connections, github, health, inventory, slack, sync, webhooks
from app.config import get_settings
from app.dashboard import routes as dashboard


def create_app() -> FastAPI:
    get_settings()
    app = FastAPI(
        title="AccessGraph Connect",
        version="0.1.0",
        description=(
            "Read-only SaaS access-discovery and connector-operations platform. "
            "No revocation, remediation, or AI security agents."
        ),
    )
    app.include_router(health.router)
    app.include_router(connections.router)
    app.include_router(github.router)
    app.include_router(slack.router)
    app.include_router(inventory.router)
    app.include_router(sync.router)
    app.include_router(webhooks.router)
    app.include_router(dashboard.router)
    return app


app = create_app()
