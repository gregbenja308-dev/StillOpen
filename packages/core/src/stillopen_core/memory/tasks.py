"""Infer named tasks from a window. Chrome groups are a prior; host class is not the key."""

from __future__ import annotations

import json
import os
import re
import time
from collections import defaultdict

import httpx

from stillopen_core.agents.framer import frame
from stillopen_core.config import get_settings
from stillopen_core.observability.logger import get_logger
from stillopen_core.schemas.tab import HostClass, Intention, SanitizedTab, TabSnapshot
from stillopen_core.schemas.task import OpenTask, TaskKind
from stillopen_core.surveyor.sanitize import sanitize_tabs

_logger = get_logger(__name__)
_DAY_MS = 24 * 60 * 60 * 1000
_PLACE = re.compile(r"\b([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)\b")


def infer_tasks(
    tabs: list[TabSnapshot],
    *,
    cutoff_days: int = 7,
    now_ms: int | None = None,
) -> list[OpenTask]:
    sanitized = sanitize_tabs(tabs)
    now = now_ms if now_ms is not None else int(time.time() * 1000)
    quiet_ms = max(1, cutoff_days) * _DAY_MS

    protected = [t for t in sanitized if t.blocked_from_model]
    rest = [t for t in sanitized if not t.blocked_from_model]

    grouped: dict[int, list[SanitizedTab]] = defaultdict(list)
    ungrouped: list[SanitizedTab] = []
    for tab in rest:
        if tab.group_id >= 0:
            grouped[tab.group_id].append(tab)
        else:
            ungrouped.append(tab)

    tasks: list[OpenTask] = []
    for members in grouped.values():
        label = (members[0].group_title or "").strip() or _label_members(members)
        tasks.append(_from_members(label, members, now=now, quiet_ms=quiet_ms))

    for members, intention in _cluster_ungrouped(ungrouped):
        tasks.append(
            _from_members(
                _goal_label(intention, members),
                members,
                now=now,
                quiet_ms=quiet_ms,
                intention=intention,
            )
        )

    if protected:
        tasks.append(
            _from_members(
                "Leave these off the model",
                protected,
                now=now,
                quiet_ms=quiet_ms,
                kind=TaskKind.PROTECTED,
            )
        )

    refined = _try_gemini(rest, tasks)
    if refined:
        tasks = _merge_labels(tasks, refined)

    tasks.sort(key=_sort_key)
    _logger.info("tasks.inferred", count=len(tasks))
    return tasks


_WEAK_TOKENS = frozenset(
    {
        "www",
        "com",
        "net",
        "org",
        "http",
        "https",
        "html",
        "the",
        "and",
        "for",
        "search",
        "google",
        "bing",
        "index",
        "home",
        "php",
    }
)


def _tab_tokens(tab: SanitizedTab) -> set[str]:
    blob = f"{tab.title} {tab.host} {tab.url}".lower()
    return {t for t in re.findall(r"[a-z0-9]+", blob) if len(t) > 2 and t not in _WEAK_TOKENS}


def _cluster_ungrouped(tabs: list[SanitizedTab]) -> list[tuple[list[SanitizedTab], Intention]]:
    """One listing job (plus the search that started it), then leftover intention piles."""
    if not tabs:
        return []
    listings = [t for t in tabs if t.host_class is HostClass.LISTING]
    rest = [t for t in tabs if t.host_class is not HostClass.LISTING]
    out: list[tuple[list[SanitizedTab], Intention]] = []
    used: set[int] = set()

    if listings:
        listing_tokens: set[str] = set()
        for tab in listings:
            listing_tokens |= _tab_tokens(tab)
        attached = [
            t
            for t in rest
            if t.host_class is HostClass.SEARCH and (_tab_tokens(t) & listing_tokens)
        ]
        members = [*listings, *attached]
        used.update(t.tab_id for t in members)
        out.append((members, Intention.COMPARING))

    leftover = [t for t in tabs if t.tab_id not in used]
    if leftover:
        for card in frame(leftover, command=None):
            members = [t for t in leftover if t.tab_id in card.tab_ids]
            if members:
                out.append((members, card.intention))
    return out


def _from_members(
    label: str,
    members: list[SanitizedTab],
    *,
    now: int,
    quiet_ms: int,
    kind: TaskKind | None = None,
    intention: Intention | None = None,
) -> OpenTask:
    intention = intention or _guess_intention(members)
    if kind is None:
        if any(t.blocked_from_model for t in members):
            kind = TaskKind.PROTECTED
        elif intention in {Intention.COMPARING, Intention.WAITING, Intention.HALF_DONE} or (
            intention is Intention.READ_LATER and len(members) >= 2
        ):
            kind = TaskKind.DURABLE
        else:
            kind = TaskKind.EPHEMERAL
    quiet = all(
        t.last_accessed_ms is not None and now - t.last_accessed_ms >= quiet_ms for t in members
    )
    hosts = sorted({t.host.removeprefix("www.") for t in members})
    return OpenTask(
        label=label[:48],
        tab_ids=[t.tab_id for t in members],
        kind=kind,
        hosts=hosts,
        titles=[t.title for t in members][:8],
        group_title=(members[0].group_title if members else "") or "",
        quiet=quiet,
        intention=intention,
    )


