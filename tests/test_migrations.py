from alembic import command
from alembic.config import Config
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, inspect, text

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
    "credential_vault",
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


def test_upgrade_encrypts_legacy_plaintext_credentials(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "legacy-credentials.db"
    url = f"sqlite:///{db_path}"
    encryption_key = Fernet.generate_key().decode()
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", encryption_key)

    from app.config import get_settings

    get_settings.cache_clear()
    try:
        config = Config("alembic.ini")
        command.upgrade(config, "ded29c766a20")
        engine = create_engine(url)
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO credential_vault "
                    "(id, ciphertext, encrypted, created_at, revoked_at) "
                    "VALUES (:id, :ciphertext, :encrypted, :created_at, NULL)"
                ),
                {
                    "id": "a3935807530048d383ea62a55b3dcba9",
                    "ciphertext": "legacy-secret",
                    "encrypted": False,
                    "created_at": "2026-01-01T00:00:00",
                },
            )
        command.upgrade(config, "head")
        with engine.connect() as connection:
            encrypted, ciphertext = connection.execute(
                text(
                    "SELECT encrypted, ciphertext FROM credential_vault WHERE id = :id"
                ),
                {"id": "a3935807530048d383ea62a55b3dcba9"},
            ).one()
        assert bool(encrypted)
        assert (
            Fernet(encryption_key.encode()).decrypt(ciphertext.encode())
            == b"legacy-secret"
        )
    finally:
        get_settings.cache_clear()
