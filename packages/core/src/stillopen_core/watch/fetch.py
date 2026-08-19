"""Watch fetchers. Cloud: GET → hash in tick → discard body. Local: refuse network."""

from __future__ import annotations

import httpx

from stillopen_core.observability.logger import get_logger
from stillopen_core.security.redact import safe_log_url

_logger = get_logger(__name__)


def fetch_forbidden(_url: str) -> str:
    """Default fetcher refuses network in local/tests."""
    return ""


def hash_only_fetch(url: str, *, timeout: float = 8.0) -> str:
    """GET the URL, return body for hashing, never persist HTML."""
    _logger.info("watch.fetch", url=safe_log_url(url))
    response = httpx.get(url, timeout=timeout, follow_redirects=True)
    response.raise_for_status()
    return response.text[:200_000]


__all__ = ["fetch_forbidden", "hash_only_fetch"]
