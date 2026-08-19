from datetime import UTC, datetime, timedelta

from stillopen_core.agents.conductor import propose_plan
from stillopen_core.agents.run_conductor import run_plan
from stillopen_core.agents.runner import FakeGoogle
from stillopen_core.memory.fakes import get_bank
from stillopen_core.memory.habits import mutate
from stillopen_core.schemas.habit import FeedbackKind, HabitEvent
from stillopen_core.schemas.plan import PlanStatus
from stillopen_core.schemas.tab import CloseHint, TabSnapshot
from stillopen_core.schemas.watch import WatchStatus
from stillopen_core.surveyor.sanitize import sanitize_tabs
from stillopen_core.watch.tick import hash_body, tick


def test_habit_uncheck_blocks_close_next_plan(seeded_tabs: list[TabSnapshot]) -> None:
    bank = get_bank()
    profile = bank.habit_for("local-dev")
    mutate(
        profile,
        HabitEvent(kind=FeedbackKind.UNCHECK, host_suffix="redfin.com", phrase="buying a house"),
    )
    bank.put_habit(profile)
    plan = propose_plan(
        user_id="local-dev",
        tabs=seeded_tabs,
        command="close the tabs about buying a house austin",
    )
    redfin_actions = [
        a
        for c in plan.cards
        for a in c.actions
        if a.tab_id == 12
    ]
    assert redfin_actions
    assert redfin_actions[0].close_hint is CloseHint.NEVER
    assert redfin_actions[0].checked is False


def test_run_creates_artifacts_and_enrolls_watches(seeded_tabs: list[TabSnapshot]) -> None:
    plan = propose_plan(
        user_id="local-dev",
        tabs=seeded_tabs,
        command="close the tabs about buying a house austin",
    )
    sanitized = sanitize_tabs(seeded_tabs)
    result = run_plan(plan, sanitized)
    assert result.plan.status is PlanStatus.VERIFIED
    assert result.records
    assert result.report.artifacts_ok
    assert get_bank().watches


def test_run_degrades_and_refuses_close_when_google_fails(
    seeded_tabs: list[TabSnapshot],
) -> None:
    plan = propose_plan(
        user_id="local-dev",
        tabs=seeded_tabs,
        command="close the tabs about buying a house austin",
    )
    google = FakeGoogle()
    from stillopen_core.schemas.artifact import ArtifactKind

    google.fail_kinds.add(ArtifactKind.DOC)
    result = run_plan(plan, sanitize_tabs(seeded_tabs), google=google)
    assert result.plan.status is PlanStatus.DEGRADED
    assert result.apply.close_tab_ids == []


def test_clerk_retry_then_succeed(seeded_tabs: list[TabSnapshot]) -> None:
    plan = propose_plan(user_id="local-dev", tabs=seeded_tabs, command="austin house")
    result = run_plan(
        plan,
        sanitize_tabs(seeded_tabs),
        clerk_raw="not-json",
        clerk_retry_raw=None,
    )
    assert result.plan.status is PlanStatus.VERIFIED
    assert result.drafts is not None


def test_watch_tick_no_show_without_human(seeded_tabs: list[TabSnapshot]) -> None:
    plan = propose_plan(
        user_id="local-dev",
        tabs=seeded_tabs,
        command="close the tabs about buying a house austin",
    )
    run_plan(plan, sanitize_tabs(seeded_tabs))
    bank = get_bank()
    assert bank.watches
    watch = next(iter(bank.watches.values()))
    watch.last_hash = hash_body("same-body")
    past = datetime.now(tz=UTC) - timedelta(days=4)
    watch.deadline_at = past
    watch.next_check_at = past

    def fetcher(_url: str) -> str:
        return "same-body"

    acted = tick(fetcher=fetcher, at=datetime.now(tz=UTC))
    assert acted
    assert acted[0].status is WatchStatus.ESCALATED
    assert acted[0].last_action == "no_show"
