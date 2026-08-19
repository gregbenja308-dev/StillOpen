"""Plan endpoints: propose, override checkboxes, run (file then close list)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from stillopen_core.agents.conductor import propose_plan
from stillopen_core.agents.overrides import apply_overrides, learn_unchecks
from stillopen_core.agents.run_conductor import run_plan
from stillopen_core.errors import NotFound
from stillopen_core.memory.fakes import get_bank
from stillopen_core.schemas.agent import TabApply, VerifyReport
from stillopen_core.schemas.artifact import ArtifactRecord
from stillopen_core.schemas.plan import Plan
from stillopen_core.schemas.tab import TabSnapshot
from stillopen_core.surveyor.sanitize import sanitize_tabs

router = APIRouter(prefix="/v1/plans", tags=["plans"])


class CreatePlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1, max_length=128)
    command: str | None = Field(default=None, max_length=500)
    tabs: list[TabSnapshot] = Field(min_length=1, max_length=80)
    force_file: bool = False


class ActionOverride(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tab_id: int
    checked: bool


class RunPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overrides: list[ActionOverride] = Field(default_factory=list)


class RunPlanResponse(BaseModel):
    plan: Plan
    apply: TabApply
    report: VerifyReport
    artifacts: list[ArtifactRecord]
    clerk: str = "heuristic"


@router.post("", response_model=Plan)
def create_plan(body: CreatePlanRequest) -> Plan:
    return propose_plan(
        user_id=body.user_id,
        tabs=body.tabs,
        command=body.command,
        force_file=body.force_file,
    )


@router.get("/{plan_id}", response_model=Plan)
def get_plan(plan_id: str) -> Plan:
    try:
        return get_bank().get_plan(plan_id)
    except NotFound as exc:
        raise HTTPException(status_code=404, detail="plan not found") from exc


@router.post("/{plan_id}/run", response_model=RunPlanResponse)
def run_existing_plan(plan_id: str, body: RunPlanRequest) -> RunPlanResponse:
    bank = get_bank()
    try:
        plan = bank.get_plan(plan_id)
        tabs = bank.get_tabs(plan_id)
    except NotFound as exc:
        raise HTTPException(status_code=404, detail="plan not found") from exc

    overrides = {row.tab_id: row.checked for row in body.overrides}
    unchecked = apply_overrides(plan, overrides)
    sanitized = sanitize_tabs(tabs)
    if unchecked:
        profile = bank.habit_for(plan.user_id)
        learn_unchecks(profile, unchecked, sanitized, plan.command)
        bank.put_habit(profile)

    result = run_plan(plan, sanitized)
    bank.put_plan(result.plan)
    for record in result.records:
        bank.put_artifact(record)
    return RunPlanResponse(
        plan=result.plan,
        apply=result.apply,
        report=result.report,
        artifacts=result.records,
        clerk=result.clerk,
    )
