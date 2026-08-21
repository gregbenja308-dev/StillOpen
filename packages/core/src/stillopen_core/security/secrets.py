"""Secret Manager hydrate. Cloud Run env wins; empty keys load from SM."""

from __future__ import annotations

import os

from stillopen_core.config import get_settings
from stillopen_core.observability.logger import get_logger

_logger = get_logger(__name__)

# Env var → Secret Manager id. Never log values.
_SECRETS: tuple[tuple[str, str], ...] = (
    ("STILLOPEN_JOB_TOKEN", "stillopen-job-token"),
    ("GOOGLE_API_KEY", "stillopen-google-api-key"),
)


def hydrate_secrets() -> list[str]:
    """Fill empty env vars from Secret Manager. Returns ids that loaded."""
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return []
    settings = get_settings()
    if settings.is_local or not settings.gcp_project:
        return []
    try:
        from google.cloud import secretmanager
    except ImportError:
        _logger.info("secrets.client_missing")
        return []

    client = secretmanager.SecretManagerServiceClient()
    loaded: list[str] = []
    for env_key, secret_id in _SECRETS:
        if os.environ.get(env_key):
            continue
        name = f"projects/{settings.gcp_project}/secrets/{secret_id}/versions/latest"
        try:
            payload = client.access_secret_version(request={"name": name})
            value = payload.payload.data.decode("utf-8").strip()
        except Exception as exc:  # noqa: BLE001 — missing secret is not fatal
            _logger.info("secrets.skip", secret=secret_id, error=type(exc).__name__)
            continue
        if not value:
            continue
        os.environ[env_key] = value
        loaded.append(secret_id)
    if loaded:
        get_settings.cache_clear()
        _logger.info("secrets.hydrated", count=len(loaded))
    return loaded


__all__ = ["hydrate_secrets"]
