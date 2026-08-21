"""Google Workspace stand-in. Live Docs/OAuth were removed; notes are the done-path."""

from __future__ import annotations

from stillopen_core.google.workspace import FakeGoogle, GoogleWorkspace


def get_google(user_id: str | None = None) -> GoogleWorkspace:
    del user_id
    return FakeGoogle()


__all__ = ["get_google"]
