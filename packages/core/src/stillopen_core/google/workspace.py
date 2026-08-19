"""Google Workspace surface. Fake and live share this contract."""

from __future__ import annotations

from typing import Protocol

from stillopen_core.schemas.artifact import ArtifactKind, ArtifactRecord


class GoogleWorkspace(Protocol):
    def create(self, kind: ArtifactKind, title: str, body: str = "") -> ArtifactRecord: ...

    def exists(self, kind: ArtifactKind, google_id: str) -> bool: ...


class FakeGoogle:
    """Local stand-in for Docs/Calendar. Tests and degrade path."""

    def __init__(self) -> None:
        self.docs: dict[str, str] = {}
        self.events: dict[str, str] = {}
        self.tasks: dict[str, str] = {}
        self.fail_kinds: set[ArtifactKind] = set()

    def create(self, kind: ArtifactKind, title: str, body: str = "") -> ArtifactRecord:
        if kind in self.fail_kinds:
            raise RuntimeError(f"google {kind.value} failed")
        google_id = f"{kind.value}-{len(self.docs) + len(self.events) + len(self.tasks) + 1}"
        url = f"https://example.invalid/{kind.value}/{google_id}"
        if kind is ArtifactKind.DOC:
            self.docs[google_id] = title
        elif kind is ArtifactKind.EVENT:
            self.events[google_id] = title
        else:
            self.tasks[google_id] = title
        return ArtifactRecord(
            draft_id="",
            kind=kind,
            google_id=google_id,
            url=url,
            title=title,
            body_preview=body[:200],
        )

    def exists(self, kind: ArtifactKind, google_id: str) -> bool:
        if kind is ArtifactKind.DOC:
            return google_id in self.docs
        if kind is ArtifactKind.EVENT:
            return google_id in self.events
        if kind is ArtifactKind.TASK:
            return google_id in self.tasks
        return False


__all__ = ["FakeGoogle", "GoogleWorkspace"]
