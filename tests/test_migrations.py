from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

EXPECTED_TABLES = {
    "tenants",
    "provider_connections",
    "identities",
    "applications",
    "resources",
    "access_records",
    "sync_runs",
    "sync_cursors",
    "webhook_inbox",
    "connector_events",
}


def test_alembic_upgrade_head_creates_schema(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "migrations.db"
    url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", url)

    from app.config import get_settings

    get_settings.cache_clear()
    try:
        command.upgrade(Config("alembic.ini"), "head")
    finally:
        get_settings.cache_clear()

    tables = set(inspect(create_engine(url)).get_table_names())
    assert EXPECTED_TABLES <= tables
