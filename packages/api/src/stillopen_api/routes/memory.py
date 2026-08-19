"""Evolving knowledge: inspect, chat preferences, observe closes, schedule."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from stillopen_core.errors import NotFound
from stillopen_core.memory.categorize import TabGroup, categorize_tabs
from stillopen_core.memory.chat import apply_chat, interpret_preference
from stillopen_core.memory.fakes import bank_storage, get_bank
from stillopen_core.memory.habits import mutate, set_cutoff
from stillopen_core.memory.match import match_tabs
from stillopen_core.schemas.base import new_id
from stillopen_core.schemas.habit import (
    FeedbackKind,
    HabitEvent,
    HabitProfile,
    MatchedTab,
    ScheduledClose,
)
from stillopen_core.schemas.tab import TabSnapshot

router = APIRouter(prefix="/v1/memory", tags=["memory"])


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=500)
    tabs: list[TabSnapshot] = Field(default_factory=list, max_length=80)


class ChatResponse(BaseModel):
    reply: str
    parser: str
    profile: HabitProfile
    storage: dict
    wants_close: bool = False
    label: str = ""
    matches: list[MatchedTab] = Field(default_factory=list)
    unused_days: int | None = None
    match_classes: list[str] = Field(default_factory=list)


class ObserveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1, max_length=128)
    kind: FeedbackKind
    host: str = Field(default="", max_length=255)
    title: str = Field(default="", max_length=300)
    source: str = Field(default="chrome", max_length=40)
    stale_cutoff_days: int | None = Field(default=None, ge=1, le=90)


class MemoryResponse(BaseModel):
    storage: dict
    profile: HabitProfile
    scheduled: list[ScheduledClose] = Field(default_factory=list)


class ScheduleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1, max_length=128)
    prompt: str = Field(min_length=1, max_length=500)
    label: str = Field(default="", max_length=80)
    run_at: datetime
    matches: list[MatchedTab] = Field(min_length=1, max_length=80)
    schedule_id: str | None = Field(default=None, max_length=64)


class ScheduleDoneRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1, max_length=128)
    status: str = Field(default="done", max_length=20)


def _snapshot(user_id: str) -> MemoryResponse:
    bank = get_bank()
    return MemoryResponse(
        storage=bank_storage(),
        profile=bank.habit_for(user_id),
        scheduled=bank.scheduled_for(user_id),
    )


@router.get("", response_model=MemoryResponse)
def get_memory(user_id: str = Query(min_length=1, max_length=128)) -> MemoryResponse:
    return _snapshot(user_id)


@router.post("/chat", response_model=ChatResponse)
def chat_memory(body: ChatRequest) -> ChatResponse:
    bank = get_bank()
    profile = bank.habit_for(body.user_id)
    intent = interpret_preference(body.message)
    apply_chat(profile, body.message, intent)
    bank.put_habit(profile)
    matches = match_tabs(body.tabs, intent) if body.tabs else []
    return ChatResponse(
        reply=intent.reply,
        parser=intent.parser,
        profile=profile,
        storage=bank_storage(),
        wants_close=intent.wants_close,
        label=intent.label,
        matches=matches,
        unused_days=intent.unused_days,
        match_classes=intent.match_classes,
    )


@router.post("/observe", response_model=MemoryResponse)
def observe_memory(body: ObserveRequest) -> MemoryResponse:
    if body.kind is FeedbackKind.CHAT:
        raise HTTPException(status_code=400, detail="use /v1/memory/chat")
    bank = get_bank()
    profile = bank.habit_for(body.user_id)
    if body.stale_cutoff_days is not None:
        set_cutoff(profile, body.stale_cutoff_days, source=body.source, phrase=body.title)
    if body.host:
        mutate(
            profile,
            HabitEvent(
                kind=body.kind,
                host_suffix=body.host,
                phrase=body.title or None,
                source=body.source,
            ),
        )
    bank.put_habit(profile)
    return _snapshot(body.user_id)


@router.post("/schedule", response_model=ScheduledClose)
def schedule_close(body: ScheduleRequest) -> ScheduledClose:
    bank = get_bank()
    row = ScheduledClose(
        schedule_id=body.schedule_id or new_id(),
        user_id=body.user_id,
        prompt=body.prompt,
        label=body.label,
        run_at=body.run_at,
        hosts=[item.host for item in body.matches],
        titles=[item.title for item in body.matches],
        urls=[item.url for item in body.matches],
        status="pending",
    )
    bank.put_scheduled(row)
    return row


@router.post("/schedule/{schedule_id}/done", response_model=ScheduledClose)
def finish_schedule(schedule_id: str, body: ScheduleDoneRequest) -> ScheduledClose:
    bank = get_bank()
    try:
        row = bank.get_scheduled(schedule_id)
    except NotFound as exc:
        raise HTTPException(status_code=404, detail="schedule not found") from exc
    if row.user_id != body.user_id:
        raise HTTPException(status_code=404, detail="schedule not found")
    row.status = body.status
    row.touch()
    bank.put_scheduled(row)
    return row


class CategorizeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1, max_length=128)
    tabs: list[TabSnapshot] = Field(min_length=1, max_length=80)


class CategorizeResponse(BaseModel):
    groups: list[TabGroup]


@router.post("/categorize", response_model=CategorizeResponse)
def categorize_memory(body: CategorizeRequest) -> CategorizeResponse:
    return CategorizeResponse(groups=categorize_tabs(body.tabs))
