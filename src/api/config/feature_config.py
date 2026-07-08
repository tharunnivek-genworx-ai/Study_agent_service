"""Feature flags for optional debug and observability behavior."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class FeatureSettings(BaseSettings):
    """Toggle debug artifact JSON writes (study/quiz/hint/QC/LlamaParse raw dumps)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    enable_artifact_logging: bool = False


feature_settings = FeatureSettings()
