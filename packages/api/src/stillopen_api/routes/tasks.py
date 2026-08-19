"""Named tasks from the current window."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field
from stillopen_core.memory.tasks import infer_tasks
from stillopen_core.schemas.tab import TabSnapshot
from stillopen_core.schemas.task import OpenTask

router = APIRouter(prefix="/v1/tasks", tags=["tasks"])


class InferTasksRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    user_id: str = Field(min_length=1, max_length=128)
    tabs: list[TabSnapshot] = Field(min_length=1, max_length=200)
    cutoff_days: int = Field(default=7, ge=1, le=90)
    existing: list[OpenTask] = Field(default_factory=list, max_length=80)
    ignored_urls: list[str] = Field(default_factory=list, max_length=200)


class InferTasksResponse(BaseModel):
    tasks: list[OpenTask]


@router.post("", response_model=InferTasksResponse)
def infer_open_tasks(body: InferTasksRequest) -> InferTasksResponse:
    return InferTasksResponse(
        tasks=infer_tasks(
            body.tabs,
            cutoff_days=body.cutoff_days,
            existing=body.existing or None,
            ignored_urls=body.ignored_urls or None,
        )
    )
