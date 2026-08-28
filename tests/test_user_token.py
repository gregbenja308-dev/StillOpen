"""Per-user bearer token for write endpoints (P3)."""

from __future__ import annotations

from fastapi.testclient import TestClient
from stillopen_api.main import create_app
from stillopen_core.config import get_settings
from stillopen_core.memory.fakes import get_bank, reset_bank
from stillopen_core.schemas.tab import TabSnapshot
from stillopen_core.security.user_token import issue_token, verify_token


def _make_payload(seeded_tabs: list[TabSnapshot]) -> dict[str, object]:
    return {
        "user_id": "user-a",
        "task_id": "task-A",
        "label": "House shortlist",
        "notes": "keep me",
        "tabs": [
            t.model_dump(mode="json")
            for t in seeded_tabs
            if "zillow" in t.url or "redfin" in t.url
        ],
        "intention": "comparing",
        "kind": "durable",
    }


def test_register_returns_a_token_and_persists_hash() -> None:
    reset_bank()
    client = TestClient(create_app())
    res = client.post("/v1/auth/register", json={"user_id": "user-a"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["user_id"] == "user-a"
    token = body["token"]
    assert len(token) == 64  # 32 bytes hex
    # The bank stores the hash, not the plaintext.
    stored = get_bank().get_token("user-a") or ""
    assert stored.startswith("user_token:")
    assert token not in stored
    assert verify_token(get_bank(), "user-a", token)
    assert not verify_token(get_bank(), "user-a", "wrong")


def test_finish_rejects_bad_token_when_enforcement_on(
    monkeypatch, seeded_tabs: list[TabSnapshot]
) -> None:
    reset_bank()
    monkeypatch.setenv("STILLOPEN_REQUIRE_USER_TOKEN", "1")
    get_settings.cache_clear()
    try:
        client = TestClient(create_app())
        # No token at all → 401.
        res = client.post("/v1/tasks/finish", json=_make_payload(seeded_tabs))
        assert res.status_code == 401

        # Right token → 200.
        reg = client.post("/v1/auth/register", json={"user_id": "user-a"}).json()
        ok = client.post(
            "/v1/tasks/finish",
            headers={"X-Stillopen-User-Token": reg["token"]},
            json=_make_payload(seeded_tabs),
        )
        assert ok.status_code == 200, ok.text

        # Token bound to a different user → 401.
        other = client.post("/v1/auth/register", json={"user_id": "user-b"}).json()
        bad = client.post(
            "/v1/tasks/finish",
            headers={"X-Stillopen-User-Token": other["token"]},
            json=_make_payload(seeded_tabs),
        )
        assert bad.status_code == 401
    finally:
        monkeypatch.delenv("STILLOPEN_REQUIRE_USER_TOKEN", raising=False)
        get_settings.cache_clear()


def test_finish_still_open_when_enforcement_off(seeded_tabs: list[TabSnapshot]) -> None:
    """Default posture: no token required, so existing installs aren't locked out."""

    reset_bank()
    client = TestClient(create_app())
    res = client.post("/v1/tasks/finish", json=_make_payload(seeded_tabs))
    assert res.status_code == 200, res.text


def test_still_going_enforces_token(monkeypatch) -> None:
    reset_bank()
    monkeypatch.setenv("STILLOPEN_REQUIRE_USER_TOKEN", "1")
    get_settings.cache_clear()
    try:
        client = TestClient(create_app())
        base = {
            "user_id": "user-a",
            "task_id": "task-Z",
            "label": "Track order",
            "urls": ["https://www.ups.com/track/1"],
        }
        assert client.post("/v1/tasks/still-going", json=base).status_code == 401
        reg = client.post("/v1/auth/register", json={"user_id": "user-a"}).json()
        ok = client.post(
            "/v1/tasks/still-going",
            headers={"X-Stillopen-User-Token": reg["token"]},
            json=base,
        )
        assert ok.status_code == 200
    finally:
        monkeypatch.delenv("STILLOPEN_REQUIRE_USER_TOKEN", raising=False)
        get_settings.cache_clear()


def test_issue_token_helper_generates_fresh_token() -> None:
    reset_bank()
    a = issue_token(get_bank(), "user-a")
    b = issue_token(get_bank(), "user-a")
    assert a != b
    assert not verify_token(get_bank(), "user-a", a)
    assert verify_token(get_bank(), "user-a", b)
