"""Plan conductor: Surveyor → Framer (habits + vectors). Run is a separate conductor."""

from __future__ import annotations

from stillopen_core.agents.framer import frame
from stillopen_core.memory.fakes import get_bank
from stillopen_core.observability.audit import record_event
from stillopen_core.observability.logger import get_logger
from stillopen_core.schemas.event import EventPhase
from stillopen_core.schemas.plan import Plan, Verb
from stillopen_core.schemas.tab import CloseHint, Intention, TabSnapshot
from stillopen_core.surveyor.sanitize import sanitize_tabs

_logger = get_logger(__name__)


def propose_plan(
    *,
    user_id: str,
    tabs: list[TabSnapshot],
    command: str | None = None,
    force_file: bool = False,
    user_notes: str = "",
    source_task_id: str | None = None,
) -> Plan:
    bank = get_bank()
    profile = bank.habit_for(user_id)
    sanitized = sanitize_tabs(tabs)
    blocked = [t.tab_id for t in sanitized if t.blocked_from_model]
    cards = frame(
        sanitized,
        command=None if force_file else command,
        profile=profile,
    )
    if force_file:
        for card in cards:
            card.verb = Verb.DECIDE if card.intention is Intention.COMPARING else Verb.FILE
            for action in card.actions:
                if action.close_hint is not CloseHint.NEVER:
                    action.checked = True
    plan = Plan(
        user_id=user_id,
        command=command,
        cards=cards,
        blocked_tab_ids=blocked,
        user_notes=user_notes,
        source_task_id=source_task_id,
    )
    bank.put_plan(plan)
    bank.put_tabs(plan.plan_id, tabs)
    record_event(
        plan_id=plan.plan_id,
        user_id=user_id,
        agent="framer",
        phase=EventPhase.PROPOSED,
        summary=(
            f"cards={len(cards)} tabs={len(tabs)} blocked={len(blocked)} "
            f"command={(command or '')[:40]}"
        ),
    )
    _logger.info(
        "conductor.proposed",
        plan_id=plan.plan_id,
        card_count=len(cards),
        blocked=len(blocked),
        habit_pins=len(profile.rules),
    )
    return plan


__all__ = ["propose_plan"]
