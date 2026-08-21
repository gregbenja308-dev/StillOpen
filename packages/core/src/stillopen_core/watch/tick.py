"""Watch tick — Continuous Action. No extension, no chat."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256

from stillopen_core.google.factory import get_google
from stillopen_core.google.workspace import GoogleWorkspace
from stillopen_core.memory.fakes import get_bank
from stillopen_core.observability.logger import get_logger
from stillopen_core.observability.tracing import start_span
from stillopen_core.schemas.artifact import ArtifactKind, ArtifactRecord
from stillopen_core.schemas.base import now_utc
from stillopen_core.schemas.watch import Watch, WatchKind, WatchStatus

_logger = get_logger(__name__)

Fetcher = Callable[[str], str]


def hash_body(body: str) -> str:
    return sha256(body.encode("utf-8")).hexdigest()


def tick(
    *,
    fetcher: Fetcher,
    google: GoogleWorkspace | None = None,
    at: datetime | None = None,
    user_id: str | None = None,
) -> list[Watch]:
    """Process due watches. Stores hashes only — never page HTML."""
    with start_span("stillopen.watch_tick"):
        return _tick(fetcher=fetcher, google=google, at=at, user_id=user_id)


def _tick(
    *,
    fetcher: Fetcher,
    google: GoogleWorkspace | None,
    at: datetime | None,
    user_id: str | None,
) -> list[Watch]:
    google = google or get_google(user_id)
    when = at or now_utc()
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    bank = get_bank()
    acted: list[Watch] = []
    watches = bank.list_watches() if hasattr(bank, "list_watches") else list(bank.watches.values())
    for watch in watches:
        if watch.status is not WatchStatus.ACTIVE:
            continue
        if not watch.is_due(when):
            continue
        body = fetcher(watch.url)
        digest = hash_body(body)
        if watch.last_hash is None:
            watch.last_hash = digest
            watch.next_check_at = when
            watch.touch()
            bank.put_watch(watch)
            continue
        if digest != watch.last_hash:
            watch.last_hash = digest
            watch.status = WatchStatus.CHANGED
            watch.last_action = "page_changed"
            _record(google, bank, watch, ArtifactKind.TASK, f"Changed: {watch.label}")
            acted.append(watch)
        elif watch.deadline_at is not None and when >= watch.deadline_at:
            watch.status = WatchStatus.ESCALATED
            watch.last_action = "no_show"
            kind = ArtifactKind.EVENT if watch.kind is WatchKind.TRACKING else ArtifactKind.TASK
            _record(google, bank, watch, kind, f"No-Show: {watch.label}")
            acted.append(watch)
        elif watch.kind is WatchKind.READ_LATER and watch.deadline_at and when >= watch.deadline_at:
            watch.status = WatchStatus.STALE
            watch.last_action = "stale"
            acted.append(watch)
        watch.touch()
        bank.put_watch(watch)
        _logger.info("watch.tick", watch_id=watch.watch_id, status=watch.status.value)
    return acted


def _record(
    google: GoogleWorkspace,
    bank: object,
    watch: Watch,
    kind: ArtifactKind,
    title: str,
) -> ArtifactRecord:
    record = google.create(kind, title)
    bank.put_artifact(record)  # type: ignore[attr-defined]
    return record


__all__ = ["hash_body", "tick"]
