"""Settings from the environment only. No secrets in code."""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: SecretStr = SecretStr("")
    supabase_url: str = ""
    supabase_jwt_secret: SecretStr = SecretStr("")
    jwt_audience: str = "authenticated"
    cors_origins: str = ""  # comma-separated list of allowed origins
    # Fernet key (urlsafe base64, 32 bytes) that encrypts Vetmanager API keys before they reach the database
    secrets_key: SecretStr = SecretStr("")
    # Vetmanager addresses are accepted only in these domains (protects the server from SSRF)
    vetmanager_host_suffixes: str = "vetmanager.ru,vetmanager.cloud,vetmanager2.ru"
    # Service endpoint that loads raw Vetmanager responses without a live account (tests, manual load)
    vetmanager_import_enabled: bool = False
    # Exports of reports (xlsx, pdf) per clinic per minute; raise it only in test environments
    export_limit_per_minute: int = 10


@lru_cache
def get_settings() -> Settings:
    return Settings()
