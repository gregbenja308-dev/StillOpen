import os

from stillopen_core.config import get_settings
from stillopen_core.gateway.gemini import apply_gemini_backend


def test_has_gemini_via_vertex(monkeypatch) -> None:
    monkeypatch.setenv("GOOGLE_API_KEY", "")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "project-aa463019-e29a-4fa8-b4c")
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "true")
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.has_gemini
    assert settings.use_vertex
    assert settings.gcp_project == "project-aa463019-e29a-4fa8-b4c"
    apply_gemini_backend()
    assert os.environ["GOOGLE_GENAI_USE_VERTEXAI"] == "true"
    assert os.environ["GOOGLE_CLOUD_PROJECT"] == "project-aa463019-e29a-4fa8-b4c"
    assert os.environ["GOOGLE_CLOUD_LOCATION"] == "global"
    assert settings.gcp_location == "global"


def test_get_google_defaults_to_filing_store() -> None:
    from stillopen_core.google.factory import get_google
    from stillopen_core.google.filings import FilingStore

    assert isinstance(get_google("local-dev"), FilingStore)


def test_get_google_falls_back_to_fake_on_flag(monkeypatch) -> None:
    from stillopen_core.google.factory import get_google
    from stillopen_core.google.workspace import FakeGoogle

    monkeypatch.setenv("STILLOPEN_USE_FAKE_GOOGLE", "1")
    assert isinstance(get_google("local-dev"), FakeGoogle)
