"""P0/P1 tests: /v1/tasks/finish routes closes through the ADK graph, and
the audit trail replays the multi-agent chain."""

from __future__ import annotations

from fastapi.testclient import TestClient
from stillopen_api.main import create_app
from stillopen_core.memory.fakes import get_bank
from stillopen_core.schemas.tab import TabSnapshot


def _fixture_ids(seeded_tabs: list[TabSnapshot], hosts: set[str]) -> list[int]:
    return [t.tab_id for t in seeded_tabs if any(h in t.url for h in hosts)]


def test_finish_task_files_then_closes(seeded_tabs: list[TabSnapshot]) -> None:
    client = TestClient(create_app())
    # A "Find a place in Austin" task: three listing tabs + the search that started it.
    payload = {
        "user_id": "local-dev",
        "task_id": "task-house",
        "label": "Find a place in Austin",
        "notes": "3 bed, under $3200, walkable to trailhead.",
        "tabs": [t.model_dump(mode="json") for t in seeded_tabs],
        "intention": "comparing",
        "kind": "durable",
    }
    res = client.post("/v1/tasks/finish", json=payload)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["report"]["artifacts_ok"] is True
    assert body["apply"]["close_tab_ids"]
    assert body["filing_urls"]
    assert body["audit_url"].startswith("/v1/plans/")

    # Notes must survive Clerk verbatim in the DOC body.
    filing_url = body["filing_urls"][0]
    filing_id = filing_url.rsplit("/", 1)[-1]
    filing = client.get(f"/v1/filings/{filing_id}?format=json").json()
    assert "3 bed, under $3200" in filing["body"]

    # Audit trail contains the reasoning chain.
    audit = client.get(body["audit_url"]).json()
    phases = [row["phase"] for row in audit["events"]]
    assert "proposed" in phases
    assert "clerk_draft" in phases
    assert "runner_file" in phases
    assert "verifier_ok" in phases


def test_finish_task_ephemeral_skips_google_but_still_audits(
    seeded_tabs: list[TabSnapshot],
) -> None:
    """A single-tab lookup with no notes should not manufacture a Doc."""
    search = next(t for t in seeded_tabs if "google.com/search" in t.url)
    client = TestClient(create_app())
    res = client.post(
        "/v1/tasks/finish",
        json={
            "user_id": "local-dev",
            "task_id": "task-search",
            "label": "austin homes search",
            "notes": "",
            "tabs": [search.model_dump(mode="json")],
            "intention": "zombie",
            "kind": "ephemeral",
            "file_to_google": False,
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["clerk"] == "skipped"
    assert body["filing_urls"] == []
    assert body["report"]["artifacts_ok"] is True
    audit = client.get(body["audit_url"]).json()
    phases = [row["phase"] for row in audit["events"]]
    assert "close_applied" in phases


def test_finish_task_respects_never_close_hosts(seeded_tabs: list[TabSnapshot]) -> None:
    """Bank tabs stay open even if the extension somehow sends them."""
    chase = next(t for t in seeded_tabs if "chase.com" in t.url)
    client = TestClient(create_app())
    res = client.post(
        "/v1/tasks/finish",
        json={
            "user_id": "local-dev",
            "task_id": "task-chase",
            "label": "Chase online banking",
            "notes": "keep",
            "tabs": [chase.model_dump(mode="json")],
            "intention": "waiting",
            "kind": "protected",
            "file_to_google": False,
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert chase.tab_id not in body["apply"]["close_tab_ids"]


def test_still_going_enrolls_watches() -> None:
    client = TestClient(create_app())
    res = client.post(
        "/v1/tasks/still-going",
        json={
            "user_id": "local-dev",
            "task_id": "task-order",
            "label": "Track UPS delivery",
            "urls": ["https://www.ups.com/track/12345"],
        },
    )
    assert res.status_code == 200, res.text
    assert res.json()["enrolled"] == 1
    assert get_bank().watches


def test_agents_registry_matches_run_graph() -> None:
    client = TestClient(create_app())
    res = client.get("/v1/agents/registry")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["graph"] == "clerk>runner>verifier"
    agents = {row["name"]: row for row in body["agents"]}
    assert set(agents) == {"clerk", "runner", "verifier"}
    assert agents["clerk"]["tools"] == []
    assert "create_doc" in agents["runner"]["tools"]
    assert "write_undo" in agents["verifier"]["tools"]
    assert agents["clerk"]["kind"] == "llm"


def test_filings_view_renders_html(seeded_tabs: list[TabSnapshot]) -> None:
    client = TestClient(create_app())
    res = client.post(
        "/v1/tasks/finish",
        json={
            "user_id": "local-dev",
            "task_id": "task-listings",
            "label": "House shortlist",
            "notes": "Zillow #12 looks strongest.",
            "tabs": [
                t.model_dump(mode="json")
                for t in seeded_tabs
                if "zillow" in t.url or "redfin" in t.url
            ],
            "intention": "comparing",
            "kind": "durable",
        },
    )
    assert res.status_code == 200, res.text
    filing_url = res.json()["filing_urls"][0]
    filing_id = filing_url.rsplit("/", 1)[-1]
    html = client.get(f"/v1/filings/{filing_id}").text
    assert "Still Open" in html
    assert "Zillow #12" in html


def test_audit_returns_404_for_unknown_plan() -> None:
    client = TestClient(create_app())
    res = client.get("/v1/plans/does-not-exist/audit")
    assert res.status_code == 404
