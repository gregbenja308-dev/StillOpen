"""Cheap vectors over redacted title+host. Never embed extracts or query strings.

Local: hashed bag-of-words (deterministic, no network).
Cloud scale-up: text-embedding-004 with a user_id restrict — same TabIndex interface.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol

_DIM = 64
_TOKEN = re.compile(r"[a-z0-9]+")


class Embedder(Protocol):
    def embed(self, text: str) -> list[float]: ...


class HashEmbedder:
    """64-d hashed bag-of-words, L2-normalized. Fine for tests and local plan matching."""

    dim: int = _DIM

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * _DIM
        for token in _TOKEN.findall(text.lower()):
            if len(token) < 3:
                continue
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:2], "big") % _DIM
            sign = 1.0 if digest[2] % 2 == 0 else -1.0
            vec[idx] += sign
        return _l2(vec)


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def _l2(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


class TabIndex:
    """In-memory index of tab vectors. Cloud: Vertex Vector Search with user_id restrict."""

    def __init__(self, embedder: Embedder | None = None) -> None:
        self._embedder = embedder or HashEmbedder()
        self._rows: list[tuple[int, list[float]]] = []

    def index_text(self, tab_id: int, text: str) -> None:
        self._rows.append((tab_id, self._embedder.embed(text)))

    def query(self, text: str, *, k: int = 12) -> list[tuple[int, float]]:
        q = self._embedder.embed(text)
        scored = [(tab_id, cosine(q, vec)) for tab_id, vec in self._rows]
        scored.sort(key=lambda row: row[1], reverse=True)
        return scored[:k]


__all__ = ["Embedder", "HashEmbedder", "TabIndex", "cosine"]
