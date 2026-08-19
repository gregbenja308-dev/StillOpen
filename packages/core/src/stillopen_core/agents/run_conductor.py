"""Run conductor: ADK Clerk → Runner → Verifier.

Retries Clerk once on InvalidAgentOutput. Never closes tabs if File failed.
Degrades the plan instead of fabricating artifacts.
"""

from __future__ import annotations

from dataclasses import dataclass

from stillopen_core.agents.adk_clerk import draft_or_degrade
from stillopen_core.agents.runner import execute
from stillopen_core.agents.verifier import safe_apply, verify
from stillopen_core.errors import InvalidAgentOutput
from stillopen_core.google.factory import get_google
from stillopen_core.google.workspace import GoogleWorkspace
from stillopen_core.observability.logger import get_logger
from stillopen_core.schemas.agent import ClerkOutput, TabApply, VerifyReport
from stillopen_core.schemas.artifact import ArtifactRecord
from stillopen_core.schemas.plan import Plan, PlanStatus
from stillopen_core.schemas.tab import SanitizedTab
from stillopen_core.watch.enroll import enroll_from_plan

_logger = get_logger(__name__)


@dataclass(slots=True)
class RunResult:
    plan: Plan
    drafts: ClerkOutput | None
    records: list[ArtifactRecord]
    apply: TabApply
    report: VerifyReport
    clerk: str = "heuristic"


def run_plan(
    plan: Plan,
    tabs: list[SanitizedTab],
    *,
    google: GoogleWorkspace | None = None,
    clerk_raw: str | None = None,
    clerk_retry_raw: str | None = None,
) -> RunResult:
    plan.status = PlanStatus.RUNNING
    google = google or get_google(plan.user_id)
    drafts: ClerkOutput | None = None
    clerk_name = "heuristic"
    try:
        drafts = draft_or_degrade(plan, tabs, raw_json=clerk_raw, allow_adk=clerk_raw is None)
        clerk_name = "adk" if clerk_raw is None and drafts is not None else "heuristic"
        if clerk_raw is not None:
            clerk_name = "injected"
    except InvalidAgentOutput:
        _logger.info("conductor.clerk_retry", plan_id=plan.plan_id)
        try:
            drafts = draft_or_degrade(
                plan, tabs, raw_json=clerk_retry_raw, allow_adk=False
            )
            clerk_name = "heuristic"
        except InvalidAgentOutput as exc:
            plan.status = PlanStatus.DEGRADED
            empty = TabApply()
            report = VerifyReport(
                artifacts_ok=False,
                apply_ok=False,
                missing=["clerk"],
                notes=str(exc),
            )
            return RunResult(plan=plan, drafts=None, records=[], apply=empty, report=report)

    try:
        records, apply = execute(plan, drafts, tabs, google)
    except Exception as exc:  # noqa: BLE001 — compensate, don't close
        plan.status = PlanStatus.DEGRADED
        empty = TabApply()
        report = VerifyReport(
            artifacts_ok=False,
            apply_ok=False,
            missing=["runner"],
            notes=str(exc),
        )
        return RunResult(
            plan=plan, drafts=drafts, records=[], apply=empty, report=report, clerk=clerk_name
        )

    report = verify(records, apply, google, plan)
    apply = safe_apply(apply, report)
    plan.status = PlanStatus.VERIFIED if report.artifacts_ok else PlanStatus.DEGRADED
    if report.artifacts_ok:
        enroll_from_plan(plan, tabs)
    _logger.info(
        "conductor.run",
        plan_id=plan.plan_id,
        status=plan.status.value,
        close_count=len(apply.close_tab_ids),
        clerk=clerk_name,
    )
    return RunResult(
        plan=plan, drafts=drafts, records=records, apply=apply, report=report, clerk=clerk_name
    )


__all__ = ["RunResult", "run_plan"]
