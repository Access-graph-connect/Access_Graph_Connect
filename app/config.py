from functools import lru_cache

from cryptography.fernet import Fernet
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "local"
    database_url: str = (
        "postgresql+psycopg://accessgraph:accessgraph@localhost:5432/accessgraph"
    )
    redis_url: str = "redis://localhost:6379/0"
    secret_key: str = "change-me"
    # Fernet key for encrypting provider tokens at rest.
    token_encryption_key: str = ""

    # GitHub App credentials (Phase 2). The private key is PEM-encoded;
    # newlines may be escaped as \n in the environment.
    github_app_id: str = ""
    github_app_slug: str = ""
    github_app_private_key: str = ""
    github_webhook_secret: str = ""
    github_api_base: str = "https://api.github.com"
    github_web_base: str = "https://github.com"

    # Slack app credentials (Phase 4).
    slack_client_id: str = ""
    slack_client_secret: str = ""
    slack_signing_secret: str = ""
    slack_redirect_uri: str = ""
    slack_api_base: str = "https://slack.com/api"

    @property
    def github_app_private_key_pem(self) -> str:
        return self.github_app_private_key.replace("\\n", "\n")

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        if self.environment.strip().lower() not in {"prod", "production"}:
            return self

        if len(self.secret_key) < 32 or self.secret_key == "change-me":
            raise ValueError(
                "production requires a unique SECRET_KEY of at least 32 characters"
            )
        if not self.token_encryption_key:
            raise ValueError("production requires TOKEN_ENCRYPTION_KEY")
        try:
            Fernet(self.token_encryption_key.encode())
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "production TOKEN_ENCRYPTION_KEY must be a valid Fernet key"
            ) from exc
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
