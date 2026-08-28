"""Per-user bearer tokens for write-path endpoints.

The extension calls ``POST /v1/auth/register`` once (per install) and gets a
random 32-byte token. The server stores only a SHA-256 hash of that token,
bound to the caller's ``user_id``. On subsequent write requests the extension
sends ``X-Stillopen-User-Token: <hex>``. The server hashes it and looks up the
bound ``user_id``. If it doesn't match the body's ``user_id`` the request is
rejected. The plaintext token never touches the model, never leaves the
extension's ``chrome.storage.local``.

When ``STILLOPEN_REQUIRE_USER_TOKEN`` is unset (default) enforcement is off, so
existing tests / older clients keep working. Turn it on in production to close
the CORS gap.
"""

from __future__ import annotations

import hashlib
import secrets

from stillopen_core.config import get_settings
from stillopen_core.memory.fakes import MemoryBank

TOKEN_BYTES = 32


def _sha256(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_token(bank: MemoryBank, user_id: str) -> str:
    """Mint a token, persist ``sha256(token)`` in the bank, return the plaintext.

    The plaintext is only returned to the caller of ``/v1/auth/register`` and
    never stored anywhere else. If the caller loses it they simply re-register.
    """

    token = secrets.token_hex(TOKEN_BYTES)
    bank.put_token(user_id, f"user_token:{_sha256(token)}")
    return token


def is_enforced() -> bool:
    return bool(get_settings().require_user_token)


def verify_token(bank: MemoryBank, user_id: str, token: str | None) -> bool:
    """Return True if the header token matches the stored hash for ``user_id``.

    A missing header or a user with no token registered is always rejected when
    enforcement is on. Constant-time comparison prevents timing leaks.
    """

    if not token:
        return False
    stored = bank.get_token(user_id) or ""
    if not stored.startswith("user_token:"):
        return False
    want = stored.split(":", 1)[1]
    return secrets.compare_digest(_sha256(token), want)


__all__ = ["issue_token", "is_enforced", "verify_token", "TOKEN_BYTES"]
