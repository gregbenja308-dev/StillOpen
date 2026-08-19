from fastapi.testclient import TestClient
from stillopen_api.main import create_app
from stillopen_core.schemas.tab import TabSnapshot


def test_healthz() -> None:
    client = TestClient(create_app())
    res = client.get("/healthz")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"
    assert res.json()["run_graph"] == "clerk>runner>verifier"


def test_create_plan_from_fixture(seeded_tabs: list[TabSnapshot]) -> None:
    client = TestClient(create_app())
    payload = {
        "user_id": "local-dev",
        "command": "close the tabs about buying a house austin",
        "tabs": [t.model_dump(mode="json") for t in seeded_tabs],
    }
    res = client.post("/v1/plans", json=payload)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "proposed"
    assert body["cards"]
    chase = next(t for t in seeded_tabs if t.tab_id == 16)
    dumped = res.text
    assert "super-secret" not in dumped
    assert chase.extract not in dumped


def test_run_plan_returns_close_list(seeded_tabs: list[TabSnapshot]) -> None:
    client = TestClient(create_app())
    created = client.post(
        "/v1/plans",
        json={
            "user_id": "local-dev",
            "command": "close the tabs about buying a house austin",
            "tabs": [t.model_dump(mode="json") for t in seeded_tabs],
        },
    )
    assert created.status_code == 200, created.text
    plan_id = created.json()["plan_id"]
    ran = client.post(f"/v1/plans/{plan_id}/run", json={"overrides": []})
    assert ran.status_code == 200, ran.text
    body = ran.json()
    assert body["report"]["artifacts_ok"] is True
    assert "close_tab_ids" in body["apply"]
    assert body["artifacts"]


def test_memory_chat_and_inspect() -> None:
    client = TestClient(create_app())
    chat = client.post(
        "/v1/memory/chat",
        json={
            "user_id": "local-dev",
            "message": "I want to delete tabs that I haven't used in a week",
        },
    )
    assert chat.status_code == 200, chat.text
    body = chat.json()
    assert body["profile"]["stale_cutoff_days"] == 7
    assert body["storage"]["backend"] == "local_json"
    assert body["profile"]["mutations"]

    observed = client.post(
        "/v1/memory/observe",
        json={
            "user_id": "local-dev",
            "kind": "stillopen_close",
            "host": "example.com",
            "title": "Example",
            "source": "stale",
        },
    )
    assert observed.status_code == 200, observed.text
    got = client.get("/v1/memory", params={"user_id": "local-dev"})
    assert got.status_code == 200
    profile = got.json()["profile"]
    assert profile["stale_cutoff_days"] == 7
    hosts = {row["host_suffix"]: row for row in profile["hosts"]}
    assert hosts["example.com"]["stillopen_closed"] == 1


def test_memory_chat_lists_news_tabs(seeded_tabs: list[TabSnapshot]) -> None:
    client = TestClient(create_app())
    res = client.post(
        "/v1/memory/chat",
        json={
            "user_id": "local-dev",
            "message": "Delete any news tabs",
            "tabs": [t.model_dump(mode="json") for t in seeded_tabs],
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["wants_close"] is True
    assert body["matches"]
    assert any(row["host"] == "nytimes.com" for row in body["matches"])
    assert "stale" not in body["reply"].lower()
