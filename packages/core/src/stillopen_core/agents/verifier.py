"""Verifier: read-only proof. If artifacts are missing, close is forbidden."""

from __future__ import annotations

from stillopen_core.google.workspace import GoogleWorkspace
from stillopen_core.schemas.agent import TabApply, VerifyReport
from stillopen_core.schemas.artifact import ArtifactKind, ArtifactRecord
from stillopen_core.schemas.plan import Plan, Verb


def verify(
    records: list[ArtifactRecord],
    apply: TabApply,
    google: GoogleWorkspace,
    plan: Plan | None = None,
) -> VerifyReport:
    missing: list[str] = []
    if plan is not None:
        needs_doc = any(c.verb in {Verb.FILE, Verb.DECIDE} for c in plan.cards)
        if needs_doc and not any(r.kind is ArtifactKind.DOC for r in records):
            missing.append("doc")
    for record in records:
        if not google.exists(record.kind, record.google_id):
            missing.append(record.google_id)
    artifacts_ok = not missing
    apply_ok = artifacts_ok
    close_ids = apply.close_tab_ids if artifacts_ok else []
    notes = "ok" if artifacts_ok else "artifacts missing; refusing close"
    return VerifyReport(
        artifacts_ok=artifacts_ok,
        apply_ok=apply_ok and bool(close_ids or apply.keep_tab_ids),
        missing=missing,
        notes=notes,
    )


def safe_apply(apply: TabApply, report: VerifyReport) -> TabApply:
    if report.artifacts_ok:
        return apply
    return TabApply(close_tab_ids=[], keep_tab_ids=apply.keep_tab_ids + apply.close_tab_ids)


__all__ = ["safe_apply", "verify"]
