from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "local"
    database_url: str = (
        "postgresql+psycopg://accessgraph:accessgraph@localhost:5432/accessgraph"
    )
    redis_url: str = "redis://localhost:6379/0"
    secret_key: str = "change-me"
    # Fernet key for encrypting provider tokens at rest (wired up in Phase 5).
    token_encryption_key: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
