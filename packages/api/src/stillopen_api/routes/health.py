"""Health probe."""

from __future__ import annotations

from fastapi import APIRouter
from stillopen_core.agents.adk_clerk import build_sequential_agent
from stillopen_core.config import get_settings

router = APIRouter()


@router.get("/healthz")
def healthz() -> dict[str, str]:
    settings = get_settings()
    adk = settings.has_gemini and build_sequential_agent() is not None
    if adk:
        clerk = "adk"
    elif settings.has_gemini:
        clerk = "adk_missing"
    else:
        clerk = "heuristic"
    return {
        "status": "ok",
        "env": settings.env.value,
        "service": settings.service_name,
        "gemini": "configured" if settings.has_gemini else "fakes",
        "google": "live" if settings.use_live_google and settings.has_oauth else "fake",
        "bank": "firestore" if settings.use_firestore else "local_json",
        "clerk": clerk,
    }
