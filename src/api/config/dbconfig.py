"""Environment-backed configuration for the Study Agent Service."""

from typing import Literal

from pydantic import computed_field
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
    # Object storage: leave gcs_bucket empty for local /uploads mode.
    gcs_bucket: str = ""
    gcs_prefix: str = "studyguru/tharun"
    gcs_signed_url_expiry_minutes: int = 60
    batch_dispatch_mode: Literal["procrastinate", "inline"] = "inline"
    generation_stale_threshold_minutes: int = 20
    # Cron for the periodic sweep that fails runs whose worker died mid-flight.
    generation_stale_sweep_cron: str = "*/5 * * * *"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def storage_backend(self) -> Literal["local", "gcs"]:
        return "gcs" if self.gcs_bucket.strip() else "local"


def build_procrastinate_conninfo() -> str:
    """Libpq connection string for the Procrastinate psycopg connector."""
    from src.api.data.clients.postgres.database import build_database_url

    conninfo = build_database_url(drivername="postgresql").render_as_string(
        hide_password=False
    )
    return str(conninfo)


settings = Settings()
