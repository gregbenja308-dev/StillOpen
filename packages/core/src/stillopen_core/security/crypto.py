"""Fernet helpers for OAuth tokens at rest. Never log plaintext."""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from stillopen_core.errors import TokenPersistDenied


def generate_key() -> str:
    return Fernet.generate_key().decode("ascii")


def encrypt_secret(key: str, plaintext: str) -> str:
    if not key:
        raise TokenPersistDenied("STILLOPEN_TOKEN_KEY is empty; refusing to persist secrets")
    return Fernet(key.encode("ascii")).encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_secret(key: str, token: str) -> str:
    if not key:
        raise TokenPersistDenied("STILLOPEN_TOKEN_KEY is empty; cannot decrypt")
    try:
        return Fernet(key.encode("ascii")).decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise TokenPersistDenied("token decrypt failed") from exc


__all__ = ["decrypt_secret", "encrypt_secret", "generate_key"]
