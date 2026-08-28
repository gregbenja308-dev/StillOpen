"""``/v1/tasks/finish`` derives its file decision from the Framer's
intentions on the sanitized tabs, not from the caller's self-report.

A client can still pass ``file_to_google`` explicitly as an override, but a
hostile caller can't spoof ``intention: "comparing"`` to force a filing on a
1-tab dictionary lookup, and can't spoof ``intention: "unknown"`` to skip
filing on a 3-tab comparison.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from stillopen_api.main import create_app
from stillopen_core.schemas.tab import TabSnapshot


def _dict_lookup(seeded: list[TabSnapshot]) -> TabSnapshot:
    return next(t for t in seeded if "google.com/search" in t.url)


def test_client_intent_lie_cannot_force_filing_on_lookup(
    seeded_tabs: list[TabSnapshot],
) -> None:
    """Even if the client says intention=comparing, a 1-tab search stays ephemeral."""

    client = TestClient(create_app())
    lookup = _dict_lookup(seeded_tabs)
    res = client.post(
        "/v1/tasks/finish",
        json={
            "user_id": "local-dev",
            "task_id": "task-lie-1",
            "label": "look up ephemeral",
            "notes": "",
            "tabs": [lookup.model_dump(mode="json")],
            "intention": "comparing",  # lie: this is a dictionary lookup
            "kind": "durable",  # lie
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["clerk"] == "skipped"
    assert body["filing_urls"] == []


def test_comparison_gets_filed_even_if_client_says_unknown(
    seeded_tabs: list[TabSnapshot],
) -> None:
    """Multiple Zillow/Redfin tabs → Framer sees COMPARING → we file, no matter
    what the client claims."""

    client = TestClient(create_app())
    house = [t for t in seeded_tabs if "zillow" in t.url or "redfin" in t.url]
    assert len(house) >= 2, "fixture must have at least 2 house-listing tabs"
    res = client.post(
        "/v1/tasks/finish",
        json={
            "user_id": "local-dev",
            "task_id": "task-lie-2",
            "label": "House shortlist",
            "notes": "",
            "tabs": [t.model_dump(mode="json") for t in house],
            "intention": "unknown",  # lie: this is a comparison
            "kind": "ephemeral",  # lie
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["filing_urls"], "server should have filed based on server-derived intent"
    assert body["clerk"] != "skipped"


def test_explicit_file_override_wins(seeded_tabs: list[TabSnapshot]) -> None:
    """The one thing the client CAN still control is an explicit file_to_google flag."""

    client = TestClient(create_app())
    lookup = _dict_lookup(seeded_tabs)
    res = client.post(
        "/v1/tasks/finish",
        json={
            "user_id": "local-dev",
            "task_id": "task-override",
            "label": "look up ephemeral",
            "notes": "",
            "tabs": [lookup.model_dump(mode="json")],
            "intention": "unknown",
            "kind": "ephemeral",
            "file_to_google": True,  # explicit user opt-in
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["filing_urls"]  # override forced the filing
