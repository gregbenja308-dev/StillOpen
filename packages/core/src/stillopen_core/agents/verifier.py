"""Verifier: read-only proof.

The Verifier has two responsibilities and both must succeed before the
extension is allowed to close tabs:

1. **Existence.** Every artifact the Runner claims to have filed must be
   readable from the Google workspace. A missing artifact fails the plan
   with ``artifacts_ok=False`` — same posture we've had since day one.
2. **Fidelity.** For every ``FILE`` or ``DECIDE`` card the plan claimed,
   at least one filed artifact must *cite* one of that card's tabs (its
   host has to appear in the body) and — if the user supplied notes —
   those notes must be present verbatim in one of the bodies. This
   closes the honest gap that a hallucinating Clerk could otherwise pass
   just by producing *some* filing. See ``SECURITY.md`` for the trust
   model this backs up.

Fidelity check is best-effort: if the workspace has no ``read()`` (older
callers, degraded FakeGoogle) it's skipped so existing tests keep
passing. In production the FilingStore always implements ``read()``.
"""

from __future__ import annotations

from stillopen_core.gateway.router import AgentGateway, get_gateway
from stillopen_core.google.workspace import GoogleWorkspace
from stillopen_core.schemas.agent import TabApply, VerifyReport
from stillopen_core.schemas.artifact import ArtifactKind, ArtifactRecord
from stillopen_core.schemas.plan import Plan, Verb
from stillopen_core.schemas.tab import SanitizedTab

_GET_TOOL = {
    ArtifactKind.DOC: "get_doc",
    ArtifactKind.EVENT: "get_event",
    ArtifactKind.TASK: "get_event",
}


def verify(
    records: list[ArtifactRecord],
    apply: TabApply,
    google: GoogleWorkspace,
    plan: Plan | None = None,
    *,
    gateway: AgentGateway | None = None,
    tabs: list[SanitizedTab] | None = None,
) -> VerifyReport:
    gw = gateway or get_gateway()
    missing: list[str] = []
    if plan is not None:
        needs_doc = any(c.verb in {Verb.FILE, Verb.DECIDE} for c in plan.cards)
        if needs_doc and not any(r.kind is ArtifactKind.DOC for r in records):
            missing.append("doc")
    for record in records:
        tool = _GET_TOOL.get(record.kind)
        if tool is None:
            missing.append(record.google_id)
            continue
        exists = gw.invoke_sync(
            agent_name="verifier",
            tool_name=tool,
            fn=google.exists,
            kind=record.kind,
            google_id=record.google_id,
        )
        if not exists:
            missing.append(record.google_id)

    if plan is not None and not missing:
        missing.extend(_fidelity_gaps(plan=plan, records=records, google=google, tabs=tabs or []))

    artifacts_ok = not missing
    apply_ok = artifacts_ok
    close_ids = apply.close_tab_ids if artifacts_ok else []
    if artifacts_ok:
        notes = "ok"
    elif any(m.startswith("citation:") for m in missing) or "notes" in missing:
        notes = "fidelity failed; refusing close"
    else:
        notes = "artifacts missing; refusing close"
    return VerifyReport(
        artifacts_ok=artifacts_ok,
        apply_ok=apply_ok and bool(close_ids or apply.keep_tab_ids),
        missing=missing,
        notes=notes,
    )


def _fidelity_gaps(
    *,
    plan: Plan,
    records: list[ArtifactRecord],
    google: GoogleWorkspace,
    tabs: list[SanitizedTab],
) -> list[str]:
    """Return a list of fidelity gaps (empty = clean).

    A FILE/DECIDE card is "fresh" if at least one filed body cites (contains
    the lowercased host of) one of that card's tabs. The user's notes — if
    any — must appear verbatim in at least one body. If the workspace can't
    ``read()``, we skip fidelity rather than false-positive.
    """

    reader = getattr(google, "read", None)
    if reader is None:
        return []

    bodies: list[str] = []
    for record in records:
        if record.kind is not ArtifactKind.DOC:
            continue
        try:
            body = reader(record.kind, record.google_id)
        except Exception:  # noqa: BLE001 — fidelity is best-effort; existence stayed hard
            body = None
        if isinstance(body, str) and body:
            bodies.append(body)

    if not bodies:
        return []

    lowered = [b.lower() for b in bodies]
    gaps: list[str] = []

    tabs_by_id = {t.tab_id: t for t in tabs}
    for card in plan.cards:
        if card.verb not in {Verb.FILE, Verb.DECIDE}:
            continue
        card_hosts = {
            tabs_by_id[t].host.removeprefix("www.").lower()
            for t in card.tab_ids
            if t in tabs_by_id and tabs_by_id[t].host
        }
        if not card_hosts:
            # Nothing to check — the card had no tab hosts we can see.
            continue
        if not any(any(host in body for host in card_hosts) for body in lowered):
            gaps.append(f"citation:{card.card_id}")

    notes = (plan.user_notes or "").strip()
    if notes:
        needle = _notes_needle(notes)
        if needle and not any(needle in body for body in bodies):
            gaps.append("notes")

    return gaps


def _notes_needle(notes: str) -> str:
    """A short, distinctive slice of the notes we expect to see verbatim.

    We look for the first meaningful line rather than the entire notes so
    line-wrapping in the artifact body doesn't false-positive. Fewer than
    a handful of characters would match anything so we skip too-short
    notes.
    """

    for line in notes.splitlines():
        stripped = line.strip()
        if len(stripped) >= 8:
            return stripped[:120]
    return ""


def safe_apply(apply: TabApply, report: VerifyReport) -> TabApply:
    if report.artifacts_ok:
        return apply
    return TabApply(close_tab_ids=[], keep_tab_ids=apply.keep_tab_ids + apply.close_tab_ids)


__all__ = ["safe_apply", "verify"]
