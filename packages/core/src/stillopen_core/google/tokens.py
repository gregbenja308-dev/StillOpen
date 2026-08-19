"""Encrypted OAuth token blobs. Never log plaintext."""

from __future__ import annotations

import json
from typing import Any

from stillopen_core.config import get_settings
from stillopen_core.errors import TokenPersistDenied
from stillopen_core.memory.fakes import get_bank
from stillopen_core.security.crypto import decrypt_secret, encrypt_secret


def save_token_blob(user_id: str, payload: dict[str, Any]) -> None:
    settings = get_settings()
    if not settings.can_persist_tokens:
        raise TokenPersistDenied("STILLOPEN_TOKEN_KEY is empty; refusing to persist OAuth tokens")
    blob = encrypt_secret(settings.token_key, json.dumps(payload))
    get_bank().put_token(user_id, blob)


def load_token_blob(user_id: str) -> dict[str, Any] | None:
    settings = get_settings()
    blob = get_bank().get_token(user_id)
    if not blob:
        return None
    if not settings.can_persist_tokens:
        raise TokenPersistDenied("STILLOPEN_TOKEN_KEY is empty; cannot decrypt tokens")
    raw = decrypt_secret(settings.token_key, blob)
    data = json.loads(raw)
    if not isinstance(data, dict):
        return None
    return data


def has_token(user_id: str) -> bool:
    return get_bank().get_token(user_id) is not None


__all__ = ["has_token", "load_token_blob", "save_token_blob"]
