from stillopen_core.agents.conductor import propose_plan
from stillopen_core.agents.run_conductor import run_plan
from stillopen_core.schemas.plan import Verb
from stillopen_core.schemas.tab import TabSnapshot
from stillopen_core.surveyor.sanitize import sanitize_tabs


def test_force_file_rewrites_cards_to_file_or_decide(seeded_tabs: list[TabSnapshot]) -> None:
    house = [t for t in seeded_tabs if t.tab_id in {11, 12, 13}]
    plan = propose_plan(
        user_id="local-dev",
        tabs=house,
        command="house shopping",
        force_file=True,
    )
    assert plan.cards
    assert all(c.verb in {Verb.FILE, Verb.DECIDE} for c in plan.cards)


def test_file_then_close_refuses_when_doc_missing(seeded_tabs: list[TabSnapshot]) -> None:
    from stillopen_core.agents.runner import FakeGoogle
    from stillopen_core.schemas.artifact import ArtifactKind

    house = [t for t in seeded_tabs if t.tab_id in {11, 12, 13}]
    plan = propose_plan(
        user_id="local-dev",
        tabs=house,
        command="house shopping",
        force_file=True,
    )
    google = FakeGoogle()
    google.fail_kinds.add(ArtifactKind.DOC)
    result = run_plan(plan, sanitize_tabs(house), google=google)
    assert result.report.artifacts_ok is False
    assert result.apply.close_tab_ids == []


def test_file_then_close_returns_artifact_url(seeded_tabs: list[TabSnapshot]) -> None:
    house = [t for t in seeded_tabs if t.tab_id in {11, 12, 13}]
    plan = propose_plan(
        user_id="local-dev",
        tabs=house,
        command="house shopping",
        force_file=True,
    )
    result = run_plan(plan, sanitize_tabs(house))
    assert result.report.artifacts_ok
    assert result.records
    # FilingStore returns a URL under the API's public base + /v1/filings/.
    assert "/v1/filings/" in result.records[0].url
    assert result.apply.close_tab_ids


def test_clerk_rewrites_a_copied_tab_title(seeded_tabs: list[TabSnapshot]) -> None:
    from stillopen_core.agents.clerk import rewrite_copied_titles
    from stillopen_core.schemas.agent import ClerkOutput
    from stillopen_core.schemas.artifact import ArtifactDraft, ArtifactKind

    house = [t for t in seeded_tabs if t.tab_id in {11, 12}]
    plan = propose_plan(
        user_id="local-dev",
        tabs=house,
        command="house shopping",
        force_file=True,
    )
    tab = house[0]
    out = ClerkOutput(
        drafts=[
            ArtifactDraft(
                kind=ArtifactKind.DOC,
                title=tab.title,
                body="notes",
                source_urls=[tab.url],
                card_id=plan.cards[0].card_id,
            )
        ]
    )
    scrubbed = rewrite_copied_titles(out, sanitize_tabs(house), plan)
    assert scrubbed.drafts[0].title != tab.title
    assert plan.cards[0].label in scrubbed.drafts[0].title
