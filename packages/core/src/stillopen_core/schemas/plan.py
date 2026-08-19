"""Plan / workbench cards."""

from __future__ import annotations

from enum import Enum

from pydantic import Field

from stillopen_core.schemas.base import TimestampedModel, new_id
from stillopen_core.schemas.tab import CloseHint, Intention


class Verb(str, Enum):
    FILE = "file"
    WATCH = "watch"
    FINISH = "finish"
    DECIDE = "decide"
    KILL = "kill"


class PlanStatus(str, Enum):
    PROPOSED = "proposed"
    HELD = "held"
    RUNNING = "running"
    VERIFIED = "verified"
    DEGRADED = "degraded"
    UNDONE = "undone"


class TabAction(TimestampedModel):
    tab_id: int
    close_hint: CloseHint
    checked: bool
    reason: str
    title: str = ""


class PlanCard(TimestampedModel):
    card_id: str = Field(default_factory=new_id)
    verb: Verb
    intention: Intention
    label: str
    tab_ids: list[int]
    actions: list[TabAction]
    notes: str = ""


class Plan(TimestampedModel):
    plan_id: str = Field(default_factory=new_id)
    user_id: str
    command: str | None = None
    status: PlanStatus = PlanStatus.PROPOSED
    cards: list[PlanCard] = Field(default_factory=list)
    blocked_tab_ids: list[int] = Field(default_factory=list)
    trace_id: str | None = None


__all__ = ["Plan", "PlanCard", "PlanStatus", "TabAction", "Verb"]
