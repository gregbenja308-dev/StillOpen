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
    # Gemini 3.5 on Vertex is global / multi-region, not us-central1.
    gcp_location: str = Field(default="global", alias="GOOGLE_CLOUD_LOCATION")
    use_vertex: bool = Field(default=False, alias="GOOGLE_GENAI_USE_VERTEXAI")

    google_api_key: str = Field(default="", alias="GOOGLE_API_KEY")
    fast_model: str = Field(default="gemini-3.5-flash", alias="STILLOPEN_FAST_MODEL")
    reasoning_model: str = Field(default="gemini-3.5-pro", alias="STILLOPEN_REASONING_MODEL")

    token_key: str = Field(
        default="",
        alias="STILLOPEN_TOKEN_KEY",
        description="Fernet key for encrypted secrets at rest.",
    )

    job_token: str = Field(default="", alias="STILLOPEN_JOB_TOKEN")
    firestore_database: str = Field(default="(default)", alias="STILLOPEN_FIRESTORE_DB")

    otel_exporter: OtelExporter = Field(
        default=OtelExporter.NONE, alias="STILLOPEN_OTEL_EXPORTER"
    )
    model_armor_template: str = Field(
        default="",
        alias="STILLOPEN_MODEL_ARMOR_TEMPLATE",
        description="Model Armor template id. Empty = inline guards only.",
    )
    cors_origin_regex: str = Field(
        default=r"chrome-extension://.*",
        alias="STILLOPEN_API_CORS_ORIGIN_REGEX",
    )

    @property
    def is_local(self) -> bool:
        return self.env is Environment.LOCAL

    @property
    def has_gemini(self) -> bool:
        return bool(self.google_api_key) or (self.use_vertex and bool(self.gcp_project))

    @property
    def armor_backend(self) -> str:
        if self.model_armor_template and self.gcp_project:
            return "model_armor"
        return "inline"

    @property
    def use_firestore(self) -> bool:
        return self.env is Environment.CLOUD and bool(self.gcp_project)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


__all__ = ["Environment", "OtelExporter", "Settings", "get_settings"]
