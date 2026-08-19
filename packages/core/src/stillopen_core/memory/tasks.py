"""Infer named tasks from a window. The model groups by goal; heuristics are fallback."""

from __future__ import annotations

import json
import os
import re
import time
from collections import defaultdict
from urllib.parse import parse_qs, unquote_plus, urlsplit

import httpx

from stillopen_core.agents.framer import frame
from stillopen_core.config import get_settings
from stillopen_core.observability.logger import get_logger
from stillopen_core.schemas.tab import HostClass, Intention, SanitizedTab, TabSnapshot
from stillopen_core.schemas.task import OpenTask, TaskKind
from stillopen_core.surveyor.sanitize import sanitize_tabs

_logger = get_logger(__name__)
_DAY_MS = 24 * 60 * 60 * 1000
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
        "wiki",
        "wikipedia",
        "section",
    }
)
_LOOKUP_HINTS = ("wiki", "dictionary", "define", "meaning", "thesaurus", "wiktionary")
_SEARCH_QUERY_KEYS = ("q", "query", "search_query", "k", "st", "p", "text", "wd")
_MAX_CLUSTER_TOKEN = 24
_MAX_NAME_TOKEN = 16


def infer_tasks(
    tabs: list[TabSnapshot],
    *,
    cutoff_days: int = 7,
    now_ms: int | None = None,
    existing: list[OpenTask] | None = None,
    ignored_urls: list[str] | None = None,
) -> list[OpenTask]:
    sanitized = sanitize_tabs(tabs)
    now = now_ms if now_ms is not None else int(time.time() * 1000)
    quiet_ms = max(1, cutoff_days) * _DAY_MS
    ignored = {_canon(u) for u in (ignored_urls or []) if u}
    visible = [t for t in sanitized if _canon(t.url) not in ignored]

    if existing:
        tasks = _reconcile(visible, existing, now=now, quiet_ms=quiet_ms)
        tasks.sort(key=_sort_key)
        _logger.info("tasks.reconciled", count=len(tasks), existing=len(existing))
        return tasks

    protected = [t for t in visible if t.blocked_from_model]
    rest = [t for t in visible if not t.blocked_from_model]
    tasks = _cluster(rest, now=now, quiet_ms=quiet_ms)
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
    tasks.sort(key=_sort_key)
    _logger.info("tasks.inferred", count=len(tasks))
    return tasks


def _cluster(tabs: list[SanitizedTab], *, now: int, quiet_ms: int) -> list[OpenTask]:
    if not tabs:
        return []
    modeled = _gemini_tasks(tabs, now=now, quiet_ms=quiet_ms)
    if modeled:
        modeled, leftover = _attach_to_tasks(modeled, tabs, now=now, quiet_ms=quiet_ms)
        return [*modeled, *_fallback_tasks(leftover, now=now, quiet_ms=quiet_ms)]
    return _fallback_tasks(tabs, now=now, quiet_ms=quiet_ms)


def _fallback_tasks(tabs: list[SanitizedTab], *, now: int, quiet_ms: int) -> list[OpenTask]:
    """Token overlap only — no host-class buckets, no site-specific rules."""
    out: list[OpenTask] = []
    for members in _fallback_groups(tabs):
        out.append(
            _from_members(
                _goal_label(members),
                members,
                now=now,
                quiet_ms=quiet_ms,
                intention=_guess_intention(members),
            )
        )
    return out


def _fold(token: str) -> str:
    """ephemeral / ephemerality should count as the same lookup."""
    if len(token) < 6:
        return token
    for suffix in (
        "ities",
        "iness",
        "ation",
        "tions",
        "tion",
        "ment",
        "ness",
        "ally",
        "ing",
        "ity",
        "ies",
        "ers",
        "er",
        "ed",
        "es",
        "s",
    ):
        stem = token[: -len(suffix)]
        if token.endswith(suffix) and len(stem) >= 4:
            return stem
    return token


_CAMEL = re.compile(r"[A-Z][a-z]{2,}")


def _is_noise_token(token: str, *, naming: bool = False) -> bool:
    """IDs, hashes, and letter-salad query blobs are not task names."""
    t = token.lower()
    if len(t) < 3 or t in _WEAK_TOKENS:
        return True
    limit = _MAX_NAME_TOKEN if naming else _MAX_CLUSTER_TOKEN
    if len(t) > limit:
        return True
    if t.isdigit():
        return True
    if re.fullmatch(r"[0-9a-f]{8,}", t) and any(c.isdigit() for c in t):
        return True
    digits = sum(c.isdigit() for c in t)
    if digits >= 2 and len(t) >= 8:
        return True
    if digits >= 1 and len(t) >= 11:
        return True
    vowels = sum(c in "aeiou" for c in t)
    return len(t) >= 8 and vowels < 2


