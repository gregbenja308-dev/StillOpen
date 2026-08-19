"""Tab snapshot and intention types."""

from __future__ import annotations

from enum import Enum

from pydantic import ConfigDict, Field, field_validator

from stillopen_core.schemas.base import StillOpenModel


class Intention(str, Enum):
    WAITING = "waiting"
    COMPARING = "comparing"
    READ_LATER = "read_later"
    HALF_DONE = "half_done"
    REFERENCE = "reference"
    ZOMBIE = "zombie"
    UNKNOWN = "unknown"


class HostClass(str, Enum):
    MONEY = "money"
    HEALTH = "health"
    GOV = "gov"
    SCHOOL = "school"
    AUTH = "auth"
    SEARCH = "search"
    NEWS = "news"
    LISTING = "listing"
    DOCS = "docs"
    MAIL = "mail"
    GENERIC = "generic"


class CloseHint(str, Enum):
    NEVER = "never"
    PRE_CHECK = "pre_check"
    PRE_UNCHECK = "pre_uncheck"


class TabSnapshot(StillOpenModel):
    """One tab as seen by the extension. Extracts are optional and opt-in."""

    model_config = ConfigDict(
        strict=True,
        extra="ignore",
        validate_assignment=True,
        populate_by_name=True,
        frozen=False,
    )

    tab_id: int
    window_id: int
    index: int
    url: str
    title: str = ""
    pinned: bool = False
    audible: bool = False
    discarded: bool = False
    active: bool = False
    group_id: int = -1
    group_title: str = ""
    last_accessed_ms: int | None = None
    extract: str | None = Field(
        default=None,
        max_length=4000,
        description="Optional page snippet. Never sent for deny-listed hosts.",
    )

    @field_validator("tab_id", "window_id", "index", "group_id", mode="before")
    @classmethod
    def _coerce_int(cls, value: object) -> object:
        if isinstance(value, bool) or value is None or value == "":
            return value
        try:
            return int(float(str(value)))
        except (TypeError, ValueError):
            return value

    @field_validator("last_accessed_ms", mode="before")
    @classmethod
    def _coerce_ms(cls, value: object) -> int | None:
        if value is None or value == "":
            return None
        try:
            return int(float(str(value)))
        except (TypeError, ValueError):
            return None


class SanitizedTab(StillOpenModel):
    """Tab after Surveyor: redacted URL, no secrets, host class attached."""

    tab_id: int
    window_id: int
    index: int
    url: str
    title: str
    host: str
    host_class: HostClass
    pinned: bool
    audible: bool
    discarded: bool
    active: bool
    group_id: int
    group_title: str = ""
    last_accessed_ms: int | None
    extract: str | None
    redacted: bool
    blocked_from_model: bool


__all__ = [
    "CloseHint",
    "HostClass",
    "Intention",
    "SanitizedTab",
    "TabSnapshot",
]
