"""Infer named tasks from a window. The model groups by goal; heuristics are fallback."""

from __future__ import annotations

import re
import time
from collections import defaultdict
from urllib.parse import parse_qs, unquote_plus, urlsplit

from stillopen_core.agents.framer import frame
from stillopen_core.gateway.gemini import TITLE_IS_DATA, generate_json
from stillopen_core.observability.logger import get_logger
from stillopen_core.schemas.tab import HostClass, Intention, SanitizedTab, TabSnapshot
from stillopen_core.schemas.task import OpenTask, TaskKind
from stillopen_core.security.armor import looks_like_injection
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
_SEARCH_QUERY_KEYS = ("q", "query", "search_query", "k", "st", "p", "text", "wd")
_MAX_CLUSTER_TOKEN = 24
_MAX_NAME_TOKEN = 16
_VAGUE_LABEL_WORDS = frozenset(
    {
        "sophisticated",
        "important",
        "complex",
        "serious",
        "misc",
        "miscellaneous",
        "various",
        "general",
        "random",
        "stuff",
        "things",
    }
)


def infer_tasks(
    tabs: list[TabSnapshot],
    *,
    cutoff_days: int = 7,
    now_ms: int | None = None,
    existing: list[OpenTask] | None = None,
    ignored_urls: list[str] | None = None,
    fast: bool = False,
) -> list[OpenTask]:
    sanitized = sanitize_tabs(tabs)
    now = now_ms if now_ms is not None else int(time.time() * 1000)
    quiet_ms = max(1, cutoff_days) * _DAY_MS
    ignored = {_canon(u) for u in (ignored_urls or []) if u}
    visible = [t for t in sanitized if _canon(t.url) not in ignored]

    if existing:
        tasks = _reconcile(visible, existing, now=now, quiet_ms=quiet_ms, fast=fast)
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


def _cluster_tokens(tab: SanitizedTab) -> set[str]:
    """Overlap for grouping. Hostnames do not count — site kind is not a task."""
    brands = _brand_tokens(tab)
    return {t for t in _tab_tokens(tab) if t not in brands and _fold(t) not in brands}


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
    """Registrable site name only (example.co.uk → example). Subdomains stay content."""
    host = tab.host.removeprefix("www.").lower()
    parts = [p for p in host.split(".") if p]
    if len(parts) >= 2:
        return {parts[-2], parts[-1]}
    return {p for p in parts if len(p) > 2}


def _content_tokens(tab: SanitizedTab) -> set[str]:
    brands = _brand_tokens(tab)
    return {
        t
        for t in _tab_tokens(tab)
        if t not in brands and _fold(t) not in brands and not _is_noise_token(t, naming=True)
    }


def _fallback_groups(tabs: list[SanitizedTab]) -> list[list[SanitizedTab]]:
    return _split_by_tokens(tabs)


def _compact(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _fragment_of_slug(tok: str, slug: str) -> bool:
    """Hyphen suffix of a longer slug ('python' in 'adk-python') is not the job."""
    if not slug:
        return False
    parts = [p for p in re.split(r"[-_/]+", slug.lower()) if p]
    t = tok.lower()
    if len(parts) < 2 or t == _compact(slug):
        return False
    if _fold(_compact(slug)) == t or _fold(_compact(slug)) == _fold(t):
        return False
    return t == parts[-1] and t != parts[0] and len(parts[0]) >= 3


def _same_job_overlap(
    left: set[str],
    right: set[str],
    left_slug: str,
    right_slug: str,
) -> bool:
    if left_slug and right_slug and left_slug.lower() == right_slug.lower():
        return True
    shared = left & right
    if not shared:
        return False
    shared = {
        tok
        for tok in shared
        if not _fragment_of_slug(tok, left_slug) and not _fragment_of_slug(tok, right_slug)
    }
    return bool(shared)


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

    tokens = _expand_contained({t.tab_id: _cluster_tokens(t) for t in tabs})
    slugs = {t.tab_id: _path_topic(t) for t in tabs}
    for left in tabs:
        for right in tabs:
            if left.tab_id >= right.tab_id:
                continue
            if _same_job_overlap(
                tokens[left.tab_id],
                tokens[right.tab_id],
                slugs[left.tab_id],
                slugs[right.tab_id],
            ):
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
                notes=parent.notes,
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
    fast: bool = False,
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
                    notes=task.notes,
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
                notes=parent.notes,
            )
        else:
            still.append(tab)

    kept.extend(
        _fallback_tasks(still, now=now, quiet_ms=quiet_ms)
        if fast
        else _cluster(still, now=now, quiet_ms=quiet_ms)
    )

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
                notes=prev.notes if prev else "",
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
    notes: str = "",
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
        "notes": notes[:4000],
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


def _path_topic(tab: SanitizedTab) -> str:
    """Last meaningful path slug. Same rule on every host — not a site list."""
    segs = [unquote_plus(s) for s in urlsplit(tab.url).path.split("/") if s]
    useful: list[str] = []
    for seg in segs:
        compact = re.sub(r"[^a-z0-9]+", "", seg.lower())
        if len(compact) < 4 or _is_noise_token(compact, naming=True):
            continue
        useful.append(seg)
    return useful[-1] if useful else ""


