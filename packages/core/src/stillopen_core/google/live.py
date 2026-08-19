"""Live Docs / Calendar via least-privilege OAuth. Opt-in; FakeGoogle stays default."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from stillopen_core.errors import ConfigError
from stillopen_core.google.oauth import credentials_for
from stillopen_core.observability.logger import get_logger
from stillopen_core.schemas.artifact import ArtifactKind, ArtifactRecord

_logger = get_logger(__name__)


class LiveGoogle:
    def __init__(self, user_id: str) -> None:
        creds = credentials_for(user_id)
        if creds is None:
            raise ConfigError("no OAuth credentials for this user")
        try:
            from googleapiclient.discovery import build
        except ImportError as exc:
            raise ConfigError("google-api-python-client is not installed (core[cloud])") from exc
        self._creds = creds
        self._docs = build("docs", "v1", credentials=creds, cache_discovery=False)
        self._drive = build("drive", "v3", credentials=creds, cache_discovery=False)
        self._calendar = build("calendar", "v3", credentials=creds, cache_discovery=False)

    def create(self, kind: ArtifactKind, title: str, body: str = "") -> ArtifactRecord:
        if kind is ArtifactKind.DOC:
            return self._create_doc(title, body)
        if kind is ArtifactKind.EVENT:
            return self._create_event(title, body)
        if kind is ArtifactKind.TASK:
            return self._create_event(f"Task: {title}", body)
        raise ConfigError(f"live google cannot create {kind.value}")

    def exists(self, kind: ArtifactKind, google_id: str) -> bool:
        try:
            if kind is ArtifactKind.DOC:
                self._docs.documents().get(documentId=google_id).execute()
                return True
            if kind in {ArtifactKind.EVENT, ArtifactKind.TASK}:
                self._calendar.events().get(calendarId="primary", eventId=google_id).execute()
                return True
        except Exception as exc:  # noqa: BLE001 — missing artifact is a verify miss
            _logger.info("google.exists_miss", kind=kind.value, error=type(exc).__name__)
            return False
        return False

    def _create_doc(self, title: str, body: str) -> ArtifactRecord:
        created = self._docs.documents().create(body={"title": title}).execute()
        google_id = str(created["documentId"])
        if body:
            self._docs.documents().batchUpdate(
                documentId=google_id,
                body={"requests": [{"insertText": {"location": {"index": 1}, "text": body}}]},
            ).execute()
        url = f"https://docs.google.com/document/d/{google_id}/edit"
        _logger.info("google.doc_created", google_id=google_id)
        return ArtifactRecord(
            draft_id="",
            kind=ArtifactKind.DOC,
            google_id=google_id,
            url=url,
            title=title,
            body_preview=body[:200],
        )

    def _create_event(self, title: str, body: str) -> ArtifactRecord:
        start = datetime.now(tz=UTC) + timedelta(days=1)
        end = start + timedelta(hours=1)
        created = (
            self._calendar.events()
            .insert(
                calendarId="primary",
                body={
                    "summary": title,
                    "description": body,
                    "start": {"dateTime": start.isoformat(), "timeZone": "UTC"},
                    "end": {"dateTime": end.isoformat(), "timeZone": "UTC"},
                },
            )
            .execute()
        )
        google_id = str(created["id"])
        url = str(created.get("htmlLink") or f"https://calendar.google.com/calendar/event?eid={google_id}")
        _logger.info("google.event_created", google_id=google_id)
        return ArtifactRecord(
            draft_id="",
            kind=ArtifactKind.EVENT,
            google_id=google_id,
            url=url,
            title=title,
            body_preview=body[:200],
        )


__all__ = ["LiveGoogle"]
