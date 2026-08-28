"""Google Workspace factory.

Live Google Docs would need per-user OAuth (heavy for a hackathon and out
of scope for the trust model — see ``SECURITY.md``). Instead the "durable
artifact" for Still Open is a Firestore-shaped filing served from
Cloud Run. Every ``create()`` writes a real Firestore document that
Verifier can subsequently ``exists()``-check, and the URL renders from
``GET /v1/filings/{id}`` — a genuine Google Cloud artifact with a
shareable link.

Set ``STILLOPEN_USE_FAKE_GOOGLE=1`` to force the in-memory-only
``FakeGoogle`` (used by a handful of tests that want the create() to
fail deterministically without touching MemoryBank).
"""

from __future__ import annotations

import os

from stillopen_core.google.filings import FilingStore
from stillopen_core.google.workspace import FakeGoogle, GoogleWorkspace


def get_google(user_id: str | None = None) -> GoogleWorkspace:
    from stillopen_core.config import get_settings
    from stillopen_core.memory.fakes import get_bank

    if os.environ.get("STILLOPEN_USE_FAKE_GOOGLE") == "1":
        return FakeGoogle()
    settings = get_settings()
    return FilingStore(
        bank=get_bank(),
        user_id=user_id,
        base_url=settings.public_base_url,
    )


__all__ = ["get_google"]
