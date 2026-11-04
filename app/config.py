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

    # GitHub App credentials (Phase 2). The private key is PEM-encoded;
    # newlines may be escaped as \n in the environment.
    github_app_id: str = ""
    github_app_slug: str = ""
    github_app_private_key: str = ""
    github_webhook_secret: str = ""
    github_api_base: str = "https://api.github.com"
    github_web_base: str = "https://github.com"

    @property
    def github_app_private_key_pem(self) -> str:
        return self.github_app_private_key.replace("\\n", "\n")


@lru_cache
def get_settings() -> Settings:
    return Settings()
