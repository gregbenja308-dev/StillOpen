"""Named open tasks. A task is a goal, not a host-class bucket."""

from __future__ import annotations

from enum import Enum

from pydantic import ConfigDict, Field, field_validator

from stillopen_core.schemas.base import StillOpenModel, new_id
from stillopen_core.schemas.tab import Intention


class TaskKind(str, Enum):
    DURABLE = "durable"
    EPHEMERAL = "ephemeral"
    PROTECTED = "protected"


class OpenTask(StillOpenModel):
    model_config = ConfigDict(
        strict=True,
        extra="ignore",
        validate_assignment=True,
        populate_by_name=True,
        frozen=False,
    )
    task_id: str = Field(default_factory=new_id)
    label: str
    tab_ids: list[int]
    kind: TaskKind
    hosts: list[str] = Field(default_factory=list)
    titles: list[str] = Field(default_factory=list)
    urls: list[str] = Field(default_factory=list)
    group_title: str = ""
    quiet: bool = False
    intention: Intention = Intention.UNKNOWN
    user_locked: bool = False

    @field_validator("kind", mode="before")
    @classmethod
    def _kind(cls, value: object) -> TaskKind:
        if isinstance(value, TaskKind):
            return value
        if value in {item.value for item in TaskKind}:
            return TaskKind(str(value))
        return TaskKind.EPHEMERAL

    @field_validator("intention", mode="before")
    @classmethod
    def _intention(cls, value: object) -> Intention:
        if isinstance(value, Intention):
            return value
        if value in {item.value for item in Intention}:
            return Intention(str(value))
        return Intention.UNKNOWN

    @field_validator("tab_ids", mode="before")
    @classmethod
    def _tab_ids(cls, value: object) -> object:
        if not isinstance(value, list):
            return value
        out: list[int] = []
        for item in value:
            try:
                out.append(int(float(str(item))))
            except (TypeError, ValueError):
                return value
        return out


__all__ = ["OpenTask", "TaskKind"]
