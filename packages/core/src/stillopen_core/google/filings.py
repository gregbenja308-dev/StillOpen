"""StillOpen Filing Store — a real Google Cloud artifact without OAuth.

The Runner's ``GoogleWorkspace`` contract is a ``create()`` that returns
an ``ArtifactRecord`` with a durable, verifiable URL. Live Google Docs
would require OAuth per user, refresh tokens, revoke UX — heavy for a
hackathon and out of scope for the trust model (`SECURITY.md`).

Instead this store writes the Doc / Event / Task body to Firestore
(``filings/{filing_id}``) and returns a URL that renders it from the
Cloud Run API. Verifier's ``exists()`` reads the same collection, so
the "artifacts_ok" gate is genuine and judges can click a real link
that points at Cloud Console → Firestore.
"""

from __future__ import annotations

from stillopen_core.config import get_settings
from stillopen_core.memory.fakes import MemoryBank, get_bank
from stillopen_core.schemas.artifact import ArtifactKind, ArtifactRecord
from stillopen_core.schemas.base import new_id, now_utc


class FilingStore:
    """Persist a filing into MemoryBank / Firestore. Returns a shareable URL."""

    def __init__(
        self,
        bank: MemoryBank | None = None,
        *,
        user_id: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self._bank = bank or get_bank()
        self._user_id = user_id
        self._base_url = (base_url or get_settings().public_base_url).rstrip("/")

    def create(self, kind: ArtifactKind, title: str, body: str = "") -> ArtifactRecord:
        filing_id = f"{kind.value}-{new_id()}"
        payload = {
            "filing_id": filing_id,
            "kind": kind.value,
            "title": title,
            "body": body,
            "user_id": self._user_id or "unknown",
            "created_at": now_utc().isoformat(),
        }
        self._bank.put_filing(filing_id, payload)
        url = (
            f"{self._base_url}/v1/filings/{filing_id}"
            if self._base_url
            else f"stillopen:filing/{filing_id}"
        )
        return ArtifactRecord(
            draft_id="",
            kind=kind,
            google_id=filing_id,
            url=url,
            title=title,
            body_preview=body[:200],
        )

    def exists(self, kind: ArtifactKind, google_id: str) -> bool:
        try:
            payload = self._bank.get_filing(google_id)
        except Exception:  # noqa: BLE001 — treat any error as "not found"
            return False
        return payload.get("kind") == kind.value

    def read(self, kind: ArtifactKind, google_id: str) -> str | None:
        """Return the persisted body so the Verifier can check fidelity."""

        try:
            payload = self._bank.get_filing(google_id)
        except Exception:  # noqa: BLE001 — same posture as exists()
            return None
        if payload.get("kind") != kind.value:
            return None
        body = payload.get("body")
        return body if isinstance(body, str) else None


__all__ = ["FilingStore"]
