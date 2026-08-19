"""Framer: cluster by intention, apply habits. No Google writes."""

from __future__ import annotations

import re
from collections import defaultdict

from stillopen_core.heuristics.close import (
    close_hint,
    duplicate_ids,
    infer_intention,
    sibling_counts,
)
from stillopen_core.memory.context import embedding_text
from stillopen_core.memory.embeddings import TabIndex
from stillopen_core.memory.habits import apply_habit_hint
from stillopen_core.schemas.habit import HabitProfile
from stillopen_core.schemas.plan import PlanCard, TabAction, Verb
from stillopen_core.schemas.tab import CloseHint, Intention, SanitizedTab

_STOP = frozenset({"the", "a", "an", "about", "tabs", "tab", "close", "please", "my", "to", "for"})

_VERB_FOR_INTENTION: dict[Intention, Verb] = {
    Intention.COMPARING: Verb.DECIDE,
    Intention.WAITING: Verb.WATCH,
    Intention.READ_LATER: Verb.FILE,
    Intention.HALF_DONE: Verb.FINISH,
    Intention.ZOMBIE: Verb.KILL,
    Intention.REFERENCE: Verb.FILE,
    Intention.UNKNOWN: Verb.FILE,
}


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in _STOP and len(t) > 2}


def match_named_job(
    command: str | None,
    tabs: list[SanitizedTab],
    *,
    use_vectors: bool = True,
) -> set[int]:
    """Token overlap union vector top-k. Empty command → all tabs."""
    if not command or not command.strip():
        return {t.tab_id for t in tabs}
    needle = _tokens(command)
    if not needle:
        return {t.tab_id for t in tabs}
    matched: set[int] = set()
    for tab in tabs:
        hay = _tokens(f"{tab.title} {tab.host} {tab.url}")
        if needle & hay:
            matched.add(tab.tab_id)
    if use_vectors:
        index = TabIndex()
        for tab in tabs:
            index.index_text(tab.tab_id, embedding_text(tab))
        for tab_id, score in index.query(command, k=12):
            if score >= 0.2:
                matched.add(tab_id)
    return matched


def frame(
    tabs: list[SanitizedTab],
    *,
    command: str | None = None,
    profile: HabitProfile | None = None,
) -> list[PlanCard]:
    matched_ids = match_named_job(command, tabs)
    matched = [t for t in tabs if t.tab_id in matched_ids]
    counts = sibling_counts(matched)
    dupes = duplicate_ids(matched)

    by_intention: dict[Intention, list[SanitizedTab]] = defaultdict(list)
    hints: dict[int, tuple[CloseHint, str]] = {}
    for tab in matched:
        host = tab.host.removeprefix("www.")
        intention = infer_intention(tab, sibling_count_same_host=counts.get(host, 1))
        if profile is not None:
            rule = profile.rule_for(host)
            if rule is not None and rule.intention_override is not None:
                intention = rule.intention_override
        hint, reason = close_hint(tab, intention=intention, is_duplicate=tab.tab_id in dupes)
        if profile is not None:
            hint = apply_habit_hint(tab, profile, hint)
            if hint is CloseHint.NEVER:
                reason = "habit pin: keep"
        hints[tab.tab_id] = (hint, reason)
        by_intention[intention].append(tab)

    cards: list[PlanCard] = []
    for intention, group in by_intention.items():
        verb = _VERB_FOR_INTENTION[intention]
        actions = [
            TabAction(
                tab_id=t.tab_id,
                close_hint=hints[t.tab_id][0],
                checked=hints[t.tab_id][0] is CloseHint.PRE_CHECK,
                reason=hints[t.tab_id][1],
                title=t.title,
            )
            for t in group
        ]
        cards.append(
            PlanCard(
                verb=verb,
                intention=intention,
                label=_label(intention, group),
                tab_ids=[t.tab_id for t in group],
                actions=actions,
            )
        )
    cards.sort(key=lambda c: c.verb.value)
    return cards


def _label(intention: Intention, group: list[SanitizedTab]) -> str:
    hosts = sorted({t.host.removeprefix("www.") for t in group})
    host_bit = hosts[0] if len(hosts) == 1 else f"{len(group)} tabs"
    return f"{intention.value}: {host_bit}"


__all__ = ["frame", "match_named_job"]
