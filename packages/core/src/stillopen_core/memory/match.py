"""Match a close request to tabs via named tasks, then fall back per-tab."""

from __future__ import annotations

import re

from stillopen_core.memory.tasks import _fold
from stillopen_core.schemas.habit import ChatIntent, MatchedTab
from stillopen_core.schemas.tab import TabSnapshot
from stillopen_core.schemas.task import OpenTask, TaskKind
from stillopen_core.security.hosts import NEVER_CLOSE_CLASSES, classify_host
from stillopen_core.security.redact import host_of, redact_url

_DAY_MS = 24 * 60 * 60 * 1000
_STOP = frozenset(
    {
        "about",
        "after",
        "always",
        "close",
        "delete",
        "drop",
        "from",
        "have",
        "idle",
        "into",
        "just",
        "keep",
        "kill",
        "left",
        "month",
        "months",
        "never",
        "okay",
        "older",
        "open",
        "please",
        "related",
        "relating",
        "remove",
        "stale",
        "still",
        "tabs",
        "than",
        "that",
        "them",
        "then",
        "these",
        "this",
        "those",
        "unused",
        "used",
        "want",
        "week",
        "weeks",
        "window",
        "with",
    }
)
_HOME = frozenset({"house", "houses", "housing", "home", "homes", "hous"})
_HOUSING = _HOME | frozenset(
    {
        "apartment",
        "apartments",
        "apt",
        "rental",
        "rentals",
        "realtor",
        "estate",
        "realestate",
    }
)
_MERCH = frozenset(
    {
        "laptop",
        "macbook",
        "iphone",
        "pixel",
        "headphone",
        "keyboard",
        "mouse",
        "airpods",
    }
)
_CLASS_MAJORITY = frozenset({"news", "mail", "docs", "search"})


def match_tabs(
    tabs: list[TabSnapshot],
    intent: ChatIntent,
    *,
    tasks: list[OpenTask] | None = None,
    query: str = "",
    now_ms: int | None = None,
) -> list[MatchedTab]:
    if not intent.wants_close:
        return []
    now = now_ms if now_ms is not None else _now_ms()
    unused_ms = (intent.unused_days or 0) * _DAY_MS
    by_id = {t.tab_id: t for t in tabs}
    terms = _query_tokens(query) | {c.lower() for c in intent.match_classes}
    topical = bool(terms or intent.close_hosts)

    related_ids: set[int] | None = None
    if tasks and topical:
        related_ids = set()
        for task in tasks:
            if task.kind is TaskKind.PROTECTED:
                continue
            if _task_related(task, intent, by_id, terms):
                related_ids.update(task.tab_ids)

    found: list[MatchedTab] = []
    for tab in tabs:
        if tab.pinned or tab.audible:
            continue
        host = host_of(tab.url).lower().removeprefix("www.")
        host_class = classify_host(host)
        explicit_host = _host_hit(host, intent.close_hosts)
        if host_class in NEVER_CLOSE_CLASSES and not explicit_host:
            continue
        if unused_ms and (tab.last_accessed_ms is None or now - tab.last_accessed_ms < unused_ms):
            continue
        if related_ids is not None:
            if tab.tab_id not in related_ids:
                continue
        elif not _matches(tab, host, host_class.value, intent, explicit_host, terms):
            continue
        safe, _changed = redact_url(tab.url)
        found.append(
            MatchedTab(tab_id=tab.tab_id, title=tab.title or host, host=host, url=safe),
        )
    return found


def _task_related(
    task: OpenTask,
    intent: ChatIntent,
    by_id: dict[int, TabSnapshot],
    terms: set[str],
) -> bool:
    members = [by_id[i] for i in task.tab_ids if i in by_id]
    if intent.close_hosts and any(
        _host_hit(host_of(t.url).lower().removeprefix("www."), intent.close_hosts) for t in members
    ):
        return True
    hay = _tokens(_task_text(task, members))
    if terms and any(_alike(q, h) for q in terms for h in hay):
        return True
    if terms & _HOUSING and _listing_job(members, hay):
        return True
    classes = [c.lower() for c in intent.match_classes if c.lower() in _CLASS_MAJORITY]
    if classes and members:
        hits = sum(1 for t in members if classify_host(host_of(t.url)).value in classes)
        if hits * 2 >= len(members):
            return True
    return False


def _task_text(task: OpenTask, members: list[TabSnapshot]) -> str:
    parts = [task.label, task.group_title, *task.titles, *task.hosts, *task.urls]
    for tab in members:
        parts.append(tab.title)
        parts.append(tab.url)
    return " ".join(parts)


def _matches(
    tab: TabSnapshot,
    host: str,
    host_class: str,
    intent: ChatIntent,
    explicit_host: bool,
    terms: set[str],
) -> bool:
    if explicit_host:
        return True
    if intent.match_classes and host_class in intent.match_classes:
        return True
    if terms:
        hay = _tokens(f"{tab.title} {host} {tab.url}")
        return any(_alike(q, h) for q in terms for h in hay)
    return bool(intent.unused_days)


def _query_tokens(text: str) -> set[str]:
    return {tok for tok in _tokens(text) if tok not in _STOP and len(tok) >= 4}


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if t}


def _listing_job(members: list[TabSnapshot], hay: set[str]) -> bool:
    if not members or hay & _MERCH:
        return False
    listing = sum(1 for tab in members if classify_host(host_of(tab.url)).value == "listing")
    return listing * 2 >= len(members)


def _alike(query: str, hay: str) -> bool:
    if query == hay:
        return True
    q_cores, h_cores = _cores(query), _cores(hay)
    if q_cores & h_cores:
        return True
    if q_cores & _HOUSING and h_cores & _HOUSING:
        return True
    for q in q_cores:
        if len(q) >= 4 and (hay.startswith(q) or q in hay and len(hay) - len(q) <= 6):
            return True
    return False


def _cores(token: str) -> set[str]:
    t = token.lower()
    out = {t, _fold(t)}
    if t.endswith("e") and len(t) >= 5:
        out.add(t[:-1])
    if out & _HOME:
        out.update(_HOME)
    return {c for c in out if len(c) >= 3}


def _host_hit(host: str, suffixes: list[str]) -> bool:
    for suffix in suffixes:
        s = suffix.lower().removeprefix("www.")
        if host == s or host.endswith("." + s):
            return True
    return False


def _now_ms() -> int:
    from time import time

    return int(time() * 1000)


__all__ = ["match_tabs"]
