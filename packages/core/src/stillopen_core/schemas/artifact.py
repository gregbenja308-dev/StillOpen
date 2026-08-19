"""Google artifact drafts — Clerk output, Runner input."""

from __future__ import annotations

from enum import Enum

from pydantic import Field

from stillopen_core.schemas.base import TimestampedModel, new_id


class ArtifactKind(str, Enum):
    DOC = "doc"
    EVENT = "event"
    TASK = "task"
    MAIL = "mail"


class ArtifactDraft(TimestampedModel):
    draft_id: str = Field(default_factory=new_id)
    kind: ArtifactKind
    title: str
    body: str
    source_urls: list[str] = Field(default_factory=list)
    card_id: str | None = None


class ArtifactRecord(TimestampedModel):
    record_id: str = Field(default_factory=new_id)
    draft_id: str
    kind: ArtifactKind
    google_id: str
    url: str
    title: str = ""
    body_preview: str = ""


__all__ = ["ArtifactDraft", "ArtifactKind", "ArtifactRecord"]
