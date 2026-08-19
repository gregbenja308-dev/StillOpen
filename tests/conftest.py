"""Shared test helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from stillopen_core.config import get_settings
from stillopen_core.gateway.router import reset_gateway
from stillopen_core.memory.fakes import reset_bank
from stillopen_core.schemas.tab import TabSnapshot

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "seeded_window.json"


@pytest.fixture(autouse=True)
def _reset() -> None:
    get_settings.cache_clear()
    reset_bank()
    reset_gateway()
    yield
    get_settings.cache_clear()
    reset_bank()
    reset_gateway()


@pytest.fixture
def seeded_tabs() -> list[TabSnapshot]:
    raw = json.loads(FIXTURE.read_text())
    return [TabSnapshot.model_validate(row) for row in raw["tabs"]]
