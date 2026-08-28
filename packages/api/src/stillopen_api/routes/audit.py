"""``GET /v1/plans/{plan_id}/audit`` — reasoning-chain replay for judges."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from stillopen_core.errors import NotFound
from stillopen_core.memory.fakes import get_bank
from stillopen_core.observability.tracing import current_trace_id
from stillopen_core.schemas.event import PlanEvent
from stillopen_core.schemas.plan import PlanStatus

router = APIRouter(prefix="/v1/plans", tags=["audit"])


class AuditResponse(BaseModel):
    plan_id: str
    user_id: str
    status: PlanStatus
    trace_id: str | None
    current_trace_id: str | None
    events: list[PlanEvent] = Field(default_factory=list)


@router.get("/{plan_id}/audit", response_model=AuditResponse)
def audit(plan_id: str) -> AuditResponse:
    bank = get_bank()
    try:
        plan = bank.get_plan(plan_id)
    except NotFound as exc:
        raise HTTPException(status_code=404, detail="plan not found") from exc
    return AuditResponse(
        plan_id=plan.plan_id,
        user_id=plan.user_id,
        status=plan.status,
        trace_id=plan.trace_id,
        current_trace_id=current_trace_id(),
        events=bank.list_events(plan_id),
    )


__all__ = ["router"]
