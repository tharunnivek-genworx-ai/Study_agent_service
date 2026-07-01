"""Environment-backed configuration for the Study Agent Service."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Database, auth, and service settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_hostname: str
    database_port: str
    database_password: str
    database_name: str
    database_username: str
    database_echo: bool = False
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    cors_origins: str = "*"
    # Public base URL of this service, used to build absolute image URLs that
    # the browser can load directly (must be reachable from the frontend).
    media_base_url: str = "http://localhost:8001"


settings = Settings()