def _search_query_text(query: str) -> str:
    if not query:
        return ""
    bits: list[str] = []
    parsed = parse_qs(query, keep_blank_values=False)
    for key in _SEARCH_QUERY_KEYS:
        for raw in parsed.get(key, []):
            text = unquote_plus(raw).replace("+", " ").strip()
            if not text:
                continue
            compact = re.sub(r"[^a-z0-9]+", "", text.lower())
            if " " not in text and _is_noise_token(compact, naming=True):
                continue
            bits.append(text)
    return " ".join(bits)


def _url_text(tab: SanitizedTab) -> str:
    """Title + host + path + human search query. No tracking params."""
    parts = urlsplit(tab.url)
    path = (parts.path or "").replace("-", " ").replace("_", " ").replace("/", " ")
    return f"{tab.title} {tab.host} {path} {_search_query_text(parts.query)}"


def _plain_words(text: str) -> list[str]:
    """Split identifiers. Skip mixed alphanum IDs so they cannot become labels."""
    words: list[str] = []
    for word in re.split(r"[^a-zA-Z0-9]+", text):
        if not word or any(c.isdigit() for c in word):
            continue
        words.append(word)
    return words


def _tab_tokens(tab: SanitizedTab) -> set[str]:
    raw: set[str] = set()
    for word in _plain_words(_url_text(tab)):
        raw.add(word.lower())
        raw.update(m.lower() for m in _CAMEL.findall(word))
        raw.update(re.findall(r"[a-z]{3,}", word.lower()))
    raw = {t for t in raw if not _is_noise_token(t)}
    return {t for t in (raw | {_fold(t) for t in raw}) if not _is_noise_token(t)}


def _compound_parts(token: str, known: set[str]) -> set[str]:
    """austinapartments → austin + apartments; not homes ⊂ realestateandhomes."""
    extra: set[str] = set()
    for word in known:
        if word == token or len(word) < 5:
            continue
        if token.startswith(word):
            rest = token[len(word) :]
            if rest in known or _fold(rest) in known:
                extra.add(word)
        if token.endswith(word):
            rest = token[: -len(word)]
            if rest in known or _fold(rest) in known:
                extra.add(word)
    return extra


def _expand_contained(tokens_by_id: dict[int, set[str]]) -> dict[int, set[str]]:
    known = {w for toks in tokens_by_id.values() for w in toks if len(w) >= 5}
    out: dict[int, set[str]] = {}
    for tab_id, toks in tokens_by_id.items():
        extra = set(toks)
        for token in toks:
            extra.update(_compound_parts(token, known))
        out[tab_id] = extra
    return out


def _brand_tokens(tab: SanitizedTab) -> set[str]:
    host = tab.host.removeprefix("www.").lower().replace(".", " ")
    return {t for t in re.findall(r"[a-z0-9]+", host) if len(t) > 2}


def _content_tokens(tab: SanitizedTab) -> set[str]:
    brands = _brand_tokens(tab)
    return {
        t
        for t in _tab_tokens(tab)
        if t not in brands and _fold(t) not in brands and not _is_noise_token(t, naming=True)
    }


def _fallback_groups(tabs: list[SanitizedTab]) -> list[list[SanitizedTab]]:
    groups = _split_by_tokens(tabs)
    news: list[SanitizedTab] = []
    rest: list[list[SanitizedTab]] = []
    for group in groups:
        if group and all(t.host_class is HostClass.NEWS for t in group):
            news.extend(group)
        else:
            rest.append(group)
    if news:
        rest.append(news)
    return rest


def _split_by_tokens(tabs: list[SanitizedTab]) -> list[list[SanitizedTab]]:
    if not tabs:
        return []
    parent = {t.tab_id: t.tab_id for t in tabs}

    def find(tab_id: int) -> int:
        while parent[tab_id] != tab_id:
            parent[tab_id] = parent[parent[tab_id]]
            tab_id = parent[tab_id]
        return tab_id

    def union(left: int, right: int) -> None:
        root_l, root_r = find(left), find(right)
        if root_l != root_r:
            parent[root_r] = root_l

    tokens = _expand_contained({t.tab_id: _tab_tokens(t) for t in tabs})
    for left in tabs:
        for right in tabs:
            if left.tab_id >= right.tab_id:
                continue
            if tokens[left.tab_id] & tokens[right.tab_id]:
                union(left.tab_id, right.tab_id)
    groups: dict[int, list[SanitizedTab]] = defaultdict(list)
    for tab in tabs:
        groups[find(tab.tab_id)].append(tab)
    return list(groups.values())


