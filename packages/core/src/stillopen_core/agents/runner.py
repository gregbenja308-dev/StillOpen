"""Runner: execute locked drafts. No LLM. Close is last and only if artifacts landed."""

from __future__ import annotations

from stillopen_core.gateway.router import AgentGateway, get_gateway
from stillopen_core.google.workspace import FakeGoogle, GoogleWorkspace
from stillopen_core.schemas.agent import ClerkOutput, TabApply
from stillopen_core.schemas.artifact import ArtifactKind, ArtifactRecord
from stillopen_core.schemas.plan import Plan, Verb
from stillopen_core.schemas.tab import CloseHint, SanitizedTab

_CREATE_TOOL = {
    ArtifactKind.DOC: "create_doc",
    ArtifactKind.EVENT: "create_event",
    ArtifactKind.TASK: "create_task",
    ArtifactKind.MAIL: "send_mail",
}


def execute(
    plan: Plan,
    drafts: ClerkOutput,
    tabs: list[SanitizedTab],
    google: GoogleWorkspace,
    *,
    gateway: AgentGateway | None = None,
) -> tuple[list[ArtifactRecord], TabApply]:
    gw = gateway or get_gateway()
    records: list[ArtifactRecord] = []
    for draft in drafts.drafts:
        tool = _CREATE_TOOL.get(draft.kind)
        if tool is None:
            continue
        record = gw.invoke_sync(
            agent_name="runner",
            tool_name=tool,
            fn=google.create,
            kind=draft.kind,
            title=draft.title,
            body=draft.body,
        )
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
    apply = TabApply(close_tab_ids=close_ids, keep_tab_ids=keep_ids)
    gw.invoke_sync(agent_name="runner", tool_name="emit_tab_apply", fn=lambda: apply)
    return records, apply


__all__ = ["FakeGoogle", "execute"]
