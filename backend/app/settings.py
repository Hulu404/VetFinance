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


@lru_cache
def get_settings() -> Settings:
    return Settings()