def _canon(url: str) -> str:
    parts = urlsplit(url)
    host = (parts.hostname or "").removeprefix("www.").lower()
    path = (parts.path or "/").rstrip("/") or "/"
    return f"{host}{path}"


def _blob_tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if not _is_noise_token(t)}


def _score_tab(tab: SanitizedTab, task: OpenTask) -> int:
    hay = _blob_tokens(f"{task.label} {' '.join(task.titles)} {' '.join(task.hosts)}")
    hay |= {_fold(t) for t in hay}
    tab_toks = set(_tab_tokens(tab))
    known = {w for w in hay if len(w) >= 5}
    for token in list(tab_toks):
        tab_toks.update(_compound_parts(token, known))
    score = len(tab_toks & hay)
    host = tab.host.removeprefix("www.")
    if host in task.hosts:
        score += 2
    if tab.host_class is HostClass.SEARCH and score >= 1:
        score += 1
    return score


def _attach_to_tasks(
    tasks: list[OpenTask],
    tabs: list[SanitizedTab],
    *,
    now: int,
    quiet_ms: int,
) -> tuple[list[OpenTask], list[SanitizedTab]]:
    """Put leftover tabs into an existing task when they are clearly the same job."""
    by_id = {t.tab_id: t for t in tabs}
    used = {i for task in tasks for i in task.tab_ids}
    leftover = [t for t in tabs if t.tab_id not in used and not t.blocked_from_model]
    kept = list(tasks)
    still: list[SanitizedTab] = []
    for tab in leftover:
        best_i = -1
        best = 0
        for i, task in enumerate(kept):
            if task.kind is TaskKind.PROTECTED:
                continue
            score = _score_tab(tab, task)
            if score > best:
                best = score
                best_i = i
        if best >= 2 and best_i >= 0:
            parent = kept[best_i]
            extra = [by_id[i] for i in parent.tab_ids if i in by_id]
            extra.append(tab)
            kept[best_i] = _from_members(
                parent.label,
                extra,
                now=now,
                quiet_ms=quiet_ms,
                kind=parent.kind,
                intention=parent.intention,
                task_id=parent.task_id,
                user_locked=parent.user_locked,
            )
        else:
            still.append(tab)
    return kept, still


def _reconcile(
    live: list[SanitizedTab],
    existing: list[OpenTask],
    *,
    now: int,
    quiet_ms: int,
) -> list[OpenTask]:
    """Keep user tasks; drop closed tabs; attach or cluster leftovers."""
    by_id = {t.tab_id: t for t in live}
    by_canon: dict[str, list[SanitizedTab]] = defaultdict(list)
    for tab in live:
        by_canon[_canon(tab.url)].append(tab)

    assigned: set[int] = set()
    kept: list[OpenTask] = []
    for task in existing:
        if task.kind is TaskKind.PROTECTED:
            continue
        members: list[SanitizedTab] = []
        seen: set[int] = set()
        for tab_id in task.tab_ids:
            tab = by_id.get(tab_id)
            if tab and tab.tab_id not in seen:
                members.append(tab)
                seen.add(tab.tab_id)
        for url in task.urls:
            for tab in by_canon.get(_canon(url), []):
                if tab.tab_id not in seen:
                    members.append(tab)
                    seen.add(tab.tab_id)
        if not members and not task.user_locked:
            continue
        assigned.update(m.tab_id for m in members)
        if members:
            kept.append(
                _from_members(
                    task.label,
                    members,
                    now=now,
                    quiet_ms=quiet_ms,
                    kind=task.kind,
                    intention=task.intention,
                    task_id=task.task_id,
                    user_locked=task.user_locked,
                )
            )
        else:
            kept.append(
                task.model_copy(
                    update={"tab_ids": [], "urls": [], "hosts": [], "titles": [], "quiet": False}
                )
            )

    leftover = [t for t in live if t.tab_id not in assigned and not t.blocked_from_model]
    still: list[SanitizedTab] = []
    for tab in leftover:
        best_i = -1
        best = 0
        for i, task in enumerate(kept):
            if task.kind is TaskKind.PROTECTED:
                continue
            score = _score_tab(tab, task)
            if score > best:
                best = score
                best_i = i
        if best >= 2 and best_i >= 0:
            parent = kept[best_i]
            extra = [by_id[i] for i in parent.tab_ids if i in by_id]
            extra.append(tab)
            assigned.add(tab.tab_id)
            kept[best_i] = _from_members(
                parent.label,
                extra,
                now=now,
                quiet_ms=quiet_ms,
                kind=parent.kind,
                intention=parent.intention,
                task_id=parent.task_id,
                user_locked=parent.user_locked,
            )
        else:
            still.append(tab)

    kept.extend(_cluster(still, now=now, quiet_ms=quiet_ms))

    protected = [t for t in live if t.blocked_from_model]
    if protected:
        prev = next((t for t in existing if t.kind is TaskKind.PROTECTED), None)
        kept.append(
            _from_members(
                prev.label if prev and prev.user_locked else "Leave these off the model",
                protected,
                now=now,
                quiet_ms=quiet_ms,
                kind=TaskKind.PROTECTED,
                task_id=prev.task_id if prev else None,
                user_locked=bool(prev and prev.user_locked),
            )
        )
    return kept


