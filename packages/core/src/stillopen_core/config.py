"""Runtime configuration. Downstream code calls ``get_settings()``."""

from __future__ import annotations

from enum import Enum
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    LOCAL = "local"
    CLOUD = "cloud"


class OtelExporter(str, Enum):
    CONSOLE = "console"
    GCP = "gcp"
    NONE = "none"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    env: Environment = Field(default=Environment.LOCAL, alias="STILLOPEN_ENV")
    service_name: str = Field(default="stillopen", alias="STILLOPEN_SERVICE_NAME")

    gcp_project: str = Field(default="", alias="GOOGLE_CLOUD_PROJECT")
    gcp_region: str = Field(default="us-central1", alias="GOOGLE_CLOUD_REGION")

    google_api_key: str = Field(default="", alias="GOOGLE_API_KEY")
    fast_model: str = Field(default="gemini-3.5-flash", alias="STILLOPEN_FAST_MODEL")
    reasoning_model: str = Field(default="gemini-3.5-pro", alias="STILLOPEN_REASONING_MODEL")

    token_key: str = Field(
        default="",
        alias="STILLOPEN_TOKEN_KEY",
        description="Fernet key. Empty means refuse to persist OAuth tokens.",
    )

    oauth_client_id: str = Field(default="", alias="GOOGLE_OAUTH_CLIENT_ID")
    oauth_client_secret: str = Field(default="", alias="GOOGLE_OAUTH_CLIENT_SECRET")
    oauth_redirect_uri: str = Field(
        default="http://127.0.0.1:8080/v1/auth/google/callback",
        alias="GOOGLE_OAUTH_REDIRECT_URI",
    )
    use_live_google: bool = Field(default=False, alias="STILLOPEN_LIVE_GOOGLE")
    job_token: str = Field(default="", alias="STILLOPEN_JOB_TOKEN")
    firestore_database: str = Field(default="(default)", alias="STILLOPEN_FIRESTORE_DB")

    otel_exporter: OtelExporter = Field(
        default=OtelExporter.CONSOLE, alias="STILLOPEN_OTEL_EXPORTER"
    )
    cors_origin_regex: str = Field(
        default=r"chrome-extension://.*",
        alias="STILLOPEN_API_CORS_ORIGIN_REGEX",
    )

    @property
    def is_local(self) -> bool:
        return self.env is Environment.LOCAL

    @property
    def can_persist_tokens(self) -> bool:
        return bool(self.token_key)

    @property
    def has_gemini(self) -> bool:
        return bool(self.google_api_key)

    @property
    def has_oauth(self) -> bool:
        return bool(self.oauth_client_id and self.oauth_client_secret)

    @property
    def use_firestore(self) -> bool:
        return self.env is Environment.CLOUD and bool(self.gcp_project)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


__all__ = ["Environment", "OtelExporter", "Settings", "get_settings"]
