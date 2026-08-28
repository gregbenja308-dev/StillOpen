"""``POST /v1/auth/register`` — issue a per-user bearer token.

Idempotent per install (Chrome extension). The token is returned exactly once
and stored client-side in ``chrome.storage.local``. The server keeps only a
SHA-256 hash of it, bound to ``user_id``.

Under ``STILLOPEN_REQUIRE_USER_TOKEN=1`` sensitive write endpoints check
``X-Stillopen-User-Token`` against this hash. See
``packages/core/src/stillopen_core/security/user_token.py``.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field
from stillopen_core.memory.fakes import get_bank
from stillopen_core.security.user_token import (
    is_enforced,
    issue_token,
)

router = APIRouter(prefix="/v1/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1, max_length=128)


class RegisterResponse(BaseModel):
    user_id: str
    token: str
    enforced: bool


@router.post("/register", response_model=RegisterResponse)
def register(body: RegisterRequest) -> RegisterResponse:
    bank = get_bank()
    token = issue_token(bank, body.user_id)
    return RegisterResponse(user_id=body.user_id, token=token, enforced=is_enforced())


__all__ = ["router"]