def _from_members(
    label: str,
    members: list[SanitizedTab],
    *,
    now: int,
    quiet_ms: int,
    kind: TaskKind | None = None,
    intention: Intention | None = None,
    task_id: str | None = None,
    user_locked: bool = False,
) -> OpenTask:
    intention = intention or (_guess_intention(members) if members else Intention.UNKNOWN)
    if kind is None:
        if any(t.blocked_from_model for t in members):
            kind = TaskKind.PROTECTED
        elif intention in {Intention.COMPARING, Intention.WAITING, Intention.HALF_DONE} or (
            intention is Intention.READ_LATER and len(members) >= 2
        ):
            kind = TaskKind.DURABLE
        else:
            kind = TaskKind.EPHEMERAL
    quiet = bool(members) and all(
        t.last_accessed_ms is not None and now - t.last_accessed_ms >= quiet_ms for t in members
    )
    hosts = sorted({t.host.removeprefix("www.") for t in members})
    payload: dict[str, object] = {
        "label": label[:48],
        "tab_ids": [t.tab_id for t in members],
        "kind": kind,
        "hosts": hosts,
        "titles": [t.title for t in members][:8],
        "urls": [t.url for t in members],
        "group_title": (members[0].group_title if members else "") or "",
        "quiet": quiet,
        "intention": intention,
        "user_locked": user_locked,
    }
    if task_id:
        payload["task_id"] = task_id
    return OpenTask.model_validate(payload)


def _guess_intention(members: list[SanitizedTab]) -> Intention:
    cards = frame(members, command=None)
    if len(cards) == 1:
        return cards[0].intention
    if any(c.intention is Intention.COMPARING for c in cards):
        return Intention.COMPARING
    return cards[0].intention if cards else Intention.UNKNOWN


def _goal_label(members: list[SanitizedTab]) -> str:
    """A todo the user could mark done — never the page title or site name."""
    topic = _shared_name(members) or (_topic_from_one(members[0]) if members else "")
    blob = " ".join(_url_text(t) for t in members).lower()
    if any(hint in blob for hint in _LOOKUP_HINTS):
        return f"Definition for {topic}" if topic else "Look this up"
    if all(t.host_class is HostClass.NEWS for t in members):
        return "Reading today's news"
    if "track" in blob:
        return "Track this shipment"
    if any(t.host_class is HostClass.LISTING for t in members):
        return f"Compare {topic} options" if topic else "Compare these options"
    if any(t.host_class is HostClass.SEARCH for t in members):
        return f"Look up {topic}" if topic else "Look this up"
    if topic:
        return f"Finish this {topic} work"
    fallback = _short(members[0].title, members[0].host) if members else ""
    return fallback if fallback and not _label_has_noise(fallback) else "Unfinished task"


def _shared_name(members: list[SanitizedTab]) -> str:
    token_sets = [_content_tokens(m) for m in members]
    if not token_sets:
        return ""
    shared = set.intersection(*token_sets) if len(token_sets) > 1 else token_sets[0]
    if not shared:
        return ""
    word = max(shared, key=len)
    if len(word) < 4:
        return ""
    return word.replace("-", " ").title()


def _topic_from_one(tab: SanitizedTab) -> str:
    tokens = _content_tokens(tab)
    if not tokens:
        return ""
    word = max(tokens, key=len)
    if len(word) < 4:
        return ""
    return word.replace("-", " ").title()


