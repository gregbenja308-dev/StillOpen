"""Context window budget — Evolving Knowledge Engine.

Accuracy does not require every extract in the prompt. Habits stay hot;
extracts are opt-in and capped; deny-listed hosts never enter the model.
"""

from __future__ import annotations

from stillopen_core.schemas.habit import HabitProfile
from stillopen_core.schemas.tab import SanitizedTab

MAX_TABS_IN_PROMPT = 12
MAX_HABIT_PINS = 8
MAX_EXTRACT_CHARS = 2000
MAX_FACTS_PER_USER = 150


def embedding_text(tab: SanitizedTab) -> str:
    """Title + host + path only. No query string, no extract."""
    return f"{tab.host} {tab.title}"


def prompt_tabs(tabs: list[SanitizedTab], *, ranked_ids: list[int] | None = None) -> list[SanitizedTab]:
    """Pin ranked matches, drop the rest. Strips extracts unless already small."""
    by_id = {t.tab_id: t for t in tabs}
    if ranked_ids:
        ordered = [by_id[i] for i in ranked_ids if i in by_id]
    else:
        ordered = list(tabs)
    clipped: list[SanitizedTab] = []
    for tab in ordered[:MAX_TABS_IN_PROMPT]:
        extract = tab.extract
        if extract and len(extract) > MAX_EXTRACT_CHARS:
            extract = extract[:MAX_EXTRACT_CHARS]
        if tab.blocked_from_model:
            extract = None
        clipped.append(tab.model_copy(update={"extract": extract}))
    return clipped


def habit_pins(profile: HabitProfile) -> list[str]:
    return [
        f"{rule.host_suffix}:{rule.close_policy.value}"
        for rule in profile.rules[:MAX_HABIT_PINS]
    ]


__all__ = [
    "MAX_EXTRACT_CHARS",
    "MAX_FACTS_PER_USER",
    "MAX_HABIT_PINS",
    "MAX_TABS_IN_PROMPT",
    "embedding_text",
    "habit_pins",
    "prompt_tabs",
]
