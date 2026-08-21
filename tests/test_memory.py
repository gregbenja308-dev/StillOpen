from stillopen_core.memory.categorize import heuristic_groups
from stillopen_core.memory.chat import apply_chat, parse_preference
from stillopen_core.memory.fakes import get_bank
from stillopen_core.memory.habits import mutate
from stillopen_core.memory.match import match_tabs
from stillopen_core.memory.tasks import infer_tasks
from stillopen_core.schemas.habit import ClosePolicy, FeedbackKind, HabitEvent, HabitProfile
from stillopen_core.schemas.tab import TabSnapshot


def test_chat_answers_what_stale_means() -> None:
    intent = parse_preference("what does stale mean?")
    assert intent.wants_close is False
    assert "7 days" in intent.reply
    assert "does not depend" in intent.reply.lower()


def test_chat_explains_the_product() -> None:
    intent = parse_preference("what does this app do")
    assert intent.wants_close is False
    assert "task" in intent.reply.lower()
    intent = parse_preference("I want to delete tabs that I haven't used in a week")
    assert intent.stale_cutoff_days == 7
    profile = HabitProfile(user_id="local-dev")
    apply_chat(profile, "I want to delete tabs that I haven't used in a week", intent)
    assert profile.stale_cutoff_days == 7
    assert profile.mutations
    assert profile.mutations[0].after["stale_cutoff_days"] == 7
    assert profile.chats[0].role == "user"


def test_chat_never_close_host() -> None:
    intent = parse_preference("never close github.com")
    assert "github.com" in intent.keep_hosts
    profile = HabitProfile(user_id="u")
    apply_chat(profile, "never close github.com", intent)
    rule = profile.rule_for("github.com")
    assert rule is not None
    assert rule.close_policy is ClosePolicy.ALWAYS_KEEP


def test_user_close_infers_after_two() -> None:
    profile = HabitProfile(user_id="u")
    mutate(
        profile, HabitEvent(kind=FeedbackKind.USER_CLOSE, host_suffix="reddit.com", source="chrome")
    )
    assert profile.rule_for("reddit.com") is None
    mutate(
        profile, HabitEvent(kind=FeedbackKind.USER_CLOSE, host_suffix="reddit.com", source="chrome")
    )
    rule = profile.rule_for("reddit.com")
    assert rule is not None
    assert rule.close_policy is ClosePolicy.FILE_THEN_CLOSE
    assert profile.stat_for("reddit.com").user_closed == 2


def test_stillopen_close_infers_immediately() -> None:
    profile = HabitProfile(user_id="u")
    mutate(
        profile,
        HabitEvent(kind=FeedbackKind.STILLOPEN_CLOSE, host_suffix="medium.com", source="stale"),
    )
    assert profile.rule_for("medium.com").close_policy is ClosePolicy.FILE_THEN_CLOSE


def test_uncheck_beats_inferred_close() -> None:
    profile = HabitProfile(user_id="u")
    mutate(profile, HabitEvent(kind=FeedbackKind.STILLOPEN_CLOSE, host_suffix="zillow.com"))
    mutate(profile, HabitEvent(kind=FeedbackKind.UNCHECK, host_suffix="zillow.com", source="plan"))
    assert profile.rule_for("zillow.com").close_policy is ClosePolicy.ALWAYS_KEEP
    assert profile.stat_for("zillow.com").kept == 1


def test_delete_news_tabs_matches_now_not_stale_only(seeded_tabs: list[TabSnapshot]) -> None:
    intent = parse_preference("Delete any news tabs")
    assert intent.wants_close is True
    assert "news" in intent.match_classes
    assert "nytimes.com" not in intent.close_hosts
    assert "stale" not in intent.reply.lower()
    hits = match_tabs(
        seeded_tabs, intent, query="Delete any news tabs", now_ms=1_800_000_000_000
    )
    hosts = {row.host for row in hits}
    assert "nytimes.com" in hosts
    assert "zillow.com" not in hosts
    assert "chase.com" not in hosts
    assert "stale" not in intent.reply.lower()


