"""Apply checkbox overrides and learn habits from explicit unchecks."""

from __future__ import annotations

from stillopen_core.memory.habits import mutate
from stillopen_core.schemas.habit import FeedbackKind, HabitEvent, HabitProfile
from stillopen_core.schemas.plan import Plan
from stillopen_core.schemas.tab import CloseHint, SanitizedTab
from stillopen_core.security.redact import host_of


def apply_overrides(plan: Plan, overrides: dict[int, bool]) -> list[int]:
    """Set checked flags. NEVER hints cannot be checked on. Returns newly unchecked ids."""
    unchecked: list[int] = []
    for card in plan.cards:
        for action in card.actions:
            if action.tab_id not in overrides:
                continue
            wanted = overrides[action.tab_id]
            if action.close_hint is CloseHint.NEVER:
                action.checked = False
                continue
            if action.checked and not wanted:
                unchecked.append(action.tab_id)
            action.checked = wanted
            action.touch()
    return unchecked


def learn_unchecks(
    profile: HabitProfile,
    unchecked_ids: list[int],
    tabs: list[SanitizedTab],
    phrase: str | None,
) -> HabitProfile:
    by_id = {t.tab_id: t for t in tabs}
    for tab_id in unchecked_ids:
        tab = by_id.get(tab_id)
        if tab is None:
            continue
        host = host_of(tab.url) or tab.host
        mutate(
            profile,
            HabitEvent(
                kind=FeedbackKind.UNCHECK,
                host_suffix=host,
                phrase=phrase,
            ),
        )
    return profile


__all__ = ["apply_overrides", "learn_unchecks"]
