"""Append-only audit events for a plan.

Every agent step (Surveyor / Framer / Clerk / Runner / Verifier / Watch)
writes one PlanEvent so judges can replay the multi-agent chain from
Firestore or the ``/v1/plans/{id}/audit`` endpoint. Bodies are never stored;
inputs and outputs are summarised as counts + short hashes.
"""

from __future__ import annotations

from enum import Enum

from pydantic import Field

from stillopen_core.schemas.base import TimestampedModel, new_id


class EventPhase(str, Enum):
    PROPOSED = "proposed"
    CLERK_DRAFT = "clerk_draft"
    CLERK_DEGRADE = "clerk_degrade"
    RUNNER_FILE = "runner_file"
    RUNNER_FAIL = "runner_fail"
    VERIFIER_OK = "verifier_ok"
    VERIFIER_MISSING = "verifier_missing"
    CLOSE_APPLIED = "close_applied"
    CLOSE_BLOCKED = "close_blocked"
    WATCH_ENROLLED = "watch_enrolled"
    WATCH_TICK = "watch_tick"


class Verdict(str, Enum):
    OK = "ok"
    DEGRADED = "degraded"
    BLOCKED = "blocked"
    INFO = "info"


class PlanEvent(TimestampedModel):
    """One immutable step in the multi-agent chain for a plan."""

    event_id: str = Field(default_factory=new_id)
    plan_id: str
    user_id: str
    agent: str
    tool: str = ""
    phase: EventPhase
    verdict: Verdict = Verdict.INFO
    summary: str = Field(default="", max_length=280)
    duration_ms: int = 0
    trace_id: str | None = None


__all__ = ["EventPhase", "PlanEvent", "Verdict"]
