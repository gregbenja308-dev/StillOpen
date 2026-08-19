from stillopen_core.memory.categorize import heuristic_groups
from stillopen_core.memory.chat import apply_chat, parse_preference
from stillopen_core.memory.fakes import get_bank
from stillopen_core.memory.habits import mutate
from stillopen_core.memory.match import match_tabs
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
    hits = match_tabs(seeded_tabs, intent, now_ms=1_800_000_000_000)
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
