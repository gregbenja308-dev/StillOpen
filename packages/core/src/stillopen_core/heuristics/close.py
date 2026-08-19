"""Close-checkbox heuristics. Time-open alone is never enough."""

from __future__ import annotations

import time
from urllib.parse import urlsplit

from stillopen_core.schemas.tab import CloseHint, HostClass, Intention, SanitizedTab
from stillopen_core.security.hosts import NEVER_CLOSE_CLASSES

_SEARCH_HOSTS = frozenset({"www.google.com", "google.com", "www.bing.com", "bing.com", "duckduckgo.com"})
_IDLE_MS = 8 * 24 * 60 * 60 * 1000  # 8 days


def _canonical_url(url: str) -> str:
    parts = urlsplit(url)
    host = (parts.hostname or "").removeprefix("www.")
    path = parts.path.rstrip("/") or "/"
    return f"{host}{path}"


def infer_intention(tab: SanitizedTab, *, sibling_count_same_host: int) -> Intention:
    title = tab.title.lower()
    path = urlsplit(tab.url).path.lower()
    if tab.host_class in NEVER_CLOSE_CLASSES:
        return Intention.HALF_DONE if "form" in path or "checkout" in path else Intention.REFERENCE
    if tab.host_class is HostClass.SEARCH:
        return Intention.ZOMBIE
    if any(s in title or s in path for s in ("track", "order status", "application status", "we'll email")):
        return Intention.WAITING
    if tab.host_class is HostClass.LISTING and sibling_count_same_host >= 2:
        return Intention.COMPARING
    if tab.host_class is HostClass.NEWS:
        return Intention.READ_LATER
    if tab.host_class is HostClass.DOCS:
        return Intention.REFERENCE
    if any(s in path for s in ("checkout", "cart", "apply", "form")):
        return Intention.HALF_DONE
    if sibling_count_same_host >= 3 and tab.host_class is HostClass.GENERIC:
        return Intention.COMPARING
    return Intention.UNKNOWN


def close_hint(
    tab: SanitizedTab,
    *,
    intention: Intention,
    is_duplicate: bool,
    now_ms: int | None = None,
) -> tuple[CloseHint, str]:
    if tab.pinned or tab.audible or tab.active:
        return CloseHint.NEVER, "pinned, audible, or focused"
    if tab.host_class in NEVER_CLOSE_CLASSES:
        return CloseHint.NEVER, f"host class {tab.host_class.value} is never-close"
    if intention is Intention.HALF_DONE:
        return CloseHint.NEVER, "half-done form"
    if intention is Intention.WAITING:
        return CloseHint.PRE_UNCHECK, "waiting — watch, don't close"
    if intention is Intention.REFERENCE:
        return CloseHint.PRE_UNCHECK, "reference shape"
    if is_duplicate:
        return CloseHint.PRE_CHECK, "duplicate URL"
    if tab.host_class is HostClass.SEARCH:
        return CloseHint.PRE_CHECK, "search leftover"
    now = now_ms if now_ms is not None else int(time.time() * 1000)
    idle = tab.last_accessed_ms is not None and (now - tab.last_accessed_ms) >= _IDLE_MS
    if idle and intention in {Intention.READ_LATER, Intention.ZOMBIE, Intention.UNKNOWN}:
        return CloseHint.PRE_CHECK, "idle and low-attention"
    if intention is Intention.COMPARING:
        return CloseHint.PRE_UNCHECK, "compare set — show, don't assume"
    return CloseHint.PRE_UNCHECK, "default keep until named"


def duplicate_ids(tabs: list[SanitizedTab]) -> set[int]:
    """All but the newest (or focused) tab per canonical URL."""
    by_canon: dict[str, list[SanitizedTab]] = {}
    for tab in tabs:
        by_canon.setdefault(_canonical_url(tab.url), []).append(tab)
    dupes: set[int] = set()
    for group in by_canon.values():
        if len(group) < 2:
            continue
        ranked = sorted(
            group,
            key=lambda t: (t.active, t.last_accessed_ms or 0),
            reverse=True,
        )
        for extra in ranked[1:]:
            dupes.add(extra.tab_id)
    return dupes


def sibling_counts(tabs: list[SanitizedTab]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for tab in tabs:
        host = tab.host.removeprefix("www.")
        counts[host] = counts.get(host, 0) + 1
    return counts


__all__ = ["close_hint", "duplicate_ids", "infer_intention", "sibling_counts"]
