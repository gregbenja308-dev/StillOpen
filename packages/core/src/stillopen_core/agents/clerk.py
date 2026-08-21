"""Clerk: draft Google artifacts. No execute tools."""

from __future__ import annotations

from stillopen_core.agents.parse import parse_output
from stillopen_core.errors import InvalidAgentOutput
from stillopen_core.schemas.agent import ClerkOutput
from stillopen_core.schemas.artifact import ArtifactDraft, ArtifactKind
from stillopen_core.schemas.plan import Plan, Verb
from stillopen_core.schemas.tab import SanitizedTab


def draft_artifacts(
    plan: Plan, tabs: list[SanitizedTab], *, raw_json: str | None = None
) -> ClerkOutput:
    """Heuristic drafts, or parse Gemini JSON when provided."""
    if raw_json is not None:
        out = parse_output("clerk", raw_json, ClerkOutput)
        _require_citations(out)
        return rewrite_copied_titles(out, tabs, plan)
    drafts: list[ArtifactDraft] = []
    by_id = {t.tab_id: t for t in tabs}
    for card in plan.cards:
        if card.verb is Verb.DECIDE:
            urls = [by_id[i].url for i in card.tab_ids if i in by_id]
            drafts.append(
                ArtifactDraft(
                    kind=ArtifactKind.DOC,
                    title=f"Decide: {card.label}",
                    body=_table(tabs, card.tab_ids),
                    source_urls=urls,
                    card_id=card.card_id,
                )
            )
        elif card.verb is Verb.FILE:
            urls = [by_id[i].url for i in card.tab_ids if i in by_id]
            drafts.append(
                ArtifactDraft(
                    kind=ArtifactKind.DOC,
                    title=f"Filed: {card.label}",
                    body="\n".join(
                        f"- {by_id[i].title}: {by_id[i].url}"
                        for i in card.tab_ids
                        if i in by_id
                    ),
                    source_urls=urls,
                    card_id=card.card_id,
                )
            )
        elif card.verb is Verb.WATCH:
            urls = [by_id[i].url for i in card.tab_ids if i in by_id]
            drafts.append(
                ArtifactDraft(
                    kind=ArtifactKind.EVENT,
                    title=f"Watch: {card.label}",
                    body="Check tracking page.",
                    source_urls=urls,
                    card_id=card.card_id,
                )
            )
    out = ClerkOutput(drafts=drafts)
    _require_citations(out)
    return rewrite_copied_titles(out, tabs, plan)


def rewrite_copied_titles(
    out: ClerkOutput, tabs: list[SanitizedTab], plan: Plan
) -> ClerkOutput:
    """Doc/event titles must not be copied from a tab title (untrusted)."""
    copied = {_norm_title(t.title) for t in tabs if t.title}
    labels = {c.card_id: c.label for c in plan.cards}
    for draft in out.drafts:
        if _norm_title(draft.title) not in copied:
            continue
        label = labels.get(draft.card_id or "", plan.command or "Filed tabs")
        prefix = "Watch" if draft.kind is ArtifactKind.EVENT else "Filed"
        draft.title = f"{prefix}: {label}"[:80]
    return out


def _norm_title(text: str) -> str:
    return " ".join(text.lower().split())


def _require_citations(out: ClerkOutput) -> None:
    for draft in out.drafts:
        if not draft.source_urls:
            raise InvalidAgentOutput("clerk", f"draft {draft.title!r} missing source_urls")


def _table(tabs: list[SanitizedTab], tab_ids: list[int]) -> str:
    by_id = {t.tab_id: t for t in tabs}
    lines = ["| Title | URL |", "|---|---|"]
    for tab_id in tab_ids:
        tab = by_id.get(tab_id)
        if tab is None:
            continue
        lines.append(f"| {tab.title} | {tab.url} |")
    return "\n".join(lines)


__all__ = ["draft_artifacts", "rewrite_copied_titles"]
