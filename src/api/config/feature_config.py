"""Feature flags for optional debug and observability behavior."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class FeatureSettings(BaseSettings):
    """Toggle debug artifact JSON writes and frontend QC response projection."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    enable_artifact_logging: bool = False
    suppress_expected_qc_failures_from_frontend: bool = (
        True  # temporary: demo; set false after review
    )


feature_settings = FeatureSettings()
