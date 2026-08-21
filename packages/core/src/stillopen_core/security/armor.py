"""Inline Model Armor — prompt injection, tool poisoning, hostile titles.

Remote Model Armor runs when STILLOPEN_MODEL_ARMOR_TEMPLATE is set. Local
regex always runs so Gemini never sees jailbreak titles even without a template.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from stillopen_core.config import get_settings
from stillopen_core.observability.logger import get_logger

_logger = get_logger(__name__)

_INJECTION = re.compile(
    r"(ignore\s+(all\s+)?(previous|prior|above)\s+instructions"
    r"|you\s+are\s+now\s+(a|an|dan|jailbreak)"
    r"|system\s+prompt\s*:"
    r"|disregard\s+(the\s+)?(rules|policies|guardrails)"
    r"|do\s+not\s+follow\s+(your\s+)?(instructions|rules)"
    r"|<\s*script\b"
    r"|tool\s+policy\s+override)",
    re.IGNORECASE,
)

_PII_HINT = re.compile(
    r"\b(?:\d{3}-\d{2}-\d{4}|\d{16}|sk-[A-Za-z0-9]{20,})\b",
)


@dataclass(frozen=True, slots=True)
class ArmorVerdict:
    text: str
    blocked: bool
    reason: str = ""


def looks_like_injection(text: str) -> bool:
    return bool(text and _INJECTION.search(text))


def armor_title(title: str) -> str:
    """Tab titles are data. Jailbreaks become a placeholder, never instructions."""
    if looks_like_injection(title) or _PII_HINT.search(title or ""):
        return "[untrusted title]"
    return title


def armor_prompt(prompt: str) -> ArmorVerdict:
    """Strip injection / obvious secrets before generateContent."""
    if not prompt:
        return ArmorVerdict(text="", blocked=True, reason="empty")
    if looks_like_injection(prompt):
        cleaned = _INJECTION.sub("[blocked]", prompt)
        _logger.info("armor.injection", backend="inline")
        prompt = cleaned
    if _PII_HINT.search(prompt):
        prompt = _PII_HINT.sub("[redacted]", prompt)
        _logger.info("armor.pii", backend="inline")
    remote = _remote_sanitize(prompt)
    if remote is not None:
        return remote
    return ArmorVerdict(text=prompt, blocked=False)


def _remote_sanitize(prompt: str) -> ArmorVerdict | None:
    settings = get_settings()
    template = settings.model_armor_template
    if not template or not settings.gcp_project:
        return None
    try:
        import google.auth
        import google.auth.transport.requests
        import httpx
    except ImportError:
        return None
    try:
        creds, _project = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        creds.refresh(google.auth.transport.requests.Request())  # type: ignore[no-untyped-call]
    except Exception as exc:  # noqa: BLE001 — ADC missing is not fatal
        _logger.info("armor.remote_skip", error=type(exc).__name__)
        return None
    region = settings.gcp_region
    url = (
        f"https://modelarmor.{region}.rep.googleapis.com/v1/"
        f"projects/{settings.gcp_project}/locations/{region}/"
        f"templates/{template}:sanitizeUserPrompt"
    )
    try:
        response = httpx.post(
            url,
            headers={"Authorization": f"Bearer {creds.token}"},
            json={"userPromptData": {"text": prompt}},
            timeout=8.0,
        )
    except Exception as exc:  # noqa: BLE001
        _logger.warning("armor.remote_failed", error=type(exc).__name__)
        return None
    if response.status_code >= 400:
        _logger.warning("armor.remote_failed", status=response.status_code)
        return None
    payload = response.json()
    sanitization = payload.get("sanitizationResult") or payload
    match = str(sanitization.get("filterMatchState") or "").upper()
    if match in {"MATCH_FOUND", "SANITIZE_MATCH"}:
        _logger.info("armor.blocked", backend="model_armor")
        return ArmorVerdict(text="", blocked=True, reason="model_armor")
    sanitized = str((payload.get("sanitizedUserPrompt") or {}).get("text") or prompt)
    return ArmorVerdict(text=sanitized, blocked=False, reason="model_armor")


__all__ = ["ArmorVerdict", "armor_prompt", "armor_title", "looks_like_injection"]
