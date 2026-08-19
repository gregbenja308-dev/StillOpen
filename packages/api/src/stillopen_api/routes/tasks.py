"""Named tasks from the current window."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field
from stillopen_core.memory.tasks import infer_tasks
from stillopen_core.schemas.tab import TabSnapshot
from stillopen_core.schemas.task import OpenTask

router = APIRouter(prefix="/v1/tasks", tags=["tasks"])


class InferTasksRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1, max_length=128)
    tabs: list[TabSnapshot] = Field(min_length=1, max_length=80)
    cutoff_days: int = Field(default=7, ge=1, le=90)


class InferTasksResponse(BaseModel):
    tasks: list[OpenTask]


@router.post("", response_model=InferTasksResponse)
def infer_open_tasks(body: InferTasksRequest) -> InferTasksResponse:
    return InferTasksResponse(tasks=infer_tasks(body.tabs, cutoff_days=body.cutoff_days))
