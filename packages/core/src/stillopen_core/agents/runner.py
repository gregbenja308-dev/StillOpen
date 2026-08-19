"""Runner: execute locked drafts. No LLM. Close is last and only if artifacts landed."""

from __future__ import annotations

from stillopen_core.google.workspace import FakeGoogle, GoogleWorkspace
from stillopen_core.schemas.agent import ClerkOutput, TabApply
from stillopen_core.schemas.artifact import ArtifactRecord
from stillopen_core.schemas.plan import Plan, Verb
from stillopen_core.schemas.tab import CloseHint, SanitizedTab


def execute(
    plan: Plan,
    drafts: ClerkOutput,
    tabs: list[SanitizedTab],
    google: GoogleWorkspace,
) -> tuple[list[ArtifactRecord], TabApply]:
    records: list[ArtifactRecord] = []
    for draft in drafts.drafts:
        record = google.create(draft.kind, draft.title, draft.body)
        record.draft_id = draft.draft_id
        if not record.title:
            record.title = draft.title
        records.append(record)

    close_ids: list[int] = []
    keep_ids: list[int] = []
    by_id = {t.tab_id: t for t in tabs}
    for card in plan.cards:
        for action in card.actions:
            tab = by_id.get(action.tab_id)
            if tab is None:
                continue
            if (
                action.checked
                and action.close_hint is not CloseHint.NEVER
                and card.verb in {Verb.FILE, Verb.DECIDE, Verb.KILL}
            ):
                close_ids.append(action.tab_id)
            else:
                keep_ids.append(action.tab_id)
    return records, TabApply(close_tab_ids=close_ids, keep_tab_ids=keep_ids)


__all__ = ["FakeGoogle", "execute"]
