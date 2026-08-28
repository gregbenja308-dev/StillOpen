"""Firestore MemoryBank. Same document shape as local bank.json."""

from __future__ import annotations

from typing import Any

from stillopen_core.config import get_settings
from stillopen_core.errors import NotFound
from stillopen_core.observability.logger import get_logger
from stillopen_core.schemas.artifact import ArtifactRecord
from stillopen_core.schemas.event import PlanEvent
from stillopen_core.schemas.habit import HabitProfile, ScheduledClose
from stillopen_core.schemas.plan import Plan
from stillopen_core.schemas.tab import TabSnapshot
from stillopen_core.schemas.watch import Watch

_logger = get_logger(__name__)


def _client() -> Any:
    from google.cloud import firestore

    settings = get_settings()
    return firestore.Client(project=settings.gcp_project, database=settings.firestore_database)


class FirestoreBank:
    """Drop-in behind get_bank() when STILLOPEN_ENV=cloud."""

    def __init__(self, client: Any | None = None) -> None:
        self._db = client or _client()
        self.plans: dict[str, Plan] = {}
        self.habits: dict[str, HabitProfile] = {}
        self.watches: dict[str, Watch] = {}
        self.artifacts: dict[str, ArtifactRecord] = {}
        self.tab_sets: dict[str, list[TabSnapshot]] = {}
        self.scheduled: dict[str, ScheduledClose] = {}
        self.tokens: dict[str, str] = {}
        self.events: dict[str, list[PlanEvent]] = {}
        self.filings: dict[str, dict[str, Any]] = {}

    def _col(self, name: str) -> Any:
        return self._db.collection(name)

    def _write(self, collection: str, doc_id: str, payload: dict[str, Any]) -> None:
        self._col(collection).document(doc_id).set(payload)

    def put_plan(self, plan: Plan) -> None:
        self.plans[plan.plan_id] = plan
        self._write("plans", plan.plan_id, plan.model_dump(mode="json"))

    def get_plan(self, plan_id: str) -> Plan:
        if plan_id in self.plans:
            return self.plans[plan_id]
        snap = self._col("plans").document(plan_id).get()
        if not snap.exists:
            raise NotFound("plans", plan_id)
        plan = Plan.model_validate(snap.to_dict(), strict=False)
        self.plans[plan.plan_id] = plan
        return plan

    def put_tabs(self, plan_id: str, tabs: list[TabSnapshot]) -> None:
        clean = [t.model_copy(update={"extract": None}) for t in tabs]
        self.tab_sets[plan_id] = clean
        self._write(
            "tab_sets",
            plan_id,
            {"tabs": [t.model_dump(mode="json") for t in clean]},
        )

    def get_tabs(self, plan_id: str) -> list[TabSnapshot]:
        if plan_id in self.tab_sets:
            return self.tab_sets[plan_id]
        snap = self._col("tab_sets").document(plan_id).get()
        if not snap.exists:
            raise NotFound("tab_sets", plan_id)
        raw_tabs = (snap.to_dict() or {}).get("tabs") or []
        tabs = [TabSnapshot.model_validate(t, strict=False) for t in raw_tabs]
        self.tab_sets[plan_id] = tabs
        return tabs

    def habit_for(self, user_id: str) -> HabitProfile:
        if user_id in self.habits:
            return self.habits[user_id]
        snap = self._col("habits").document(user_id).get()
        if snap.exists:
            profile = HabitProfile.model_validate(snap.to_dict(), strict=False)
        else:
            profile = HabitProfile(user_id=user_id)
        self.habits[user_id] = profile
        return profile

    def put_habit(self, profile: HabitProfile) -> None:
        self.habits[profile.user_id] = profile
        self._write("habits", profile.user_id, profile.model_dump(mode="json"))

    def put_watch(self, watch: Watch) -> None:
        self.watches[watch.watch_id] = watch
        self._write("watches", watch.watch_id, watch.model_dump(mode="json"))

    def due_watches(self) -> list[Watch]:
        return [w for w in self.list_watches() if w.is_due()]

    def list_watches(self) -> list[Watch]:
        found: dict[str, Watch] = {}
        for snap in self._col("watches").stream():
            data = snap.to_dict() or {}
            watch = Watch.model_validate(data, strict=False)
            found[watch.watch_id] = watch
        self.watches = found
        return list(found.values())

    def put_artifact(self, record: ArtifactRecord) -> None:
        self.artifacts[record.record_id] = record
        self._write("artifacts", record.record_id, record.model_dump(mode="json"))

    def artifact_by_google_id(self, google_id: str) -> ArtifactRecord | None:
        for record in self.artifacts.values():
            if record.google_id == google_id:
                return record
        for snap in self._col("artifacts").where("google_id", "==", google_id).limit(1).stream():
            return ArtifactRecord.model_validate(snap.to_dict(), strict=False)
        return None

    def put_scheduled(self, row: ScheduledClose) -> None:
        self.scheduled[row.schedule_id] = row
        self._write("scheduled", row.schedule_id, row.model_dump(mode="json"))

    def scheduled_for(self, user_id: str) -> list[ScheduledClose]:
        rows: list[ScheduledClose] = []
        for snap in self._col("scheduled").where("user_id", "==", user_id).stream():
            rows.append(ScheduledClose.model_validate(snap.to_dict(), strict=False))
        rows.sort(key=lambda row: row.run_at)
        return rows

    def get_scheduled(self, schedule_id: str) -> ScheduledClose:
        if schedule_id in self.scheduled:
            return self.scheduled[schedule_id]
        snap = self._col("scheduled").document(schedule_id).get()
        if not snap.exists:
            raise NotFound("scheduled", schedule_id)
        row = ScheduledClose.model_validate(snap.to_dict(), strict=False)
        self.scheduled[schedule_id] = row
        return row

    def put_token(self, user_id: str, blob: str) -> None:
        self.tokens[user_id] = blob
        self._write("tokens", user_id, {"blob": blob})

    def get_token(self, user_id: str) -> str | None:
        if user_id in self.tokens:
            return self.tokens[user_id]
        snap = self._col("tokens").document(user_id).get()
        if not snap.exists:
            return None
        blob = (snap.to_dict() or {}).get("blob")
        return blob if isinstance(blob, str) else None

    def append_event(self, event: PlanEvent) -> None:
        rows = self.events.setdefault(event.plan_id, [])
        rows.append(event)
        self._write(
            f"plans/{event.plan_id}/events",
            event.event_id,
            event.model_dump(mode="json"),
        )

    def list_events(self, plan_id: str) -> list[PlanEvent]:
        if plan_id in self.events:
            return list(self.events[plan_id])
        rows: list[PlanEvent] = []
        for snap in self._col(f"plans/{plan_id}/events").stream():
            rows.append(PlanEvent.model_validate(snap.to_dict(), strict=False))
        rows.sort(key=lambda e: e.created_at)
        self.events[plan_id] = rows
        return list(rows)

    def put_filing(self, filing_id: str, payload: dict[str, Any]) -> None:
        self.filings[filing_id] = payload
        self._write("filings", filing_id, payload)

    def get_filing(self, filing_id: str) -> dict[str, Any]:
        if filing_id in self.filings:
            return self.filings[filing_id]
        snap = self._col("filings").document(filing_id).get()
        if not snap.exists:
            raise NotFound("filings", filing_id)
        payload = snap.to_dict() or {}
        self.filings[filing_id] = payload
        return payload


def firestore_storage() -> dict[str, Any]:
    settings = get_settings()
    return {
        "engine": "MemoryBank",
        "backend": "firestore",
        "path": f"projects/{settings.gcp_project}/databases/{settings.firestore_database}",
        "collections": [
            "plans",
            "plans/{plan_id}/events",
            "habits",
            "watches",
            "artifacts",
            "tab_sets",
            "scheduled",
            "tokens",
            "filings",
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
            "Cloud MemoryBank. Documents are redacted snapshots only. "
            "Original Undo URLs never leave chrome.storage.session. "
            "OAuth tokens are Fernet-encrypted blobs."
        ),
    }


__all__ = ["FirestoreBank", "firestore_storage"]
