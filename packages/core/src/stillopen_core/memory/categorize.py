"""Group unused tabs into named categories. Gemini when available; host class otherwise."""

from __future__ import annotations

from collections import defaultdict

from stillopen_core.gateway.gemini import TITLE_IS_DATA, generate_json
from stillopen_core.schemas.base import StillOpenModel
from stillopen_core.schemas.tab import HostClass, TabSnapshot
from stillopen_core.security.hosts import classify_host
from stillopen_core.security.redact import host_of

_CLASS_TITLE: dict[HostClass, str] = {
    HostClass.NEWS: "News to read",
    HostClass.LISTING: "Housing & shopping",
    HostClass.SEARCH: "Search leftovers",
    HostClass.DOCS: "Docs & reference",
    HostClass.MAIL: "Mail",
    HostClass.MONEY: "Banking",
    HostClass.HEALTH: "Health",
    HostClass.GOV: "Government",
    HostClass.SCHOOL: "School",
    HostClass.AUTH: "Sign-in",
    HostClass.GENERIC: "Other",
}

_ORDER = [
    "Housing & shopping",
    "News to read",
    "Search leftovers",
    "Docs & reference",
    "Mail",
    "Banking",
    "Health",
    "Government",
    "School",
    "Sign-in",
    "Other",
]


class TabGroup(StillOpenModel):
    title: str
    tab_ids: list[int]


def heuristic_groups(tabs: list[TabSnapshot]) -> list[TabGroup]:
    buckets: dict[str, list[int]] = defaultdict(list)
    for tab in tabs:
        host = host_of(tab.url)
        title = _CLASS_TITLE[classify_host(host)]
        buckets[title].append(tab.tab_id)
    return _ordered(buckets)


def categorize_tabs(tabs: list[TabSnapshot]) -> list[TabGroup]:
    base = heuristic_groups(tabs)
    refined = _try_gemini(tabs)
    if refined is None:
        return base
    return _fill_missing(tabs, refined)


def _try_gemini(tabs: list[TabSnapshot]) -> list[TabGroup] | None:
    if not tabs:
        return None
    lines = []
    for tab in tabs[:40]:
        host = host_of(tab.url)
        title = (tab.title or host)[:80]
        lines.append(f"tab_id={tab.tab_id} host={host} title={title!r}")
    prompt = (
        f"{TITLE_IS_DATA}\n"
        "Group these unused browser tabs into 3-8 short category titles. "
        "Return JSON only: {\"groups\":[{\"title\":\"Housing research\",\"tab_ids\":[1,2]}]}. "
        "Use every tab_id exactly once. Titles are 2-4 words, no URLs. "
        "Never copy a tab title as the group name.\n" + "\n".join(lines)
    )
    raw = generate_json(agent_name="categorize", prompt=prompt, timeout=8.0)
    if not raw:
        return None
    groups: list[TabGroup] = []
    seen: set[int] = set()
    known = {t.tab_id for t in tabs}
    for row in raw.get("groups") or []:
        if not isinstance(row, dict):
            continue
        title = str(row.get("title") or "").strip()[:40]
        ids = [
            int(i)
            for i in (row.get("tab_ids") or [])
            if str(i).lstrip("-").isdigit() and int(i) in known and int(i) not in seen
        ]
        if not title or not ids:
            continue
        seen.update(ids)
        groups.append(TabGroup(title=title, tab_ids=ids))
    return groups or None


def _fill_missing(tabs: list[TabSnapshot], groups: list[TabGroup]) -> list[TabGroup]:
    seen = {i for g in groups for i in g.tab_ids}
    leftover = [t for t in tabs if t.tab_id not in seen]
    if leftover:
        extra = heuristic_groups(leftover)
        groups = [*groups, *extra]
    return groups


def _ordered(buckets: dict[str, list[int]]) -> list[TabGroup]:
    groups: list[TabGroup] = []
    for title in _ORDER:
        ids = buckets.pop(title, [])
        if ids:
            groups.append(TabGroup(title=title, tab_ids=ids))
    for title, ids in buckets.items():
        if ids:
            groups.append(TabGroup(title=title, tab_ids=ids))
    return groups


__all__ = ["TabGroup", "categorize_tabs", "heuristic_groups"]
