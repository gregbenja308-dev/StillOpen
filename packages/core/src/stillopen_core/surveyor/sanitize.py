"""Surveyor: redact + classify before anything reaches Gemini or logs."""

from __future__ import annotations

from stillopen_core.observability.logger import get_logger
from stillopen_core.schemas.tab import SanitizedTab, TabSnapshot
from stillopen_core.security.hosts import blocked_from_model, classify_host
from stillopen_core.security.redact import host_of, redact_text, redact_url

_logger = get_logger(__name__)


def sanitize_tabs(tabs: list[TabSnapshot]) -> list[SanitizedTab]:
    out: list[SanitizedTab] = []
    blocked = 0
    for tab in tabs:
        safe_url, changed = redact_url(tab.url)
        host = host_of(safe_url)
        host_class = classify_host(host)
        deny = blocked_from_model(host_class)
        extract = None if deny else redact_text(tab.extract)
        if deny:
            blocked += 1
        title = redact_text(tab.title, max_chars=200) or ""
        out.append(
            SanitizedTab(
                tab_id=tab.tab_id,
                window_id=tab.window_id,
                index=tab.index,
                url=safe_url,
                title=title,
                host=host,
                host_class=host_class,
                pinned=tab.pinned,
                audible=tab.audible,
                discarded=tab.discarded,
                active=tab.active,
                group_id=tab.group_id,
                group_title=tab.group_title,
                last_accessed_ms=tab.last_accessed_ms,
                extract=extract,
                redacted=changed,
                blocked_from_model=deny,
            )
        )
    _logger.info("surveyor.sanitized", tab_count=len(out), blocked_from_model=blocked)
    return out


__all__ = ["sanitize_tabs"]
