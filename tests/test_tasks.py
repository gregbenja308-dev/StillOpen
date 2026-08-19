from fastapi.testclient import TestClient
from stillopen_api.main import create_app
from stillopen_core.memory.tasks import infer_tasks
from stillopen_core.schemas.tab import TabSnapshot
from stillopen_core.schemas.task import TaskKind


def test_listings_and_search_are_one_named_task(seeded_tabs: list[TabSnapshot]) -> None:
    tasks = infer_tasks(seeded_tabs)
    durable = [t for t in tasks if t.kind is TaskKind.DURABLE]
    assert durable
    house = next(t for t in durable if {11, 12, 13}.issubset(set(t.tab_ids)))
    assert 14 in house.tab_ids
    label = house.label.lower()
    assert "place" in label or "listing" in label or "austin" in label
    assert 16 not in house.tab_ids
    assert 17 not in house.tab_ids


def test_chase_is_protected_and_not_in_durable(seeded_tabs: list[TabSnapshot]) -> None:
    tasks = infer_tasks(seeded_tabs)
    protected = [t for t in tasks if t.kind is TaskKind.PROTECTED]
    assert protected
    assert any(16 in t.tab_ids for t in protected)
    for task in tasks:
        if task.kind is not TaskKind.PROTECTED:
            assert 16 not in task.tab_ids


def test_chrome_group_name_wins(seeded_tabs: list[TabSnapshot]) -> None:
    house = [t for t in seeded_tabs if t.tab_id in {11, 12, 13}]
    for tab in house:
        tab.group_id = 7
        tab.group_title = "Austin rentals"
    tasks = infer_tasks(house)
    assert any(t.label == "Austin rentals" and t.kind is TaskKind.DURABLE for t in tasks)


def test_tasks_api(seeded_tabs: list[TabSnapshot]) -> None:
    client = TestClient(create_app())
    res = client.post(
        "/v1/tasks",
        json={
            "user_id": "local-dev",
            "tabs": [t.model_dump(mode="json") for t in seeded_tabs],
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["tasks"]
    kinds = {row["kind"] for row in body["tasks"]}
    assert "durable" in kinds
    assert "protected" in kinds
