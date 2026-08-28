"""``POST /v1/tasks/finish`` — the extension's "Done, close!" path.

Runs the full ADK graph on a single OpenTask: proposes a Plan, Clerk drafts,
Runner files into the FilingStore (Firestore in prod), Verifier checks, and
returns the list of tab ids the extension is *allowed* to close. If
artifacts_ok is false, no close list is returned — the extension keeps the
tabs open. See ``ARCHITECTURE.md``.
"""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from stillopen_core.agents.conductor import propose_plan
from stillopen_core.agents.run_conductor import run_plan
from stillopen_core.memory.fakes import get_bank
from stillopen_core.observability.audit import record_event
from stillopen_core.schemas.agent import TabApply, VerifyReport
from stillopen_core.schemas.artifact import ArtifactRecord
from stillopen_core.schemas.event import EventPhase, Verdict
from stillopen_core.schemas.plan import Plan, Verb
from stillopen_core.schemas.tab import CloseHint, Intention, TabSnapshot
from stillopen_core.schemas.task import TaskKind
from stillopen_core.schemas.watch import WatchKind
from stillopen_core.security.user_token import is_enforced, verify_token
from stillopen_core.surveyor.sanitize import sanitize_tabs
from stillopen_core.watch.enroll import enroll_from_task

router = APIRouter(prefix="/v1/tasks", tags=["tasks"])


_FILING_INTENTIONS = frozenset(
    {
        Intention.COMPARING,
        Intention.READ_LATER,
        Intention.WAITING,
        Intention.REFERENCE,
    }
)


class FinishTaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1, max_length=128)
    task_id: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=200)
    notes: str = Field(default="", max_length=4000)
    tabs: list[TabSnapshot] = Field(min_length=0, max_length=200)
    # ``intention`` / ``kind`` are accepted for backwards-compat with older
    # extension builds but are ignored server-side: the file decision is
    # derived from the Framer's ``infer_intention`` on the sanitized tabs
    # so a hostile caller can't force a filing by lying about intent.
    intention: Intention = Intention.UNKNOWN
    kind: TaskKind = TaskKind.EPHEMERAL
    file_to_google: bool | None = None


class FinishTaskResponse(BaseModel):
    plan: Plan
    apply: TabApply
    report: VerifyReport
    artifacts: list[ArtifactRecord] = Field(default_factory=list)
    clerk: str = "heuristic"
    audit_url: str
    filing_urls: list[str] = Field(default_factory=list)


class StillGoingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1, max_length=128)
    task_id: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=200)
    urls: list[str] = Field(min_length=1, max_length=40)


class StillGoingResponse(BaseModel):
    enrolled: int
    watch_ids: list[str]


def _require_user(bank, user_id: str, token: str | None) -> None:
    """Enforce the per-user bearer token when the feature flag is on.

    Off by default so unit tests and existing extensions keep working; flipping
    ``STILLOPEN_REQUIRE_USER_TOKEN=1`` closes the CORS-only gap.
    """

    if not is_enforced():
        return
    if not verify_token(bank, user_id, token):
        raise HTTPException(status_code=401, detail="bad user token")


def _should_file(
    *,
    plan_intentions: set[Intention],
    non_protected_tab_count: int,
    notes: str,
    file_override: bool | None,
) -> bool:
    """Decide whether the Clerk graph runs, using **server-derived** signals.

    The client can still pass ``file_to_google`` as an explicit override, but
    we ignore its self-reported ``intention``/``kind`` for this decision.
    The intentions here come from the Framer's ``infer_intention`` on the
    sanitized tabs — a hostile caller can't force filing by lying.
    """

    if file_override is not None:
        return file_override
    if not non_protected_tab_count:
        return False
    if notes.strip():
        return True
    if plan_intentions & _FILING_INTENTIONS:
        return True
    return non_protected_tab_count >= 3


def _promote_to_file(plan: Plan) -> None:
    """Turn a proposed plan into a Clerk-runnable File plan in place.

    Same rules ``propose_plan(force_file=True)`` would have used, but applied
    *after* the server-side file decision instead of relying on the caller.
    """

    for card in plan.cards:
        card.verb = Verb.DECIDE if card.intention is Intention.COMPARING else Verb.FILE
        for action in card.actions:
            if action.close_hint is not CloseHint.NEVER:
                action.checked = True


