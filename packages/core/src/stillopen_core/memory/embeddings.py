"""Cheap vectors over redacted title+host. Never embed extracts or query strings.

Local: hashed bag-of-words (deterministic, no network).
Cloud: ``text-embedding-004`` on Vertex, gated by ``STILLOPEN_USE_VERTEX_EMBEDDINGS``.
Both implement the same ``Embedder`` protocol; ``TabIndex`` is oblivious.

The Vertex path caches per-text vectors in-process to avoid retries on the
same query for a single plan (typical: ~12 tabs plus the plan command).
"""

from __future__ import annotations

import hashlib
import math
import os
import re
from functools import lru_cache
from typing import Protocol

from stillopen_core.observability.logger import get_logger

_logger = get_logger(__name__)

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


class VertexEmbedder:
    """``text-embedding-004`` via google-genai. Falls back to HashEmbedder on error.

    Titles + hosts only. Deny-listed tabs never reach this class because
    ``rank_prompt_ids`` filters them upstream. We never embed extracts,
    query strings, or the user's notes.
    """

    dim: int = 768

    def __init__(self, model: str = "text-embedding-004") -> None:
        self._model = model
        self._fallback = HashEmbedder()

    def embed(self, text: str) -> list[float]:
        try:
            return self._embed_cached(text)
        except Exception as exc:  # noqa: BLE001 — degrade to hash embedder
            _logger.warning("embedder.vertex_degrade", error=type(exc).__name__)
            return self._fallback.embed(text)

    @lru_cache(maxsize=256)  # noqa: B019 — per-instance-cache
    def _embed_cached(self, text: str) -> list[float]:  # type: ignore[misc]
        from stillopen_core.config import get_settings

        settings = get_settings()
        try:
            from google import genai
            from google.genai import types  # noqa: F401 — imports needed at runtime
        except ImportError as exc:
            raise RuntimeError("google-genai not installed") from exc
        client = genai.Client(
            vertexai=True,
            project=settings.gcp_project,
            location=settings.gcp_location,
        )
        response = client.models.embed_content(
            model=self._model,
            contents=text[:8000],
        )
        embeddings = getattr(response, "embeddings", None) or []
        if not embeddings:
            raise RuntimeError("Vertex returned no embeddings")
        values = getattr(embeddings[0], "values", None) or []
        return _l2([float(x) for x in values])


def build_embedder() -> Embedder:
    """Factory used by ``TabIndex`` when no embedder is passed."""

    if os.environ.get("PYTEST_CURRENT_TEST"):
        return HashEmbedder()
    from stillopen_core.config import get_settings

    settings = get_settings()
    if (
        settings.use_vertex_embeddings
        and settings.use_vertex
        and settings.gcp_project
    ):
        _logger.info("embedder.vertex", model="text-embedding-004")
        return VertexEmbedder()
    return HashEmbedder()


def cosine(a: list[float], b: list[float]) -> float:
    # zip(strict=True) enforces same-dim vectors so a Vertex/Hash mix fails loudly.
    return sum(x * y for x, y in zip(a, b, strict=True))


def _l2(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


class TabIndex:
    """In-memory index of tab vectors. Same interface for hash & Vertex embedders."""

    def __init__(self, embedder: Embedder | None = None) -> None:
        self._embedder = embedder or build_embedder()
        self._rows: list[tuple[int, list[float]]] = []

    def index_text(self, tab_id: int, text: str) -> None:
        self._rows.append((tab_id, self._embedder.embed(text)))

    def query(self, text: str, *, k: int = 12) -> list[tuple[int, float]]:
        q = self._embedder.embed(text)
        scored = [(tab_id, cosine(q, vec)) for tab_id, vec in self._rows]
        scored.sort(key=lambda row: row[1], reverse=True)
        return scored[:k]


__all__ = [
    "Embedder",
    "HashEmbedder",
    "TabIndex",
    "VertexEmbedder",
    "build_embedder",
    "cosine",
]
