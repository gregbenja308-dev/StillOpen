"""Verifier fidelity (P3+): a filing that lacks citations or drops the user's
notes is treated the same as a missing filing — tabs stay open.

These tests hand-craft a ``ClerkOutput`` and drive Runner + Verifier directly
so the "hallucinated Clerk" case is deterministic. The full ADK graph path is
still exercised in ``test_run_and_watch.py``.
"""

from __future__ import annotations

from stillopen_core.agents.conductor import propose_plan
from stillopen_core.agents.runner import execute
from stillopen_core.agents.verifier import safe_apply, verify
from stillopen_core.google.workspace import FakeGoogle
from stillopen_core.schemas.agent import ClerkOutput
from stillopen_core.schemas.artifact import ArtifactDraft, ArtifactKind
from stillopen_core.schemas.tab import TabSnapshot
from stillopen_core.surveyor.sanitize import sanitize_tabs


def _house_tabs(seeded: list[TabSnapshot]) -> list[TabSnapshot]:
    return [t for t in seeded if "zillow" in t.url or "redfin" in t.url]


def _house_plan(seeded: list[TabSnapshot], *, notes: str = ""):
    return propose_plan(
        user_id="local-dev",
        tabs=_house_tabs(seeded),
        command="close the tabs about buying a house austin",
        force_file=True,
        user_notes=notes,
    )


def _run(plan, sanitized, drafts: ClerkOutput, google: FakeGoogle):
    """Execute the Runner + Verifier the same way ``run_plan`` would."""

    records, apply = execute(plan, drafts, sanitized, google)
    return records, apply, verify(records, apply, google, plan, tabs=sanitized)


def test_verifier_vetoes_when_body_lacks_any_source_host(
    seeded_tabs: list[TabSnapshot],
) -> None:
    """Clerk drafts a body that doesn't cite any of the plan's tab hosts.

    Even though the artifact was created (google.exists() would say yes) the
    Verifier must refuse to green-light the close.
    """

    plan = _house_plan(seeded_tabs)
    sanitized = sanitize_tabs(_house_tabs(seeded_tabs))
    drafts = ClerkOutput(
        drafts=[
            ArtifactDraft(
                kind=ArtifactKind.DOC,
                title="Filed: House hunt",
                body="unrelated content with no citations",
                source_urls=["urn:x-plan"],
            )
        ]
    )
    _records, apply, report = _run(plan, sanitized, drafts, FakeGoogle())
    assert report.artifacts_ok is False
    assert any(m.startswith("citation:") for m in report.missing)
    assert apply.close_tab_ids  # Runner staged closes, but…
    assert safe_apply(apply, report).close_tab_ids == []  # …Verifier vetoes.


def test_verifier_vetoes_when_body_drops_user_notes(seeded_tabs: list[TabSnapshot]) -> None:
    """User notes must appear verbatim in at least one filed body.

    Simulates a Clerk that cited sources correctly but silently dropped the
    user's own words. The safety net catches that even though the LLM produced
    a plausible-looking Doc.
    """

    plan = _house_plan(seeded_tabs, notes="3 bed, under $3200, walkable to trailhead.")
    sanitized = sanitize_tabs(_house_tabs(seeded_tabs))
    drafts = ClerkOutput(
        drafts=[
            ArtifactDraft(
                kind=ArtifactKind.DOC,
                title="Filed: House hunt",
                body="zillow.com listing A\nredfin.com listing B",
                source_urls=["urn:x-plan"],
            )
        ]
    )
    _records, _apply, report = _run(plan, sanitized, drafts, FakeGoogle())
    assert report.artifacts_ok is False
    assert "notes" in report.missing


def test_verifier_passes_when_body_cites_hosts_and_keeps_notes(
    seeded_tabs: list[TabSnapshot],
) -> None:
    """A body that cites at least one host and contains the notes verbatim clears fidelity."""

    plan = _house_plan(seeded_tabs, notes="3 bed, under $3200, walkable to trailhead.")
    sanitized = sanitize_tabs(_house_tabs(seeded_tabs))
    drafts = ClerkOutput(
        drafts=[
            ArtifactDraft(
                kind=ArtifactKind.DOC,
                title="Filed: House hunt",
                body=(
                    "Zillow listing at zillow.com — 3 bed downtown.\n"
                    "Redfin comp at redfin.com.\n\n"
                    "## Notes from the user\n"
                    "3 bed, under $3200, walkable to trailhead."
                ),
                source_urls=["urn:x-plan"],
            )
        ]
    )
    _records, _apply, report = _run(plan, sanitized, drafts, FakeGoogle())
    assert report.artifacts_ok is True
    assert not report.missing


def test_read_from_fakegoogle_returns_body() -> None:
    """FakeGoogle now stores the body so Verifier fidelity has something to check."""

    google = FakeGoogle()
    record = google.create(ArtifactKind.DOC, "Filed: House hunt", body="zillow.com listing")
    assert google.exists(ArtifactKind.DOC, record.google_id)
    assert google.read(ArtifactKind.DOC, record.google_id) == "zillow.com listing"
    assert google.read(ArtifactKind.MAIL, "missing") is None
