"""Mutating habit memory — Evolving Knowledge Engine."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import Field

from stillopen_core.schemas.base import StillOpenModel, TimestampedModel, new_id
from stillopen_core.schemas.tab import CloseHint, Intention

MAX_MUTATIONS = 80
MAX_HOST_STATS = 40
MAX_STATEMENTS = 30
MAX_CHATS = 40


class ClosePolicy(str, Enum):
    ALWAYS_KEEP = "always_keep"
    FILE_THEN_CLOSE = "file_then_close"
    NEVER_CLOSE = "never_close"


class FeedbackKind(str, Enum):
    UNCHECK = "uncheck"
    UNDO = "undo"
    VETO_INTENTION = "veto_intention"
    CHAT = "chat"
    USER_CLOSE = "user_close"
    STILLOPEN_CLOSE = "stillopen_close"
    KEEP = "keep"


class HabitRule(TimestampedModel):
    rule_id: str = Field(default_factory=new_id)
    host_suffix: str
    phrase: str | None = None
    close_policy: ClosePolicy = ClosePolicy.ALWAYS_KEEP
    intention_override: Intention | None = None
    hits: int = 1
    source: str = "uncheck"


class HabitEvent(TimestampedModel):
    """An explicit user move. We never learn from an unconfirmed session."""

    event_id: str = Field(default_factory=new_id)
    kind: FeedbackKind
    host_suffix: str = ""
    phrase: str | None = None
    from_intention: Intention | None = None
    to_intention: Intention | None = None
    source: str = "plan"


class HostStat(TimestampedModel):
    host_suffix: str
    user_closed: int = 0
    stillopen_closed: int = 0
    kept: int = 0
    last_action: str | None = None


class PreferenceStatement(TimestampedModel):
    statement_id: str = Field(default_factory=new_id)
    text: str
    parsed: dict[str, Any] = Field(default_factory=dict)
    active: bool = True


class ChatTurn(TimestampedModel):
    turn_id: str = Field(default_factory=new_id)
    role: str
    text: str
    mutations: list[str] = Field(default_factory=list)


class Mutation(TimestampedModel):
    mutation_id: str = Field(default_factory=new_id)
    kind: FeedbackKind
    source: str
    summary: str
    host_suffix: str | None = None
    before: dict[str, Any] = Field(default_factory=dict)
    after: dict[str, Any] = Field(default_factory=dict)
    phrase: str | None = None


class HabitProfile(TimestampedModel):
    user_id: str
    rules: list[HabitRule] = Field(default_factory=list)
    stale_cutoff_days: int = 7
    statements: list[PreferenceStatement] = Field(default_factory=list)
    hosts: list[HostStat] = Field(default_factory=list)
    mutations: list[Mutation] = Field(default_factory=list)
    chats: list[ChatTurn] = Field(default_factory=list)
    close_classes: list[str] = Field(default_factory=list)

    def rule_for(self, host: str) -> HabitRule | None:
        h = _norm_host(host)
        for rule in self.rules:
            suffix = _norm_host(rule.host_suffix)
            if h == suffix or h.endswith("." + suffix):
                return rule
        return None

    def stat_for(self, host: str) -> HostStat:
        h = _norm_host(host)
        for stat in self.hosts:
            if _norm_host(stat.host_suffix) == h:
                return stat
        stat = HostStat(host_suffix=h)
        self.hosts.append(stat)
        if len(self.hosts) > MAX_HOST_STATS:
            self.hosts = self.hosts[-MAX_HOST_STATS:]
        return stat


class ChatIntent(StillOpenModel):
    stale_cutoff_days: int | None = None
    unused_days: int | None = None
    keep_hosts: list[str] = Field(default_factory=list)
    close_hosts: list[str] = Field(default_factory=list)
    match_classes: list[str] = Field(default_factory=list)
    wants_close: bool = False
    label: str = ""
    reply: str = ""
    parser: str = "heuristic"


class MatchedTab(StillOpenModel):
    tab_id: int
    title: str
    host: str
    url: str


class ScheduledClose(TimestampedModel):
    schedule_id: str = Field(default_factory=new_id)
    user_id: str
    prompt: str
    label: str = ""
    run_at: datetime
    hosts: list[str] = Field(default_factory=list)
    titles: list[str] = Field(default_factory=list)
    urls: list[str] = Field(default_factory=list)
    status: str = "pending"


def _norm_host(host: str) -> str:
    return host.lower().removeprefix("www.").strip()


def policy_to_hint(policy: ClosePolicy) -> CloseHint:
    if policy is ClosePolicy.FILE_THEN_CLOSE:
        return CloseHint.PRE_CHECK
    return CloseHint.NEVER


__all__ = [
    "MAX_CHATS",
    "MAX_MUTATIONS",
    "MAX_STATEMENTS",
    "ChatIntent",
    "ChatTurn",
    "ClosePolicy",
    "FeedbackKind",
    "HabitEvent",
    "HabitProfile",
    "HabitRule",
    "HostStat",
    "MatchedTab",
    "Mutation",
    "PreferenceStatement",
    "ScheduledClose",
    "policy_to_hint",
]
