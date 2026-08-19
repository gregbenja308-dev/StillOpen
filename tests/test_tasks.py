import pytest
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
    assert house.label.lower() != "housing"
    assert 16 not in house.tab_ids
    assert 17 not in house.tab_ids


def test_laptop_and_housing_listings_stay_separate() -> None:
    tabs = [
        TabSnapshot(
            tab_id=1,
            window_id=1,
            index=0,
            url="https://www.zillow.com/austin-tx/",
            title="Austin TX Real Estate",
            pinned=False,
            audible=False,
            discarded=False,
            active=False,
            group_id=-1,
            last_accessed_ms=1,
            extract=None,
        ),
        TabSnapshot(
            tab_id=2,
            window_id=1,
            index=1,
            url="https://www.redfin.com/city/30818/TX/Austin",
            title="Austin Homes for Sale",
            pinned=False,
            audible=False,
            discarded=False,
            active=False,
            group_id=-1,
            last_accessed_ms=1,
            extract=None,
        ),
        TabSnapshot(
            tab_id=3,
            window_id=1,
            index=2,
            url="https://www.amazon.com/s?k=macbook+air",
            title="MacBook Air",
            pinned=False,
            audible=False,
            discarded=False,
            active=False,
            group_id=-1,
            last_accessed_ms=1,
            extract=None,
        ),
        TabSnapshot(
            tab_id=4,
            window_id=1,
            index=3,
            url="https://www.apple.com/macbook-air/",
            title="MacBook Air - Apple",
            pinned=False,
            audible=False,
            discarded=False,
            active=True,
            group_id=-1,
            last_accessed_ms=1,
            extract=None,
        ),
    ]
    tasks = infer_tasks(tabs)
    house = next(t for t in tasks if 1 in t.tab_ids)
    laptops = next(t for t in tasks if 3 in t.tab_ids)
    assert house.task_id != laptops.task_id
    assert 3 not in house.tab_ids
    assert 1 not in laptops.tab_ids
    assert 4 in laptops.tab_ids


def test_chase_is_protected_and_not_in_durable(seeded_tabs: list[TabSnapshot]) -> None:
    tasks = infer_tasks(seeded_tabs)
    protected = [t for t in tasks if t.kind is TaskKind.PROTECTED]
    assert protected
    assert any(16 in t.tab_ids for t in protected)
    for task in tasks:
        if task.kind is not TaskKind.PROTECTED:
            assert 16 not in task.tab_ids


def test_chrome_groups_are_not_task_boundaries(seeded_tabs: list[TabSnapshot]) -> None:
    for tab in seeded_tabs:
        if tab.tab_id in {11, 12, 13, 15}:
            tab.group_id = 7
            tab.group_title = "Housing"
    tasks = infer_tasks(seeded_tabs)
    house = next(t for t in tasks if {11, 12, 13}.issubset(set(t.tab_ids)))
    assert house.label.lower() != "housing"
    assert 15 not in house.tab_ids
    assert 14 in house.tab_ids


def test_model_owns_task_membership(
    monkeypatch: pytest.MonkeyPatch, seeded_tabs: list[TabSnapshot]
) -> None:
    monkeypatch.setattr(
        "stillopen_core.memory.tasks._ask_gemini",
        lambda _prompt: {
            "tasks": [
                {"label": "Find a rental in Austin", "tab_ids": [11, 12, 13, 14]},
                {"label": "Read the housing explainer", "tab_ids": [15]},
                {"label": "Compare these laptops", "tab_ids": [17]},
            ]
        },
    )
    tasks = infer_tasks(seeded_tabs)
    owner = {tid: task for task in tasks for tid in task.tab_ids}
    assert owner[11].label == "Find a rental in Austin"
    assert {11, 12, 13, 14}.issubset(set(owner[11].tab_ids))
    assert owner[15].label == "Read the housing explainer"
    assert owner[15].task_id != owner[11].task_id
    assert owner[17].label == "Compare these laptops"
    assert 16 not in owner[11].tab_ids
    assert next(t for t in tasks if t.kind is TaskKind.PROTECTED).tab_ids == [16]


def test_rescan_keeps_user_label_and_drops_closed_tabs(
    seeded_tabs: list[TabSnapshot],
) -> None:
    first = infer_tasks(seeded_tabs)
    house = next(t for t in first if {11, 12, 13}.issubset(set(t.tab_ids)))
    house.user_locked = True
    house.label = "Austin rentals"
    live = [t for t in seeded_tabs if t.tab_id != 13]
    again = infer_tasks(live, existing=[house])
    kept = next(t for t in again if t.task_id == house.task_id)
    assert kept.label == "Austin rentals"
    assert 13 not in kept.tab_ids
    assert 11 in kept.tab_ids


def test_new_tab_attaches_to_existing_named_task(seeded_tabs: list[TabSnapshot]) -> None:
    house_tabs = [t for t in seeded_tabs if t.tab_id in {11, 12}]
    seed = infer_tasks(house_tabs)
    house = next(t for t in seed if {11, 12}.issubset(set(t.tab_ids)))
    house.user_locked = True
    house.label = "Find a place in Austin"
    extra = next(t for t in seeded_tabs if t.tab_id == 14)
    merged = infer_tasks([*house_tabs, extra], existing=[house])
    kept = next(t for t in merged if t.task_id == house.task_id)
    assert 14 in kept.tab_ids
    assert kept.label == "Find a place in Austin"


