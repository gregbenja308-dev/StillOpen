"""Enroll Watch rows from WAITING / READ_LATER / HALF_DONE cards. No human after this."""

from __future__ import annotations

from stillopen_core.memory.fakes import get_bank
from stillopen_core.schemas.plan import Plan, Verb
from stillopen_core.schemas.tab import SanitizedTab
from stillopen_core.schemas.watch import Watch, WatchKind, default_deadline
from stillopen_core.security.redact import redact_url

_KIND = {
    Verb.WATCH: WatchKind.TRACKING,
    Verb.FILE: WatchKind.READ_LATER,
    Verb.FINISH: WatchKind.HALF_DONE,
}


def enroll_from_plan(plan: Plan, tabs: list[SanitizedTab]) -> list[Watch]:
    bank = get_bank()
    by_id = {t.tab_id: t for t in tabs}
    enrolled: list[Watch] = []
    for card in plan.cards:
        kind = _KIND.get(card.verb)
        if kind is None:
            continue
        if card.verb is Verb.FILE:
            # File cards are docs; only enroll read-later for stale detection.
            pass
        for tab_id in card.tab_ids:
            tab = by_id.get(tab_id)
            if tab is None:
                continue
            url, _ = redact_url(tab.url)
            watch = Watch(
                user_id=plan.user_id,
                plan_id=plan.plan_id,
                kind=kind,
                label=card.label,
                url=url,
                deadline_at=default_deadline(kind),
            )
            bank.put_watch(watch)
            enrolled.append(watch)
    return enrolled


__all__ = ["enroll_from_plan"]
