import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError

from app.config import Settings
from app.main import create_app


def test_production_settings_require_strong_signing_secret() -> None:
    with pytest.raises(ValidationError, match="unique SECRET_KEY"):
        Settings(
            _env_file=None,
            environment="production",
            secret_key="change-me",
            token_encryption_key=Fernet.generate_key().decode(),
        )


def test_production_settings_require_valid_encryption_key() -> None:
    with pytest.raises(ValidationError, match="valid Fernet key"):
        Settings(
            _env_file=None,
            environment="production",
            secret_key="a-unique-production-signing-key-that-is-long-enough",
            token_encryption_key="not-a-fernet-key",
        )


def test_production_settings_require_encryption_key() -> None:
    with pytest.raises(ValidationError, match="requires TOKEN_ENCRYPTION_KEY"):
        Settings(
            _env_file=None,
            environment="production",
            secret_key="a-unique-production-signing-key-that-is-long-enough",
            token_encryption_key="",
        )


def test_production_settings_accept_valid_secrets() -> None:
    settings = Settings(
        _env_file=None,
        environment="production",
        secret_key="a-unique-production-signing-key-that-is-long-enough",
        token_encryption_key=Fernet.generate_key().decode(),
    )

    assert settings.environment == "production"


def test_local_demo_allows_demo_signing_key_without_encryption_key() -> None:
    settings = Settings(
        _env_file=None,
        environment="demo",
        secret_key="local-demo-only",
        token_encryption_key="",
    )

    assert settings.environment == "demo"


def test_app_startup_rejects_weak_production_secrets(monkeypatch) -> None:
    from app.config import get_settings

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SECRET_KEY", "change-me")
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    get_settings.cache_clear()
    try:
        with pytest.raises(ValidationError, match="unique SECRET_KEY"):
            create_app()
    finally:
        get_settings.cache_clear()
