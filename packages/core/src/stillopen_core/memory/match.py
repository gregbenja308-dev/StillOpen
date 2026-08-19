"""Match open tabs against a chat close request."""

from __future__ import annotations

from stillopen_core.schemas.habit import ChatIntent, MatchedTab
from stillopen_core.schemas.tab import TabSnapshot
from stillopen_core.security.hosts import NEVER_CLOSE_CLASSES, classify_host
from stillopen_core.security.redact import host_of, redact_url

_DAY_MS = 24 * 60 * 60 * 1000


def match_tabs(
    tabs: list[TabSnapshot],
    intent: ChatIntent,
    *,
    now_ms: int | None = None,
) -> list[MatchedTab]:
    if not intent.wants_close:
        return []
    now = now_ms if now_ms is not None else _now_ms()
    unused_ms = (intent.unused_days or 0) * _DAY_MS
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
        if not _matches(tab, host, host_class.value, intent, explicit_host):
            continue
        safe, _changed = redact_url(tab.url)
        found.append(
            MatchedTab(tab_id=tab.tab_id, title=tab.title or host, host=host, url=safe),
        )
    return found


def _matches(
    tab: TabSnapshot,
    host: str,
    host_class: str,
    intent: ChatIntent,
    explicit_host: bool,
) -> bool:
    has_filter = bool(intent.match_classes or intent.close_hosts)
    if not has_filter:
        return True
    if intent.match_classes and host_class in intent.match_classes:
        return True
    if explicit_host:
        return True
    hay = f"{tab.title} {host}".lower()
    return any(cls in hay for cls in intent.match_classes)


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
