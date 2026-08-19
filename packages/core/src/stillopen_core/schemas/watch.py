"""Watch records — Continuous Action Engine state."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from enum import Enum

from pydantic import Field

from stillopen_core.schemas.base import TimestampedModel, new_id, now_utc


class WatchKind(str, Enum):
    TRACKING = "tracking"
    READ_LATER = "read_later"
    HALF_DONE = "half_done"


class WatchStatus(str, Enum):
    ACTIVE = "active"
    CHANGED = "changed"
    ESCALATED = "escalated"
    STALE = "stale"


class Watch(TimestampedModel):
    watch_id: str = Field(default_factory=new_id)
    user_id: str
    plan_id: str
    kind: WatchKind
    label: str
    url: str
    last_hash: str | None = None
    next_check_at: datetime = Field(default_factory=now_utc)
    deadline_at: datetime | None = None
    status: WatchStatus = WatchStatus.ACTIVE
    last_action: str | None = None

    def is_due(self, at: datetime | None = None) -> bool:
        when = at or now_utc()
        if when.tzinfo is None:
            when = when.replace(tzinfo=UTC)
        return when >= self.next_check_at and self.status is WatchStatus.ACTIVE


def default_deadline(kind: WatchKind, *, now: datetime | None = None) -> datetime | None:
    stamp = now or now_utc()
    if kind is WatchKind.TRACKING:
        return stamp + timedelta(days=3)
    if kind is WatchKind.READ_LATER:
        return stamp + timedelta(days=7)
    if kind is WatchKind.HALF_DONE:
        return stamp + timedelta(days=2)
    return None


__all__ = ["Watch", "WatchKind", "WatchStatus", "default_deadline"]
