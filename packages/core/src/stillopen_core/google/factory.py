"""Pick FakeGoogle (tests / no OAuth) or LiveGoogle (throwaway account connected)."""

from __future__ import annotations

import os

from stillopen_core.config import get_settings
from stillopen_core.google.tokens import has_token
from stillopen_core.google.workspace import FakeGoogle, GoogleWorkspace
from stillopen_core.observability.logger import get_logger

_logger = get_logger(__name__)


def get_google(user_id: str | None = None) -> GoogleWorkspace:
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return FakeGoogle()
    settings = get_settings()
    live = os.environ.get("STILLOPEN_LIVE_GOOGLE") == "1" or settings.use_live_google
    if not live or not user_id or not settings.has_oauth or not has_token(user_id):
        return FakeGoogle()
    try:
        from stillopen_core.google.live import LiveGoogle

        return LiveGoogle(user_id)
    except Exception as exc:  # noqa: BLE001 — never fail a close-path import
        _logger.info("google.live_unavailable", error=type(exc).__name__)
        return FakeGoogle()


__all__ = ["get_google"]
