"""Context window budget — Evolving Knowledge Engine.

Accuracy does not require every extract in the prompt. Habits stay hot;
extracts are opt-in and capped; deny-listed hosts never enter the model.
"""

from __future__ import annotations

from stillopen_core.memory.embeddings import TabIndex
from stillopen_core.schemas.habit import HabitProfile
from stillopen_core.schemas.tab import SanitizedTab

MAX_TABS_IN_PROMPT = 12
MAX_HABIT_PINS = 8
MAX_EXTRACT_CHARS = 2000
MAX_FACTS_PER_USER = 150


def embedding_text(tab: SanitizedTab) -> str:
    """Title + host + path only. No query string, no extract."""
    return f"{tab.host} {tab.title}"


def rank_prompt_ids(
    tabs: list[SanitizedTab],
    *,
    query: str,
    pin_ids: list[int] | None = None,
) -> list[int]:
    """Card members first, then title+host vectors. Deny-listed hosts never rank."""
    by_id = {t.tab_id: t for t in tabs}
    ordered: list[int] = []
    seen: set[int] = set()
    for tab_id in pin_ids or []:
        tab = by_id.get(tab_id)
        if tab is None or tab.blocked_from_model or tab_id in seen:
            continue
        ordered.append(tab_id)
        seen.add(tab_id)
    remainder = [t for t in tabs if t.tab_id not in seen and not t.blocked_from_model]
    if remainder:
        index = TabIndex()
        for tab in remainder:
            index.index_text(tab.tab_id, embedding_text(tab))
        for tab_id, _score in index.query(query.strip() or "tabs", k=MAX_TABS_IN_PROMPT):
            if tab_id not in seen:
                ordered.append(tab_id)
                seen.add(tab_id)
    for tab in remainder:
        if tab.tab_id not in seen:
            ordered.append(tab.tab_id)
    return ordered


def prompt_tabs(
    tabs: list[SanitizedTab],
    *,
    ranked_ids: list[int] | None = None,
) -> list[SanitizedTab]:
    """Pin ranked matches, drop the rest. Deny-listed hosts never enter the model."""
    by_id = {t.tab_id: t for t in tabs}
    ordered = [by_id[i] for i in ranked_ids if i in by_id] if ranked_ids else list(tabs)
    clipped: list[SanitizedTab] = []
    for tab in ordered:
        if tab.blocked_from_model:
            continue
        extract = tab.extract
        if extract and len(extract) > MAX_EXTRACT_CHARS:
            extract = extract[:MAX_EXTRACT_CHARS]
        clipped.append(tab.model_copy(update={"extract": extract}))
        if len(clipped) >= MAX_TABS_IN_PROMPT:
            break
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
    "rank_prompt_ids",
]
