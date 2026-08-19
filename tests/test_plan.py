from stillopen_core.agents.conductor import propose_plan
from stillopen_core.agents.framer import match_named_job
from stillopen_core.schemas.plan import Verb
from stillopen_core.schemas.tab import TabSnapshot
from stillopen_core.surveyor.sanitize import sanitize_tabs


def test_named_job_matches_house_tabs(seeded_tabs: list[TabSnapshot]) -> None:
    sanitized = sanitize_tabs(seeded_tabs)
    matched = match_named_job("close the tabs about buying a house austin", sanitized)
    titles_hosts = {t.tab_id: (t.host, t.title) for t in sanitized if t.tab_id in matched}
    assert 11 in titles_hosts
    assert 12 in titles_hosts
    assert 16 not in matched  # chase


def test_propose_plan_has_decide_and_blocks_bank(seeded_tabs: list[TabSnapshot]) -> None:
    plan = propose_plan(
        user_id="local-dev",
        tabs=seeded_tabs,
        command="close the tabs about buying a house austin",
    )
    verbs = {c.verb for c in plan.cards}
    assert Verb.DECIDE in verbs
    assert 16 in plan.blocked_tab_ids
    for card in plan.cards:
        assert 16 not in card.tab_ids or card.verb != Verb.KILL
