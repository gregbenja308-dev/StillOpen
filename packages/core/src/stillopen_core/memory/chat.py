"""Turn a preference sentence into structured memory mutations."""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

from stillopen_core.config import get_settings
from stillopen_core.memory.habits import append_mutation, upsert_rule
from stillopen_core.schemas.habit import (
    MAX_CHATS,
    MAX_STATEMENTS,
    ChatIntent,
    ChatTurn,
    ClosePolicy,
    FeedbackKind,
    HabitProfile,
    Mutation,
    PreferenceStatement,
)

_UNIT = {
    "day": 1,
    "days": 1,
    "week": 7,
    "weeks": 7,
    "fortnight": 14,
    "month": 30,
    "months": 30,
}
_ALIASES = {
    "github": "github.com",
    "gitlab": "gitlab.com",
    "reddit": "reddit.com",
    "twitter": "x.com",
    "x.com": "x.com",
    "youtube": "youtube.com",
    "gmail": "mail.google.com",
    "zillow": "zillow.com",
    "redfin": "redfin.com",
}
_CLASS_WORDS: dict[str, str] = {
    "news": "news",
    "article": "news",
    "articles": "news",
    "listing": "listing",
    "listings": "listing",
    "housing": "listing",
    "homes": "listing",
    "shopping": "listing",
    "search": "search",
    "mail": "mail",
    "email": "mail",
}

_CUTOFF_RE = re.compile(
    r"(?:haven['’]?t\s+(?:used|opened|accessed|touched)|unused|idle|older than|stale|not used)"
    r".{0,40}?(?:(?:in|for|after)\s+)?(?:a\s+|an\s+)?(\d+)?\s*"
    r"(day|days|week|weeks|fortnight|month|months)\b",
    re.IGNORECASE,
)
_CUTOFF_NUM_RE = re.compile(
    r"\b(\d+)\s*(day|days|week|weeks|month|months)\b",
    re.IGNORECASE,
)
_HOST_RE = re.compile(r"\b(?:[a-z0-9-]+\.)+[a-z]{2,}\b", re.IGNORECASE)
_KEEP_RE = re.compile(
    r"\b(?:never close|don['’]t close|do not close|keep|leave open|always keep)\b",
    re.IGNORECASE,
)
_CLOSE_RE = re.compile(
    r"\b(?:always close|ok to close|okay to close|delete|close|kill|drop)\b",
    re.IGNORECASE,
)


def parse_preference(message: str) -> ChatIntent:
    text = message.strip()
    if not text:
        return ChatIntent(reply="Say what to close or keep — for example, delete any news tabs.")

    cutoff: int | None = None
    cut = _CUTOFF_RE.search(text)
    if cut:
        cutoff = _days(cut.group(1), cut.group(2))
    elif re.search(r"\b(unused|stale|haven['’]?t used)\b", text, re.IGNORECASE):
        num = _CUTOFF_NUM_RE.search(text)
        if num:
            cutoff = _days(num.group(1), num.group(2))
        elif re.search(r"\ba week\b", text, re.IGNORECASE):
            cutoff = 7

    hosts = _hosts_in(text)
    classes = _classes_in(text)
    keep: list[str] = []
    close: list[str] = []
    if _KEEP_RE.search(text):
        keep = hosts
        classes = []
    elif hosts and not classes:
        close = hosts

    wants_close = bool(_CLOSE_RE.search(text) or cutoff is not None) and not keep
    unused = cutoff if wants_close else None
    label = _label(classes, close, unused)
    return ChatIntent(
        stale_cutoff_days=cutoff,
        unused_days=unused,
        keep_hosts=keep,
        close_hosts=close,
        match_classes=classes,
        wants_close=wants_close,
        label=label,
        reply=_reply(
            cutoff,
            keep,
            close,
            wants_close=wants_close,
            label=label,
            unused_days=unused,
        ),
        parser="heuristic",
    )


