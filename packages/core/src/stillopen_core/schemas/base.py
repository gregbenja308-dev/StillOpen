"""Shared Pydantic base models."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field


def now_utc() -> datetime:
    return datetime.now(tz=UTC)


def new_id() -> str:
    return uuid.uuid4().hex[:26]


class StillOpenModel(BaseModel):
    model_config = ConfigDict(
        strict=True,
        validate_assignment=True,
        extra="forbid",
        populate_by_name=True,
        frozen=False,
    )


class TimestampedModel(StillOpenModel):
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)

    def touch(self) -> None:
        self.updated_at = now_utc()


__all__ = ["StillOpenModel", "TimestampedModel", "new_id", "now_utc"]
