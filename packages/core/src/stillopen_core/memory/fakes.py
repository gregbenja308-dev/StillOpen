"""In-memory Memory Bank: plans, habits, watches, artifacts, tab sets."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from stillopen_core.errors import NotFound
from stillopen_core.schemas.artifact import ArtifactRecord
from stillopen_core.schemas.habit import HabitProfile, ScheduledClose
from stillopen_core.schemas.plan import Plan
from stillopen_core.schemas.tab import TabSnapshot
from stillopen_core.schemas.watch import Watch

_BANK_PATH = Path(".stillopen/bank.json")


class MemoryBank:
    def __init__(self) -> None:
        self.plans: dict[str, Plan] = {}
        self.habits: dict[str, HabitProfile] = {}
        self.watches: dict[str, Watch] = {}
        self.artifacts: dict[str, ArtifactRecord] = {}
        self.tab_sets: dict[str, list[TabSnapshot]] = {}
        self.scheduled: dict[str, ScheduledClose] = {}
        self.tokens: dict[str, str] = {}

    def put_plan(self, plan: Plan) -> None:
        self.plans[plan.plan_id] = plan
        persist(self)

    def get_plan(self, plan_id: str) -> Plan:
        plan = self.plans.get(plan_id)
        if plan is None:
            raise NotFound("plans", plan_id)
        return plan

    def put_tabs(self, plan_id: str, tabs: list[TabSnapshot]) -> None:
        self.tab_sets[plan_id] = [
            t.model_copy(update={"extract": None}) for t in tabs
        ]
        persist(self)

    def get_tabs(self, plan_id: str) -> list[TabSnapshot]:
        tabs = self.tab_sets.get(plan_id)
        if tabs is None:
            raise NotFound("tab_sets", plan_id)
        return tabs

    def habit_for(self, user_id: str) -> HabitProfile:
        if user_id not in self.habits:
            self.habits[user_id] = HabitProfile(user_id=user_id)
        return self.habits[user_id]

    def put_habit(self, profile: HabitProfile) -> None:
        self.habits[profile.user_id] = profile
        persist(self)

    def put_watch(self, watch: Watch) -> None:
        self.watches[watch.watch_id] = watch
        persist(self)

    def due_watches(self) -> list[Watch]:
        return [w for w in self.watches.values() if w.is_due()]

    def put_artifact(self, record: ArtifactRecord) -> None:
        self.artifacts[record.record_id] = record
        persist(self)

    def artifact_by_google_id(self, google_id: str) -> ArtifactRecord | None:
        for record in self.artifacts.values():
            if record.google_id == google_id:
                return record
        return None

    def put_scheduled(self, row: ScheduledClose) -> None:
        self.scheduled[row.schedule_id] = row
        persist(self)

    def scheduled_for(self, user_id: str) -> list[ScheduledClose]:
        rows = [row for row in self.scheduled.values() if row.user_id == user_id]
        rows.sort(key=lambda row: row.run_at)
        return rows

    def get_scheduled(self, schedule_id: str) -> ScheduledClose:
        row = self.scheduled.get(schedule_id)
        if row is None:
            raise NotFound("scheduled", schedule_id)
        return row

    def put_token(self, user_id: str, blob: str) -> None:
        self.tokens[user_id] = blob
        persist(self)

    def get_token(self, user_id: str) -> str | None:
        return self.tokens.get(user_id)

    def list_watches(self) -> list[Watch]:
        return list(self.watches.values())


def _should_persist() -> bool:
    return os.environ.get("PYTEST_CURRENT_TEST") is None


def bank_storage() -> dict[str, Any]:
    from stillopen_core.config import get_settings

    if get_settings().use_firestore:
        from stillopen_core.memory.firestore import firestore_storage

        return firestore_storage()
    return {
        "engine": "MemoryBank",
        "backend": "local_json",
        "path": str(_BANK_PATH.resolve()),
        "collections": [
            "plans",
            "habits",
            "watches",
            "artifacts",
            "tab_sets",
            "scheduled",
            "tokens",
        ],
        "habit_fields": [
            "rules",
            "stale_cutoff_days",
            "statements",
            "hosts",
            "mutations",
            "chats",
            "close_classes",
        ],
        "note": (
            "Firestore-shaped document store. Locally this is one JSON file, "
            "rewritten on every put. Original tab URLs for Undo stay in the "
            "extension chrome.storage.session — never here. Tokens are Fernet "
            "blobs only when STILLOPEN_TOKEN_KEY is set."
        ),
    }


def persist(bank: MemoryBank) -> None:
    if not _should_persist():
        return
    _BANK_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "plans": [p.model_dump(mode="json") for p in bank.plans.values()],
        "habits": [h.model_dump(mode="json") for h in bank.habits.values()],
        "watches": [w.model_dump(mode="json") for w in bank.watches.values()],
        "artifacts": [a.model_dump(mode="json") for a in bank.artifacts.values()],
        "tab_sets": {
            pid: [t.model_dump(mode="json") for t in tabs]
            for pid, tabs in bank.tab_sets.items()
        },
        "scheduled": [s.model_dump(mode="json") for s in bank.scheduled.values()],
        "tokens": dict(bank.tokens),
    }
    _BANK_PATH.write_text(json.dumps(payload, default=str), encoding="utf-8")


def load_bank() -> MemoryBank:
    bank = MemoryBank()
    if not _BANK_PATH.exists() or not _should_persist():
        return bank
    raw = json.loads(_BANK_PATH.read_text(encoding="utf-8"))
    for row in raw.get("plans") or []:
        plan = Plan.model_validate(row, strict=False)
        bank.plans[plan.plan_id] = plan
    for row in raw.get("habits") or []:
        profile = HabitProfile.model_validate(row, strict=False)
        bank.habits[profile.user_id] = profile
    for row in raw.get("watches") or []:
        watch = Watch.model_validate(row, strict=False)
        bank.watches[watch.watch_id] = watch
    for row in raw.get("artifacts") or []:
        record = ArtifactRecord.model_validate(row, strict=False)
        bank.artifacts[record.record_id] = record
    for pid, tabs in (raw.get("tab_sets") or {}).items():
        bank.tab_sets[pid] = [TabSnapshot.model_validate(t, strict=False) for t in tabs]
    for row in raw.get("scheduled") or []:
        item = ScheduledClose.model_validate(row, strict=False)
        bank.scheduled[item.schedule_id] = item
    for user_id, blob in (raw.get("tokens") or {}).items():
        if isinstance(blob, str):
            bank.tokens[user_id] = blob
    return bank


_BANK = MemoryBank()


def get_bank() -> MemoryBank:
    return _BANK


def reset_bank() -> MemoryBank:
    global _BANK
    _BANK = MemoryBank()
    return _BANK


def init_bank() -> MemoryBank:
    """Load disk snapshot once at API startup (no-op under pytest). Cloud → Firestore."""
    global _BANK
    from stillopen_core.config import get_settings

    settings = get_settings()
    if settings.use_firestore and os.environ.get("PYTEST_CURRENT_TEST") is None:
        from stillopen_core.memory.firestore import FirestoreBank

        _BANK = FirestoreBank()  # type: ignore[assignment]
        return _BANK
    _BANK = load_bank()
    return _BANK


__all__ = ["MemoryBank", "bank_storage", "get_bank", "init_bank", "reset_bank"]