def apply_chat(profile: HabitProfile, message: str, intent: ChatIntent) -> HabitProfile:
    summaries: list[str] = []
    if intent.stale_cutoff_days is not None:
        before = profile.stale_cutoff_days
        profile.stale_cutoff_days = max(1, min(int(intent.stale_cutoff_days), 90))
        summary = f"Unused cutoff {before} → {profile.stale_cutoff_days} days"
        summaries.append(summary)
        append_mutation(
            profile,
            Mutation(
                kind=FeedbackKind.CHAT,
                source="chat",
                summary=summary,
                before={"stale_cutoff_days": before},
                after={"stale_cutoff_days": profile.stale_cutoff_days},
                phrase=message,
            ),
        )
    for host in intent.keep_hosts:
        before = profile.rule_for(host)
        rule = upsert_rule(
            profile, host, ClosePolicy.ALWAYS_KEEP, phrase=message, source="chat"
        )
        summary = f"Keep {rule.host_suffix}"
        summaries.append(summary)
        append_mutation(
            profile,
            Mutation(
                kind=FeedbackKind.CHAT,
                source="chat",
                summary=summary,
                host_suffix=rule.host_suffix,
                before={"policy": before.close_policy.value if before else None},
                after={"policy": rule.close_policy.value},
                phrase=message,
            ),
        )
    for host in intent.close_hosts:
        before = profile.rule_for(host)
        rule = upsert_rule(
            profile, host, ClosePolicy.FILE_THEN_CLOSE, phrase=message, source="chat"
        )
        summary = f"Ok to close {rule.host_suffix}"
        summaries.append(summary)
        append_mutation(
            profile,
            Mutation(
                kind=FeedbackKind.CHAT,
                source="chat",
                summary=summary,
                host_suffix=rule.host_suffix,
                before={"policy": before.close_policy.value if before else None},
                after={"policy": rule.close_policy.value},
                phrase=message,
            ),
        )
    for cls in intent.match_classes:
        if cls not in profile.close_classes:
            before_classes = list(profile.close_classes)
            profile.close_classes.append(cls)
            summary = f"Class {cls}: list and close from chat"
            summaries.append(summary)
            append_mutation(
                profile,
                Mutation(
                    kind=FeedbackKind.CHAT,
                    source="chat",
                    summary=summary,
                    before={"close_classes": before_classes},
                    after={"close_classes": list(profile.close_classes)},
                    phrase=message,
                ),
            )

    profile.statements.insert(
        0,
        PreferenceStatement(
            text=message,
            parsed=intent.model_dump(mode="json"),
            active=bool(summaries),
        ),
    )
    profile.statements = profile.statements[:MAX_STATEMENTS]
    profile.chats.insert(0, ChatTurn(role="assistant", text=intent.reply, mutations=summaries))
    profile.chats.insert(0, ChatTurn(role="user", text=message, mutations=summaries))
    profile.chats = profile.chats[:MAX_CHATS]
    profile.touch()
    return profile


def interpret_preference(message: str) -> ChatIntent:
    heuristic = parse_preference(message)
    gemini = _try_gemini(message)
    if gemini is None:
        return heuristic
    merged = ChatIntent(
        stale_cutoff_days=gemini.stale_cutoff_days or heuristic.stale_cutoff_days,
        unused_days=gemini.unused_days or heuristic.unused_days,
        keep_hosts=_uniq([*gemini.keep_hosts, *heuristic.keep_hosts]),
        close_hosts=_uniq([*gemini.close_hosts, *heuristic.close_hosts]),
        match_classes=_uniq([*gemini.match_classes, *heuristic.match_classes]),
        wants_close=gemini.wants_close or heuristic.wants_close,
        label=gemini.label or heuristic.label,
        reply=gemini.reply or heuristic.reply,
        parser="gemini",
    )
    if not merged.reply:
        merged.reply = _reply(
            merged.stale_cutoff_days,
            merged.keep_hosts,
            merged.close_hosts,
            wants_close=merged.wants_close,
            label=merged.label,
            unused_days=merged.unused_days,
        )
    return merged


