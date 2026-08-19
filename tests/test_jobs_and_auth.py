from fastapi.testclient import TestClient
from stillopen_api.main import create_app
from stillopen_core.config import get_settings
from stillopen_core.google.tokens import load_token_blob, save_token_blob
from stillopen_core.security.crypto import generate_key


def test_watch_job_refuses_network_locally() -> None:
    client = TestClient(create_app())
    res = client.post("/v1/jobs/watch")
    assert res.status_code == 200
    body = res.json()
    assert body["fetcher"] == "forbidden"
    assert body["acted"] == 0


def test_auth_status_without_oauth() -> None:
    client = TestClient(create_app())
    res = client.get("/v1/auth/google/status", params={"user_id": "local-dev"})
    assert res.status_code == 200
    body = res.json()
    assert body["connected"] == "no"
    assert "drive.file" in body["scopes"]


def test_token_roundtrip(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    key = generate_key()
    monkeypatch.setenv("STILLOPEN_TOKEN_KEY", key)
    get_settings.cache_clear()
    save_token_blob("local-dev", {"refresh_token": "rt", "token": "at"})
    blob = load_token_blob("local-dev")
    assert blob is not None
    assert blob["refresh_token"] == "rt"
    get_settings.cache_clear()