def test_ignored_url_is_not_auto_grouped(seeded_tabs: list[TabSnapshot]) -> None:
    nyt = next(t for t in seeded_tabs if t.tab_id == 15)
    tasks = infer_tasks(seeded_tabs, ignored_urls=[nyt.url])
    for task in tasks:
        assert 15 not in task.tab_ids


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


def _snap(tab_id: int, url: str, title: str) -> TabSnapshot:
    return TabSnapshot(
        tab_id=tab_id,
        window_id=1,
        index=tab_id,
        url=url,
        title=title,
        pinned=False,
        audible=False,
        discarded=False,
        active=False,
        group_id=-1,
        last_accessed_ms=1,
        extract=None,
    )


def test_demo_window_makes_several_named_tasks() -> None:
    tabs = [
        _snap(1, "https://www.zillow.com/austin-tx/", "Zillow Austin"),
        _snap(2, "https://www.redfin.com/city/30818/TX/Austin", "Redfin Austin"),
        _snap(3, "https://www.zillow.com/homes/Austin-TX_rb/", "Zillow listings"),
        _snap(4, "https://www.google.com/search?q=austin+homes+3+bedroom", "Google: austin homes"),
        _snap(5, "https://www.nytimes.com/section/realestate", "NYT real estate"),
        _snap(6, "https://www.chase.com/", "Chase"),
        _snap(7, "https://www.realtor.com/realestateandhomes-search/Austin_TX", "Realtor Austin"),
        _snap(8, "https://www.apartments.com/austin-tx/", "Apartments.com Austin"),
        _snap(9, "https://austin.craigslist.org/search/apa", "Craigslist Austin apts"),
        _snap(10, "https://www.merriam-webster.com/dictionary/ephemeral", "Dictionary: ephemeral"),
        _snap(11, "https://en.wikipedia.org/wiki/Ephemeral", "Wikipedia: Ephemeral"),
        _snap(12, "https://www.google.com/search?q=what+does+ephemeral+mean", "Google: ephemeral"),
        _snap(13, "https://www.amazon.com/s?k=macbook+air", "Amazon: MacBook Air"),
        _snap(
            14,
            "https://www.bestbuy.com/site/searchpage.jsp?st=macbook+air",
            "Best Buy: MacBook Air",
        ),
        _snap(15, "https://www.apple.com/macbook-air/", "Apple MacBook Air"),
        _snap(16, "https://www.ups.com/track?loc=en_US", "UPS tracking"),
        _snap(17, "https://www.bbc.com/news", "BBC News"),
        _snap(18, "https://github.com/google/adk-python", "GitHub: google/adk-python"),
        _snap(19, "https://www.reddit.com/r/AustinApartments/", "Reddit: AustinApartments"),
        _snap(20, "https://stackoverflow.com/questions/tagged/python", "Stack Overflow: python"),
        _snap(21, "https://www.nytimes.com/section/technology", "NYT technology"),
    ]
    tasks = infer_tasks(tabs)
    owner = {tid: task for task in tasks for tid in task.tab_ids}
    house = owner[1]
    assert {1, 2, 3, 4, 7, 8, 9, 19}.issubset(set(house.tab_ids))
    laptops = owner[13]
    assert laptops.task_id != house.task_id
    assert {13, 14, 15}.issubset(set(laptops.tab_ids))
    assert 1 not in laptops.tab_ids
    lookup = owner[10]
    assert lookup.task_id != house.task_id
    assert {10, 11, 12}.issubset(set(lookup.tab_ids))
    assert "ephemeral" in lookup.label.lower()
    assert lookup.label.lower() not in {"ephemeral", "ephemerality"}
    assert owner[17].label.lower() != "bbc news"
    protected = next(t for t in tasks if t.kind is TaskKind.PROTECTED)
    assert 6 in protected.tab_ids
    assert 16 not in house.tab_ids
    assert len(tasks) >= 4


def test_tasks_api_accepts_chrome_noise(seeded_tabs: list[TabSnapshot]) -> None:
    client = TestClient(create_app())
    noisy = []
    for tab in seeded_tabs:
        row = tab.model_dump(mode="json")
        row["last_accessed_ms"] = 1_712_000_000_000.7
        row["favIconUrl"] = "https://example/icon.png"
        noisy.append(row)
    res = client.post(
        "/v1/tasks",
        json={
            "user_id": "local-dev",
            "tabs": noisy,
            "existing": [
                {
                    "task_id": "userlockedtask0000000001",
                    "label": "Keep this name",
                    "tab_ids": [],
                    "kind": "ephemeral",
                    "user_locked": True,
                    "bogus": True,
                }
            ],
        },
    )
    assert res.status_code == 200, res.text


