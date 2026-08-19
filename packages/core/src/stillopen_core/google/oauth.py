"""Least-privilege Google OAuth for Docs + Calendar. Throwaway account only."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from stillopen_core.config import get_settings
from stillopen_core.errors import ConfigError
from stillopen_core.google.tokens import load_token_blob, save_token_blob
from stillopen_core.observability.logger import get_logger

_logger = get_logger(__name__)

SCOPES = (
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/calendar.events",
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
)


def _client_config() -> dict[str, Any]:
    settings = get_settings()
    if not settings.has_oauth:
        raise ConfigError("GOOGLE_OAUTH_CLIENT_ID / SECRET are empty")
    return {
        "web": {
            "client_id": settings.oauth_client_id,
            "client_secret": settings.oauth_client_secret,
            "redirect_uris": [settings.oauth_redirect_uri],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }


def authorization_url(user_id: str) -> str:
    """Build the consent URL. State is the user_id (extension-generated UUID)."""
    try:
        from google_auth_oauthlib.flow import Flow
    except ImportError as exc:
        raise ConfigError("google-auth-oauthlib is not installed (core[cloud])") from exc

    settings = get_settings()
    flow = Flow.from_client_config(
        _client_config(),
        scopes=list(SCOPES),
        redirect_uri=settings.oauth_redirect_uri,
    )
    url, _state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=user_id,
    )
    return url


def exchange_code(user_id: str, code: str) -> dict[str, str]:
    try:
        from google_auth_oauthlib.flow import Flow
    except ImportError as exc:
        raise ConfigError("google-auth-oauthlib is not installed (core[cloud])") from exc

    settings = get_settings()
    flow = Flow.from_client_config(
        _client_config(),
        scopes=list(SCOPES),
        redirect_uri=settings.oauth_redirect_uri,
    )
    flow.fetch_token(code=code)
    creds = flow.credentials
    payload = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes or SCOPES),
    }
    save_token_blob(user_id, payload)
    _logger.info("oauth.token_saved", user_id=user_id)
    return {"user_id": user_id, "status": "connected"}


def credentials_for(user_id: str) -> Any | None:
    try:
        from google.oauth2.credentials import Credentials
    except ImportError:
        return None
    blob = load_token_blob(user_id)
    if not blob or not blob.get("refresh_token"):
        return None
    return Credentials(
        token=blob.get("token"),
        refresh_token=blob.get("refresh_token"),
        token_uri=blob.get("token_uri") or "https://oauth2.googleapis.com/token",
        client_id=blob.get("client_id") or get_settings().oauth_client_id,
        client_secret=blob.get("client_secret") or get_settings().oauth_client_secret,
        scopes=blob.get("scopes") or list(SCOPES),
    )


def oauth_status(user_id: str) -> dict[str, str]:
    settings = get_settings()
    connected = False
    try:
        connected = credentials_for(user_id) is not None
    except Exception:
        connected = False
    return {
        "configured": "yes" if settings.has_oauth else "no",
        "connected": "yes" if connected else "no",
        "consent_path": f"/v1/auth/google?{urlencode({'user_id': user_id})}",
        "scopes": "drive.file calendar.events",
    }


__all__ = [
    "SCOPES",
    "authorization_url",
    "credentials_for",
    "exchange_code",
    "oauth_status",
]