def test_memory_bank_persists_profile_fields() -> None:
    bank = get_bank()
    profile = bank.habit_for("local-dev")
    intent = parse_preference("ok to close reddit.com")
    apply_chat(profile, "ok to close reddit.com", intent)
    bank.put_habit(profile)
    again = get_bank().habit_for("local-dev")
    assert again.rule_for("reddit.com") is not None
    assert again.statements


def test_heuristic_groups_seeded_window(seeded_tabs: list[TabSnapshot]) -> None:
    groups = heuristic_groups(seeded_tabs)
    by_title = {g.title: set(g.tab_ids) for g in groups}
    assert 15 in by_title["News to read"]
    assert 11 in by_title["Housing & shopping"]
    assert 14 in by_title["Search leftovers"]
    assert 16 in by_title["Banking"]
    assigned = [i for g in groups for i in g.tab_ids]
    assert len(assigned) == len(set(assigned)) == len(seeded_tabs)


def _snap(tab_id: int, url: str, title: str) -> TabSnapshot:
    return TabSnapshot(
        tab_id=tab_id,
        window_id=1,
        index=tab_id,
        url=url,
        title=title,
        pinned=False,
        audible=False,
        discarded=False,
        active=False,
        group_id=-1,
        last_accessed_ms=1,
        extract=None,
    )


def test_house_prompt_picks_related_tasks_not_github_or_lookup() -> None:
    tabs = [
        _snap(1, "https://www.zillow.com/austin-tx/", "Zillow Austin"),
        _snap(2, "https://www.redfin.com/city/30818/TX/Austin", "Redfin Austin"),
        _snap(3, "https://www.apartments.com/austin-tx/", "Apartments.com Austin"),
        _snap(4, "https://www.nytimes.com/section/realestate", "NYT real estate"),
        _snap(5, "https://www.merriam-webster.com/dictionary/ephemeral", "Dictionary: ephemeral"),
        _snap(6, "https://en.wikipedia.org/wiki/Ephemeral", "Wikipedia: Ephemeral"),
        _snap(7, "https://github.com/google/adk-python", "GitHub: google/adk-python"),
        _snap(8, "https://www.amazon.com/s?k=macbook+air", "Amazon: MacBook Air"),
        _snap(9, "https://www.bbc.com/news", "BBC News"),
        _snap(10, "https://www.chase.com/", "Chase"),
    ]
    tasks = infer_tasks(tabs)
    prompt = "delete any house/real-estate tabs"
    intent = parse_preference(prompt)
    assert intent.wants_close is True
    hits = match_tabs(tabs, intent, tasks=tasks, query=prompt)
    ids = {row.tab_id for row in hits}
    assert {1, 2, 3}.issubset(ids)
    assert 4 in ids
    assert 5 not in ids
    assert 6 not in ids
    assert 7 not in ids
    assert 8 not in ids
    assert 9 not in ids
    assert 10 not in ids
    owners = {tid: task.task_id for task in tasks for tid in task.tab_ids}
    assert len({owners[i] for i in ids}) >= 1


def test_close_without_a_topic_does_not_mean_every_tab(seeded_tabs: list[TabSnapshot]) -> None:
    intent = parse_preference("delete any tabs")
    hits = match_tabs(seeded_tabs, intent, tasks=infer_tasks(seeded_tabs), query="delete any tabs")
    assert hits == []


def test_news_prompt_uses_news_tasks_not_housing(seeded_tabs: list[TabSnapshot]) -> None:
    tasks = infer_tasks(seeded_tabs)
    prompt = "Delete any news tabs"
    intent = parse_preference(prompt)
    hits = match_tabs(seeded_tabs, intent, tasks=tasks, query=prompt, now_ms=1_800_000_000_000)
    hosts = {row.host for row in hits}
    assert "nytimes.com" in hosts
    assert "zillow.com" not in hosts
    assert "github.com" not in hosts
