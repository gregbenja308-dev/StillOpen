"""Google Workspace surface. Fake and live share this contract."""

from __future__ import annotations

from typing import Protocol

from stillopen_core.schemas.artifact import ArtifactKind, ArtifactRecord


class GoogleWorkspace(Protocol):
    def create(self, kind: ArtifactKind, title: str, body: str = "") -> ArtifactRecord: ...

    def exists(self, kind: ArtifactKind, google_id: str) -> bool: ...

    def read(self, kind: ArtifactKind, google_id: str) -> str | None: ...


class FakeGoogle:
    """Local stand-in for Docs/Calendar. Tests and degrade path.

    Stores the full body (not just the title) so the Verifier can run a
    fidelity check against what the Clerk actually wrote — see
    ``stillopen_core.agents.verifier``.
    """

    def __init__(self) -> None:
        self.docs: dict[str, tuple[str, str]] = {}
        self.events: dict[str, tuple[str, str]] = {}
        self.tasks: dict[str, tuple[str, str]] = {}
        self.fail_kinds: set[ArtifactKind] = set()

    def _bucket(self, kind: ArtifactKind) -> dict[str, tuple[str, str]] | None:
        if kind is ArtifactKind.DOC:
            return self.docs
        if kind is ArtifactKind.EVENT:
            return self.events
        if kind is ArtifactKind.TASK:
            return self.tasks
        return None

    def create(self, kind: ArtifactKind, title: str, body: str = "") -> ArtifactRecord:
        if kind in self.fail_kinds:
            raise RuntimeError(f"google {kind.value} failed")
        google_id = f"{kind.value}-{len(self.docs) + len(self.events) + len(self.tasks) + 1}"
        url = f"https://example.invalid/{kind.value}/{google_id}"
        bucket = self._bucket(kind)
        if bucket is not None:
            bucket[google_id] = (title, body)
        return ArtifactRecord(
            draft_id="",
            kind=kind,
            google_id=google_id,
            url=url,
            title=title,
            body_preview=body[:200],
        )

    def exists(self, kind: ArtifactKind, google_id: str) -> bool:
        bucket = self._bucket(kind)
        return bucket is not None and google_id in bucket

    def read(self, kind: ArtifactKind, google_id: str) -> str | None:
        bucket = self._bucket(kind)
        if bucket is None:
            return None
        row = bucket.get(google_id)
        return row[1] if row is not None else None


__all__ = ["FakeGoogle", "GoogleWorkspace"]
