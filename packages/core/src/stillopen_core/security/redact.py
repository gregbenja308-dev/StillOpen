"""URL / title / extract redaction. Never log or persist secrets."""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_SECRET_QUERY_KEYS = frozenset(
    {
        "token",
        "access_token",
        "refresh_token",
        "id_token",
        "api_key",
        "apikey",
        "key",
        "auth",
        "authorization",
        "session",
        "sessionid",
        "sid",
        "password",
        "passwd",
        "secret",
        "code",
        "email",
        "user",
        "username",
        "phone",
        "ssn",
        "account",
        "client_secret",
        "oauth_token",
    }
)

_EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
_LONG_HEX_RE = re.compile(r"\b[0-9a-f]{32,}\b", re.IGNORECASE)
_BEARER_RE = re.compile(r"bearer\s+[A-Za-z0-9._\-]+", re.IGNORECASE)

_REDACTED = "REDACTED"


def redact_query_value(key: str, value: str) -> str:
    if key.lower() in _SECRET_QUERY_KEYS:
        return _REDACTED
    if _EMAIL_RE.search(value) or _LONG_HEX_RE.search(value):
        return _REDACTED
    return value


def redact_url(url: str) -> tuple[str, bool]:
    """Return (safe_url, changed). Drops fragments; redacts secret query keys."""
    if not url:
        return url, False
    parts = urlsplit(url)
    changed = bool(parts.fragment)
    pairs: list[tuple[str, str]] = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        redacted = redact_query_value(key, value)
        if redacted != value:
            changed = True
        pairs.append((key, redacted))
    query = urlencode(pairs)
    safe = urlunsplit((parts.scheme, parts.netloc, parts.path, query, ""))
    return safe, changed or safe != url


def host_of(url: str) -> str:
    try:
        return urlsplit(url).hostname or ""
    except ValueError:
        return ""


def redact_text(text: str | None, *, max_chars: int = 2000) -> str | None:
    """Redact emails / tokens from an optional extract. Truncate."""
    if text is None:
        return None
    clipped = text[:max_chars]
    clipped = _EMAIL_RE.sub(_REDACTED, clipped)
    clipped = _BEARER_RE.sub("bearer REDACTED", clipped)
    clipped = _LONG_HEX_RE.sub(_REDACTED, clipped)
    return clipped


def safe_log_url(url: str) -> str:
    """Host + path only — never query string in logs."""
    parts = urlsplit(url)
    host = parts.hostname or ""
    path = parts.path or "/"
    return f"{host}{path}"


__all__ = ["host_of", "redact_text", "redact_url", "safe_log_url"]
