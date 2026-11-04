from fastapi import FastAPI

from app.api.routes import connections, github, health, inventory, sync


def create_app() -> FastAPI:
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
    app.include_router(inventory.router)
    app.include_router(sync.router)
    return app


app = create_app()
