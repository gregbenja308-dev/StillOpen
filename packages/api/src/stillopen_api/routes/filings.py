"""``GET /v1/filings/{filing_id}`` — render a durable filing.

Firestore-backed. No OAuth. Not a Google Doc, but a real Google Cloud
artifact with a shareable link.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from stillopen_core.errors import NotFound
from stillopen_core.memory.fakes import get_bank

router = APIRouter(prefix="/v1/filings", tags=["filings"])


class Filing(BaseModel):
    filing_id: str
    kind: str
    title: str
    body: str
    user_id: str = ""
    created_at: str = ""


def _fetch(filing_id: str) -> dict[str, object]:
    try:
        return get_bank().get_filing(filing_id)
    except NotFound as exc:
        raise HTTPException(status_code=404, detail="filing not found") from exc


@router.get("/{filing_id}")
def get_filing(filing_id: str, format: str = Query(default="html")) -> object:
    payload = _fetch(filing_id)
    if format == "json":
        return Filing(
            filing_id=str(payload.get("filing_id") or filing_id),
            kind=str(payload.get("kind") or ""),
            title=str(payload.get("title") or ""),
            body=str(payload.get("body") or ""),
            user_id=str(payload.get("user_id") or ""),
            created_at=str(payload.get("created_at") or ""),
        )
    title = str(payload.get("title") or "Still Open filing")
    body = str(payload.get("body") or "")
    kind = str(payload.get("kind") or "doc")
    created_at = str(payload.get("created_at") or "")
    return HTMLResponse(
        f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{_escape(title)}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body {{ font: 16px/1.5 -apple-system, system-ui, sans-serif; max-width: 720px; margin: 40px auto; padding: 0 20px; color: #1c1c1e; }}
    header {{ color: #6b6b70; margin-bottom: 24px; }}
    kbd {{ background: #eee; padding: 2px 6px; border-radius: 4px; font-size: 12px; }}
    pre {{ white-space: pre-wrap; background: #f7f7f7; padding: 16px; border-radius: 8px; }}
    h1 {{ font-size: 22px; }}
    h2 {{ font-size: 16px; color: #444; }}
  </style>
</head>
<body>
  <header>
    <p><kbd>Still Open</kbd> · {_escape(kind)} · {_escape(created_at)}</p>
    <h1>{_escape(title)}</h1>
  </header>
  <pre>{_escape(body)}</pre>
</body>
</html>"""
    )


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\"", "&quot;")
        .replace("'", "&#39;")
    )


__all__ = ["router"]
