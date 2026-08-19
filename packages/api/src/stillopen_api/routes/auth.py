"""Throwaway-account OAuth. drive.file + calendar.events only."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from stillopen_core.config import get_settings
from stillopen_core.errors import ConfigError, TokenPersistDenied
from stillopen_core.google.oauth import authorization_url, exchange_code, oauth_status
from stillopen_core.google.tokens import has_token

router = APIRouter(prefix="/v1/auth/google", tags=["auth"])


@router.get("/status")
def status(user_id: str = Query(min_length=1, max_length=128)) -> dict[str, str]:
    try:
        return oauth_status(user_id)
    except TokenPersistDenied:
        return {
            "configured": "yes" if get_settings().has_oauth else "no",
            "connected": "yes" if has_token(user_id) else "no",
            "consent_path": f"/v1/auth/google?user_id={user_id}",
            "scopes": "drive.file calendar.events",
        }


@router.get("")
def start(user_id: str = Query(min_length=1, max_length=128)) -> RedirectResponse:
    try:
        return RedirectResponse(authorization_url(user_id), status_code=302)
    except ConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/callback")
def callback(
    code: str = Query(default=""),
    state: str = Query(default=""),
    error: str = Query(default=""),
) -> HTMLResponse:
    if error:
        return HTMLResponse(f"<p>Google OAuth error: {error}</p>", status_code=400)
    if not code or not state:
        return HTMLResponse("<p>Missing code or state.</p>", status_code=400)
    try:
        exchange_code(state, code)
    except TokenPersistDenied as exc:
        return HTMLResponse(
            f"<p>Connected, but tokens were not saved: {exc}. Set STILLOPEN_TOKEN_KEY.</p>",
            status_code=500,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return HTMLResponse(
        "<p>Still Open is connected. You can close this tab and return to the side panel.</p>"
        "<p>Scopes: drive.file, calendar.events. No Gmail. No full Drive.</p>"
    )