def _display_topic(raw: str) -> str:
    return re.sub(r"[-_/]+", " ", raw).strip().title()


def _shared_path_topic(members: list[SanitizedTab]) -> str:
    slugs = [_path_topic(m) for m in members]
    slugs = [s for s in slugs if s]
    if not slugs:
        return ""
    folded = {s.lower() for s in slugs}
    if len(folded) == 1:
        return slugs[0]
    return ""


def _looks_like_lookup(members: list[SanitizedTab]) -> bool:
    blob = " ".join(_url_text(t) for t in members).lower()
    return any(
        word in blob
        for word in (
            "define",
            "definition",
            "meaning",
            "dictionary",
            "thesaurus",
            "wiki",
            "lookup",
            "what does",
        )
    )


def _is_generic_work_label(label: str) -> bool:
    return bool(re.match(r"^(finish|do|complete)\b.+\bwork$", _norm_label(label)))


def _goal_label(members: list[SanitizedTab]) -> str:
    """A todo the user could mark done — never the page title or site name.

    When the heuristic falls all the way back to a generic label, ask
    Gemma (a second Google model, if configured) for a one-liner. Gemma
    is bounded: it never sees URLs, extracts, or the user's notes.
    """
    raw = (
        _shared_path_topic(members)
        or _shared_name(members)
        or (_path_topic(members[0]) if members else "")
        or (_topic_from_one(members[0]) if members else "")
    )
    topic = _display_topic(raw) if raw else ""
    if all(t.host_class is HostClass.NEWS for t in members):
        return "Reading today's news"
    if any(t.host_class is HostClass.LISTING for t in members):
        return f"Compare {topic} options" if topic else _gemma_or("Compare these options", members)
    if _looks_like_lookup(members) or any(t.host_class is HostClass.SEARCH for t in members):
        return f"Look up {topic}" if topic else _gemma_or("Look this up", members)
    if topic:
        intention = _guess_intention(members)
        if intention is Intention.WAITING:
            return f"Check {topic}"
        if intention is Intention.COMPARING:
            return f"Compare {topic} options"
        return f"Read {topic}"
    fallback = _short(members[0].title, members[0].host) if members else ""
    if fallback and not _label_has_noise(fallback):
        return fallback
    return _gemma_or("Unfinished task", members)


def _gemma_or(fallback: str, members: list[SanitizedTab]) -> str:
    from stillopen_core.gateway.gemma import is_available, suggest_task_label

    if not is_available() or not members:
        return fallback
    return suggest_task_label(
        hosts=[m.host for m in members],
        titles=[m.title for m in members],
        fallback=fallback,
    )


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


def _is_vague_label(label: str) -> bool:
    toks = set(re.findall(r"[a-z]+", label.lower()))
    if toks & _VAGUE_LABEL_WORDS:
        return True
    content = toks - {
        "the",
        "this",
        "that",
        "some",
        "a",
        "an",
        "do",
        "finish",
        "my",
        "work",
        "task",
        "job",
        "on",
        "for",
        "to",
        "and",
    }
    return len(content) < 1


def _task_label(label: str, members: list[SanitizedTab]) -> str:
    cleaned = label.strip()
    if (
        cleaned
        and not looks_like_injection(cleaned)
        and not _copies_tab_title(cleaned, members)
        and not _label_has_noise(cleaned)
        and not _is_vague_label(cleaned)
        and not _is_generic_work_label(cleaned)
    ):
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
    lines = []
    for t in tabs[:80]:
        path = urlsplit(t.url).path[:80]
        title = _data(t.title or t.host)
        lines.append(f"tab_id={t.tab_id} host={t.host} path={path!r} title={title}")
    return (
        f"{TITLE_IS_DATA}\n"
        "Group these open browser tabs into unfinished TASKS.\n"
        "A task is something the person meant to finish, written like a todo.\n"
        "The label is the job, never the tab title, never the site name.\n"
        "You know what common sites are; use the URL path and title. "
        "Do not invent vibe labels like 'sophisticated work'.\n"
        "\n"
        "WRONG labels: 'Ephemeral', 'BBC News', 'Finish this ephemeral work', "
        "'sophisticated work'.\n"
        "RIGHT labels: 'Look up ephemeral', 'Reading today's news', "
        "'Compare MacBook Air prices'. Lookups say Look up / Definition, "
        "not Finish this work.\n"
        "\n"
        "Grouping:\n"
        "- Same unfinished job → one task, even on different sites.\n"
        "- Same category or language is not a job. Split those.\n"
        "- Inflected forms of the same word are one job "
        "(ephemeral / ephemerality).\n"
        "- A related search belongs with the job it started.\n"
        "- Different jobs stay split even on similar sites "
        "(rentals vs laptop shopping).\n"
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


def _data(text: str) -> str:
    return repr((text or "")[:80])


def _ask_gemini(prompt: str) -> dict | None:
    return generate_json(agent_name="cluster", prompt=prompt, timeout=8.0)


__all__ = ["infer_tasks"]