@router.post("/finish", response_model=FinishTaskResponse)
def finish_task(
    body: FinishTaskRequest,
    x_stillopen_user_token: str | None = Header(default=None),
) -> FinishTaskResponse:
    bank = get_bank()
    _require_user(bank, body.user_id, x_stillopen_user_token)

    # Frame first (without any force_file), so the file decision is made from
    # server-derived intentions rather than the client-supplied ones.
    plan = propose_plan(
        user_id=body.user_id,
        tabs=body.tabs,
        command=None,
        force_file=False,
        user_notes=body.notes,
        source_task_id=body.task_id,
    )
    plan.command = body.label
    plan_intentions = {card.intention for card in plan.cards}
    non_protected_count = sum(
        1
        for card in plan.cards
        for action in card.actions
        if action.close_hint is not CloseHint.NEVER
    )
    file_to_google = _should_file(
        plan_intentions=plan_intentions,
        non_protected_tab_count=non_protected_count,
        notes=body.notes,
        file_override=body.file_to_google,
    )
    if not file_to_google:
        # Kill-only path: no Clerk, no Runner, no Verifier — the OpenTask
        # is truly ephemeral. Still emit an audit event so the chain is
        # visible for judges even on the short path. Bank / health / auth
        # tabs stay open because the Framer already marked their
        # ``close_hint`` as ``NEVER`` regardless of what the client asked.
        close_ids: list[int] = []
        keep_ids: list[int] = []
        for card in plan.cards:
            for action in card.actions:
                if action.close_hint is CloseHint.NEVER:
                    keep_ids.append(action.tab_id)
                else:
                    close_ids.append(action.tab_id)
        apply = TabApply(close_tab_ids=close_ids, keep_tab_ids=keep_ids)
        report = VerifyReport(
            artifacts_ok=True,
            apply_ok=True,
            missing=[],
            notes="ephemeral: closed without a filing",
        )
        record_event(
            plan_id=plan.plan_id,
            user_id=body.user_id,
            agent="framer",
            phase=EventPhase.CLOSE_APPLIED,
            verdict=Verdict.OK,
            summary=f"ephemeral close={len(close_ids)} keep={len(keep_ids)}",
        )
        return FinishTaskResponse(
            plan=plan,
            apply=apply,
            report=report,
            artifacts=[],
            clerk="skipped",
            audit_url=f"/v1/plans/{plan.plan_id}/audit",
            filing_urls=[],
        )

    _promote_to_file(plan)
    sanitized = sanitize_tabs(body.tabs)
    result = run_plan(plan, sanitized)
    bank.put_plan(result.plan)
    for record in result.records:
        bank.put_artifact(record)
    if result.report.artifacts_ok and result.apply.close_tab_ids:
        record_event(
            plan_id=result.plan.plan_id,
            user_id=body.user_id,
            agent="runner",
            phase=EventPhase.CLOSE_APPLIED,
            verdict=Verdict.OK,
            summary=f"count={len(result.apply.close_tab_ids)}",
        )
    return FinishTaskResponse(
        plan=result.plan,
        apply=result.apply,
        report=result.report,
        artifacts=result.records,
        clerk=result.clerk,
        audit_url=f"/v1/plans/{result.plan.plan_id}/audit",
        filing_urls=[r.url for r in result.records],
    )


@router.post("/still-going", response_model=StillGoingResponse)
def still_going(
    body: StillGoingRequest,
    x_stillopen_user_token: str | None = Header(default=None),
) -> StillGoingResponse:
    """Enroll one hash-only Watch per URL. Continuous Action Engine hook."""

    _require_user(get_bank(), body.user_id, x_stillopen_user_token)
    enrolled = enroll_from_task(
        user_id=body.user_id,
        label=body.label,
        urls=body.urls,
        kind=WatchKind.TRACKING,
        plan_id=body.task_id,
    )
    return StillGoingResponse(
        enrolled=len(enrolled),
        watch_ids=[w.watch_id for w in enrolled],
    )


__all__ = ["router"]