def _try_gemini(message: str) -> ChatIntent | None:
    import os

    if os.environ.get("PYTEST_CURRENT_TEST"):
        return None
    settings = get_settings()
    if not settings.has_gemini:
        return None
    prompt = (
        "Extract tab-closing intent as JSON with keys "
        "stale_cutoff_days (int or null), unused_days (int or null), "
        "keep_hosts (string[]), close_hosts (string[]), "
        "match_classes (string[] from news|listing|search|mail|docs), "
        "wants_close (bool), label (short), reply (short). "
        "If they ask to delete/close a kind of tab, set wants_close true "
        "and match_classes — do not say 'when stale'. User said:\n"
        f"{message[:500]}"
    )
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.fast_model}:generateContent"
    )
    try:
        response = httpx.post(
            url,
            params={"key": settings.google_api_key},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"responseMimeType": "application/json"},
            },
            timeout=8.0,
        )
        response.raise_for_status()
        data = response.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        raw: dict[str, Any] = json.loads(text)
    except Exception:
        return None
    days = raw.get("stale_cutoff_days")
    cutoff = int(days) if isinstance(days, int) and 1 <= days <= 90 else None
    return ChatIntent(
        stale_cutoff_days=cutoff,
        unused_days=cutoff if raw.get("wants_close") else None,
        keep_hosts=_hosts_from(raw.get("keep_hosts")),
        close_hosts=_hosts_from(raw.get("close_hosts")),
        match_classes=_uniq(str(x).lower() for x in (raw.get("match_classes") or []) if str(x).strip()),
        wants_close=bool(raw.get("wants_close")),
        label=str(raw.get("label") or "")[:80],
        reply=str(raw.get("reply") or "")[:400],
        parser="gemini",
    )


def _days(count: str | None, unit: str) -> int:
    n = int(count) if count else 1
    return max(1, min(n * _UNIT[unit.lower()], 90))


def _hosts_in(text: str) -> list[str]:
    found = [h.lower().removeprefix("www.") for h in _HOST_RE.findall(text)]
    lower = text.lower()
    for alias, host in _ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", lower):
            found.append(host)
    return _uniq(found)


def _hosts_from(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return _uniq(str(item).lower().removeprefix("www.") for item in value if str(item).strip())


def _uniq(items: list[str] | Any) -> list[str]:
    out: list[str] = []
    for item in items:
        host = str(item).lower().removeprefix("www.").strip()
        if host and host not in out:
            out.append(host)
    return out


def _classes_in(text: str) -> list[str]:
    lower = text.lower()
    found: list[str] = []
    for word, cls in _CLASS_WORDS.items():
        if re.search(rf"\b{re.escape(word)}\b", lower) and cls not in found:
            found.append(cls)
    return found


def _label(classes: list[str], hosts: list[str], unused: int | None) -> str:
    if classes:
        return f"{classes[0]} tabs"
    if hosts:
        return f"{hosts[0]} tabs"
    if unused:
        return f"tabs unused {unused} day{'s' if unused != 1 else ''}"
    return "matching tabs"


def _reply(
    cutoff: int | None,
    keep: list[str],
    close: list[str],
    *,
    wants_close: bool,
    label: str,
    unused_days: int | None,
) -> str:
    if keep:
        return "I'll keep " + ", ".join(keep) + "."
    if wants_close:
        extra = ""
        if unused_days:
            extra = f" unused for {unused_days} day{'s' if unused_days != 1 else ''}"
        who = label or "matching tabs"
        return f"Here are the {who}{extra}. Close them now, or schedule a time."
    if cutoff is not None:
        return f"I'll flag tabs unused for {cutoff} day{'s' if cutoff != 1 else ''}."
    if close:
        return "I'll look for " + ", ".join(close) + "."
    return (
        "Try: “delete any news tabs”, “delete tabs I haven't used in a week”, "
        "or “never close github.com”."
    )


__all__ = ["apply_chat", "interpret_preference", "parse_preference"]
