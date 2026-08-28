"""Gemma is a second Google AI model wired for task labelling. Vertex
text-embedding-004 is the production embedder. Both are opt-in via env
vars; the defaults keep tests deterministic and offline."""

from __future__ import annotations

import pytest
from stillopen_core.config import get_settings
from stillopen_core.gateway.gemma import is_available, suggest_task_label
from stillopen_core.memory.embeddings import HashEmbedder, TabIndex, build_embedder


def test_gemma_is_off_without_config() -> None:
    assert is_available() is False


def test_gemma_off_returns_fallback_label() -> None:
    assert suggest_task_label(hosts=["nytimes.com"], titles=["news"], fallback="Read") == "Read"


def test_gemma_enabled_flag_requires_vertex(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STILLOPEN_GEMMA_MODEL", "gemma-2-9b-it")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "demo-project")
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "true")
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.has_gemma is True
    assert settings.gemma_model == "gemma-2-9b-it"


def test_build_embedder_defaults_to_hash() -> None:
    embedder = build_embedder()
    assert isinstance(embedder, HashEmbedder)


def test_tab_index_uses_hash_embedder_when_vertex_flag_missing() -> None:
    index = TabIndex()
    index.index_text(1, "zillow austin house 3 bed")
    index.index_text(2, "cnn breaking news")
    hits = index.query("austin house", k=2)
    assert hits[0][0] == 1


def test_use_vertex_embeddings_setting_flips(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STILLOPEN_USE_VERTEX_EMBEDDINGS", "true")
    get_settings.cache_clear()
    assert get_settings().use_vertex_embeddings is True
