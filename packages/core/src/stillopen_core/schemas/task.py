"""Named open tasks. A task is a goal, not a host-class bucket."""

from __future__ import annotations

from enum import Enum

from pydantic import Field

from stillopen_core.schemas.base import StillOpenModel, new_id
from stillopen_core.schemas.tab import Intention


class TaskKind(str, Enum):
    DURABLE = "durable"
    EPHEMERAL = "ephemeral"
    PROTECTED = "protected"


class OpenTask(StillOpenModel):
    task_id: str = Field(default_factory=new_id)
    label: str
    tab_ids: list[int]
    kind: TaskKind
    hosts: list[str] = Field(default_factory=list)
    titles: list[str] = Field(default_factory=list)
    group_title: str = ""
    quiet: bool = False
    intention: Intention = Intention.UNKNOWN


__all__ = ["OpenTask", "TaskKind"]