def _guess_intention(members: list[SanitizedTab]) -> Intention:
    cards = frame(members, command=None)
    if len(cards) == 1:
        return cards[0].intention
    if any(c.intention is Intention.COMPARING for c in cards):
        return Intention.COMPARING
    return cards[0].intention if cards else Intention.UNKNOWN


def _goal_label(intention: Intention, members: list[SanitizedTab]) -> str:
    place = _place(members)
    if intention is Intention.COMPARING:
        return f"Find a place in {place}" if place else "Compare these listings"
    if intention is Intention.WAITING:
        return f"Wait on {members[0].host.removeprefix('www.')}"
    if intention is Intention.READ_LATER:
        return members[0].title[:40] if len(members) == 1 else "Finish this reading"
    if intention is Intention.HALF_DONE:
        return "Finish this form"
    if intention is Intention.REFERENCE:
        return "Keep as reference"
    if intention is Intention.ZOMBIE:
        if all(t.host_class is HostClass.SEARCH for t in members):
            return "Clear leftover searches"
        return "Close leftover tabs"
    if len(members) == 1:
        return _short(members[0].title, members[0].host)
    return _label_members(members)


def _label_members(members: list[SanitizedTab]) -> str:
    if all(t.host_class is HostClass.LISTING for t in members):
        place = _place(members)
        return f"Find a place in {place}" if place else "Compare these listings"
    if len(members) == 1:
        return _short(members[0].title, members[0].host)
    return f"{len(members)} related tabs"


def _place(members: list[SanitizedTab]) -> str:
    blob = " ".join(f"{t.title} {t.url}" for t in members)
    for match in _PLACE.findall(blob):
        if (
            match.lower() not in {"http", "https", "www", "com", "the"}
            and match[0].isupper()
            and len(match) > 3
        ):
            return match
    lower = blob.lower()
    for city in ("austin", "seattle", "portland", "denver", "chicago"):
        if city in lower:
            return city.title()
    return ""


def _short(title: str, host: str) -> str:
    words = [w for w in re.split(r"\s+", title.strip()) if w][:6]
    return " ".join(words) if words else host.removeprefix("www.")


def _sort_key(task: OpenTask) -> tuple[int, int, str]:
    kind_rank = {TaskKind.DURABLE: 0, TaskKind.EPHEMERAL: 1, TaskKind.PROTECTED: 2}[task.kind]
    return (kind_rank, 1 if task.quiet else 0, task.label.lower())


def _try_gemini(visible: list[SanitizedTab], tasks: list[OpenTask]) -> list[OpenTask] | None:
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return None
    settings = get_settings()
    if not settings.has_gemini or not visible or not tasks:
        return None
    lines = [
        f"{t.tab_id}\t{t.host}\t{(t.group_title or '-')}\t{(t.title or t.host)[:80]}"
        for t in visible[:40]
    ]
    prompt = (
        "These browser tabs are leftover from the user's goals. "
        "Name each goal in 2-6 words (a task, not a category: "
        "not 'Housing', yes 'Find a rental in Austin'). "
        'Return JSON only: {"tasks":[{"label":"...","tab_ids":[1,2]}]}. '
        "Use each tab_id at most once. Prefer existing Chrome group names when they name a goal.\n"
        + "\n".join(lines)
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
        text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
        raw = json.loads(text)
    except Exception:
        return None
    known = {t.tab_id for t in visible}
    out: list[OpenTask] = []
    seen: set[int] = set()
    by_id = {t.tab_id: t for t in visible}
    for row in raw.get("tasks") or []:
        if not isinstance(row, dict):
            continue
        label = str(row.get("label") or "").strip()[:48]
        ids = [
            int(i)
            for i in (row.get("tab_ids") or [])
            if str(i).lstrip("-").isdigit() and int(i) in known and int(i) not in seen
        ]
        if not label or not ids:
            continue
        seen.update(ids)
        members = [by_id[i] for i in ids]
        out.append(_from_members(label, members, now=int(time.time() * 1000), quiet_ms=7 * _DAY_MS))
    return out or None


def _merge_labels(base: list[OpenTask], refined: list[OpenTask]) -> list[OpenTask]:
    """Keep protected tasks. Gemini may relabel; uncovered tabs stay with their original task."""
    protected = [t for t in base if t.kind is TaskKind.PROTECTED]
    covered = {i for t in refined for i in t.tab_ids}
    leftover: list[OpenTask] = []
    for task in base:
        if task.kind is TaskKind.PROTECTED:
            continue
        missing = [i for i in task.tab_ids if i not in covered]
        if not missing:
            continue
        if len(missing) == len(task.tab_ids):
            leftover.append(task)
            continue
        leftover.append(
            task.model_copy(
                update={
                    "tab_ids": missing,
                    "hosts": task.hosts,
                    "titles": task.titles,
                }
            )
        )
    return [*refined, *leftover, *protected]


__all__ = ["infer_tasks"]
