"""Cloud Scheduler → Watch tick. Hash-only fetch in cloud."""

from __future__ import annotations

import os

from fastapi import APIRouter, Header, HTTPException
from stillopen_core.config import get_settings
from stillopen_core.watch.fetch import fetch_forbidden, hash_only_fetch
from stillopen_core.watch.tick import tick

router = APIRouter(prefix="/v1/jobs", tags=["jobs"])


@router.post("/watch")
def watch_tick(x_stillopen_job_token: str | None = Header(default=None)) -> dict[str, object]:
    settings = get_settings()
    if settings.job_token and x_stillopen_job_token != settings.job_token:
        raise HTTPException(status_code=401, detail="bad job token")
    live = settings.env.value == "cloud" or os.environ.get("STILLOPEN_WATCH_FETCH") == "1"
    fetcher = hash_only_fetch if live else fetch_forbidden
    acted = tick(fetcher=fetcher)
    return {
        "acted": len(acted),
        "watches": [
            {
                "watch_id": w.watch_id,
                "status": w.status.value,
                "last_action": w.last_action,
                "url": w.url,
            }
            for w in acted
        ],
        "fetcher": "hash_only" if live else "forbidden",
    }
