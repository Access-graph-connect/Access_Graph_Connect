import os
import tempfile
from pathlib import Path

import pytest

# Point the app at a throwaway SQLite database before any app module reads
# settings. Migrations and models use portable types so this matches the
# PostgreSQL deployment schema.
_TEST_DB_DIR = Path(tempfile.mkdtemp(prefix="agc-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB_DIR / 'test.db'}"
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")


@pytest.fixture(scope="session", autouse=True)
def _migrate_shared_db():
    from alembic import command
    from alembic.config import Config

    command.upgrade(Config("alembic.ini"), "head")

