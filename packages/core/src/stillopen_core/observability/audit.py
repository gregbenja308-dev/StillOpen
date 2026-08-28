"""Audit trail helper. Append-only PlanEvent rows into MemoryBank.

Every agent step in the run graph should emit at least one event so the
``/v1/plans/{plan_id}/audit`` endpoint can replay the reasoning chain in
order (Surveyor → Framer → Clerk → Runner → Verifier → Watch). Events
are structured metadata only — no page HTML, no query strings, no LLM
prompt bodies (only hashes and short summaries).
"""

from __future__ import annotations

from stillopen_core.memory.fakes import MemoryBank, get_bank
from stillopen_core.observability.logger import get_logger
from stillopen_core.observability.tracing import current_trace_id
from stillopen_core.schemas.event import EventPhase, PlanEvent, Verdict

_logger = get_logger(__name__)


def record_event(
    *,
    plan_id: str,
    user_id: str,
    agent: str,
    phase: EventPhase,
    verdict: Verdict = Verdict.INFO,
    tool: str = "",
    summary: str = "",
    duration_ms: int = 0,
    bank: MemoryBank | None = None,
) -> PlanEvent:
    b = bank or get_bank()
    event = PlanEvent(
        plan_id=plan_id,
        user_id=user_id,
        agent=agent,
        phase=phase,
        verdict=verdict,
        tool=tool,
        summary=summary[:280],
        duration_ms=max(0, int(duration_ms)),
        trace_id=current_trace_id(),
    )
    b.append_event(event)
    _logger.info(
        "audit",
        plan_id=plan_id,
        agent=agent,
        phase=phase.value,
        verdict=verdict.value,
    )
    return event


__all__ = ["record_event"]