def test_inflected_lookup_tabs_are_one_named_task() -> None:
    tabs = [
        _snap(1, "https://www.merriam-webster.com/dictionary/ephemeral", "ephemeral - Definition"),
        _snap(2, "https://en.wikipedia.org/wiki/Ephemerality", "Ephemerality - Wikipedia"),
        _snap(3, "https://www.google.com/search?q=ephemeral+meaning", "ephemeral meaning - Google"),
        _snap(4, "https://www.bbc.com/news", "BBC News"),
    ]
    tasks = infer_tasks(tabs)
    owner = {tid: task for task in tasks for tid in task.tab_ids}
    lookup = owner[1]
    assert set(lookup.tab_ids) == {1, 2, 3}
    assert "ephemeral" in lookup.label.lower()
    assert lookup.label.lower() not in {
        "ephemeral",
        "ephemerality",
        "ephemerality wikipedia",
        "bbc news",
    }
    news = owner[4]
    assert news.task_id != lookup.task_id
    assert news.label.lower() != "bbc news"
    assert "news" in news.label.lower()


def test_model_page_titles_are_rewritten_as_tasks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tabs = [
        _snap(1, "https://www.merriam-webster.com/dictionary/ephemeral", "ephemeral"),
        _snap(2, "https://en.wikipedia.org/wiki/Ephemerality", "Ephemerality - Wikipedia"),
        _snap(3, "https://www.bbc.com/news", "BBC News"),
    ]
    monkeypatch.setattr(
        "stillopen_core.memory.tasks._ask_gemini",
        lambda _prompt: {
            "tasks": [
                {"label": "Ephemeral", "tab_ids": [1, 2]},
                {"label": "BBC News", "tab_ids": [3]},
            ]
        },
    )
    tasks = infer_tasks(tabs)
    owner = {tid: task for task in tasks for tid in task.tab_ids}
    assert set(owner[1].tab_ids) == {1, 2}
    assert owner[1].label.lower() != "ephemeral"
    assert "ephemeral" in owner[1].label.lower()
    assert owner[3].label.lower() != "bbc news"


def test_forum_tab_joins_the_same_city_job() -> None:
    tabs = [
        _snap(1, "https://www.zillow.com/austin-tx/", "Austin TX Real Estate"),
        _snap(2, "https://www.apartments.com/austin-tx/", "Austin Apartments"),
        _snap(3, "https://www.reddit.com/r/AustinApartments/", "r/AustinApartments"),
        _snap(4, "https://www.amazon.com/s?k=macbook+air", "MacBook Air"),
    ]
    tasks = infer_tasks(tabs)
    owner = {tid: task for task in tasks for tid in task.tab_ids}
    assert owner[3].task_id == owner[1].task_id
    assert owner[2].task_id == owner[1].task_id
    assert owner[4].task_id != owner[1].task_id


def test_model_omitted_forum_attaches_to_same_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tabs = [
        _snap(1, "https://www.zillow.com/austin-tx/", "Austin TX Real Estate"),
        _snap(2, "https://www.apartments.com/austin-tx/", "Austin Apartments"),
        _snap(3, "https://www.reddit.com/r/AustinApartments/", "r/AustinApartments"),
        _snap(4, "https://www.amazon.com/s?k=macbook+air", "MacBook Air"),
    ]
    monkeypatch.setattr(
        "stillopen_core.memory.tasks._ask_gemini",
        lambda _prompt: {
            "tasks": [
                {"label": "Compare these Austin options", "tab_ids": [1, 2]},
                {"label": "Compare MacBook Air prices", "tab_ids": [4]},
            ]
        },
    )
    tasks = infer_tasks(tabs)
    owner = {tid: task for task in tasks for tid in task.tab_ids}
    assert owner[3].task_id == owner[1].task_id
    assert owner[1].label == "Compare these Austin options"
    assert owner[4].task_id != owner[1].task_id


def test_garbage_search_blob_is_not_the_task_name() -> None:
    noise = "Egzjahjvbwuybggaeeuyotiicaeqabgwgb4Ycagc"
    tabs = [
        _snap(
            1,
            f"https://www.google.com/search?q={noise}&ei={noise}&ved=2ahUKEwjABC",
            f"{noise} - Google Search",
        ),
        _snap(2, "https://www.bbc.com/news", "BBC News"),
    ]
    tasks = infer_tasks(tabs)
    lookup = next(t for t in tasks if 1 in t.tab_ids)
    assert noise.lower() not in lookup.label.lower()
    assert "egzjahj" not in lookup.label.lower()
    assert lookup.label == "Look this up"


def test_model_garbage_label_is_rewritten(monkeypatch: pytest.MonkeyPatch) -> None:
    noise = "Egzjahjvbwuybggaeeuyotiicaeqabgwgb4Ycagc"
    tabs = [
        _snap(1, f"https://www.google.com/search?q={noise}", f"{noise} - Google Search"),
    ]
    monkeypatch.setattr(
        "stillopen_core.memory.tasks._ask_gemini",
        lambda _prompt: {"tasks": [{"label": f"Look up {noise}", "tab_ids": [1]}]},
    )
    tasks = infer_tasks(tabs)
    assert tasks[0].label == "Look this up"
    assert noise.lower() not in tasks[0].label.lower()
