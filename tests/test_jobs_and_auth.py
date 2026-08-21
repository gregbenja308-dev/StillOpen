from fastapi.testclient import TestClient
from stillopen_api.main import create_app
from stillopen_core.config import get_settings


def test_watch_job_refuses_network_locally() -> None:
    client = TestClient(create_app())
    res = client.post("/v1/jobs/watch")
    assert res.status_code == 200
    body = res.json()
    assert body["fetcher"] == "forbidden"
    assert body["acted"] == 0


def test_watch_job_requires_token_in_cloud(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("STILLOPEN_ENV", "cloud")
    monkeypatch.setenv("STILLOPEN_JOB_TOKEN", "")
    get_settings.cache_clear()
    client = TestClient(create_app())
    res = client.post("/v1/jobs/watch")
    assert res.status_code == 503
    get_settings.cache_clear()


def test_watch_job_rejects_bad_token_in_cloud(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("STILLOPEN_ENV", "cloud")
    monkeypatch.setenv("STILLOPEN_JOB_TOKEN", "test-job-token")
    get_settings.cache_clear()
    client = TestClient(create_app())
    bad = client.post("/v1/jobs/watch", headers={"X-Stillopen-Job-Token": "wrong"})
    assert bad.status_code == 401
    res = client.post("/v1/jobs/watch", headers={"X-Stillopen-Job-Token": "test-job-token"})
    assert res.status_code == 200
    get_settings.cache_clear()