def _norm_label(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _label_has_noise(text: str) -> bool:
    return any(
        len(tok) >= 8 and _is_noise_token(tok, naming=True)
        for tok in re.findall(r"[a-z0-9]+", text.lower())
    )


def _copies_tab_title(label: str, members: list[SanitizedTab]) -> bool:
    """'BBC News' and 'Ephemerality - Wikipedia' are tabs, not tasks."""
    got = _norm_label(label)
    if not got:
        return True
    if len(got.split()) < 2:
        return True
    for tab in members:
        title = _norm_label(tab.title or "")
        if not title:
            continue
        stem = re.split(r" wikipedia| google search", title, maxsplit=1)[0].strip()
        if got in {title, stem}:
            return True
        brand = tab.host.removeprefix("www.").split(".")[0]
        if got in {brand, f"{brand} news"}:
            return True
    return False


def _task_label(label: str, members: list[SanitizedTab]) -> str:
    cleaned = label.strip()
    if cleaned and not _copies_tab_title(cleaned, members) and not _label_has_noise(cleaned):
        return cleaned[:48]
    return _goal_label(members)[:48]


def _short(title: str, host: str) -> str:
    words = [
        w
        for w in re.split(r"\s+", title.strip())
        if w and not _is_noise_token(re.sub(r"[^a-z0-9]+", "", w.lower()), naming=True)
    ][:6]
    return " ".join(words) if words else host.removeprefix("www.")


def _sort_key(task: OpenTask) -> tuple[int, int, str]:
    kind_rank = {TaskKind.DURABLE: 0, TaskKind.EPHEMERAL: 1, TaskKind.PROTECTED: 2}[task.kind]
    return (kind_rank, 1 if task.quiet else 0, task.label.lower())


def _cluster_prompt(tabs: list[SanitizedTab]) -> str:
    lines = [f"{t.tab_id}\t{t.url[:160]}\t{(t.title or t.host)[:80]}" for t in tabs[:80]]
    return (
        "Group these open browser tabs into unfinished TASKS.\n"
        "A task is something the person meant to finish, written like a todo.\n"
        "The label is the job, never the tab title, never the site name.\n"
        "\n"
        "WRONG labels (these are tabs/topics): 'Ephemeral', 'BBC News', "
        "'Ephemerality - Wikipedia', 'MacBook Air', 'Google'.\n"
        "RIGHT labels (these are tasks): 'Definition for ephemeral', "
        "'Reading today's news', 'Compare MacBook Air prices', "
        "'Track this UPS package'.\n"
        "\n"
        "Grouping:\n"
        "- Dictionary + Wikipedia + a Google search about the same word are "
        "ONE task, including inflected forms (ephemeral / ephemerality).\n"
        "- Homepage/section news tabs are ONE 'Reading today's news' task "
        "unless they are clearly different stories.\n"
        "- Different jobs stay split even on similar sites "
        "(rentals vs laptop shopping).\n"
        "- A related search belongs with the job it started.\n"
        "- A forum, subreddit, or Q&A thread about the same job stays in "
        "that task (r/AustinApartments belongs with Austin rentals).\n"
        "\n"
        "Rules:\n"
        "- Use only listed tab_id values; each exactly once.\n"
        "- Ignore Chrome tab-group names.\n"
        "- Never use URL ids, tracking params, or random letter-salad as the label.\n"
        "- Every label must be 3+ words and describe the job.\n"
        'Return JSON only: {"tasks":[{"label":"...","tab_ids":[1,2]}]}.\n' + "\n".join(lines)
    )


def _gemini_tasks(tabs: list[SanitizedTab], *, now: int, quiet_ms: int) -> list[OpenTask] | None:
    raw = _ask_gemini(_cluster_prompt(tabs))
    if not raw:
        return None
    known = {t.tab_id for t in tabs}
    by_id = {t.tab_id: t for t in tabs}
    out: list[OpenTask] = []
    seen: set[int] = set()
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
        out.append(_from_members(_task_label(label, members), members, now=now, quiet_ms=quiet_ms))
    if out:
        _logger.info("tasks.gemini", count=len(out), tabs=len(seen))
    return out or None


def _ask_gemini(prompt: str) -> dict | None:
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return None
    settings = get_settings()
    if not settings.has_gemini:
        return None
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
            timeout=20.0,
        )
        response.raise_for_status()
        text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
        raw = json.loads(text)
    except Exception as exc:
        _logger.warning("tasks.gemini_failed", error=str(exc)[:200])
        return None
    return raw if isinstance(raw, dict) else None


__all__ = ["infer_tasks"]
