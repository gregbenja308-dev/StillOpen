from stillopen_core.heuristics.close import close_hint, duplicate_ids, infer_intention
from stillopen_core.schemas.tab import CloseHint, HostClass, Intention, SanitizedTab


def _tab(**kwargs: object) -> SanitizedTab:
    base: dict[str, object] = {
        "tab_id": 1,
        "window_id": 1,
        "index": 0,
        "url": "https://www.zillow.com/home/1",
        "title": "Home",
        "host": "www.zillow.com",
        "host_class": HostClass.LISTING,
        "pinned": False,
        "audible": False,
        "discarded": False,
        "active": False,
        "group_id": -1,
        "last_accessed_ms": 1,
        "extract": None,
        "redacted": False,
        "blocked_from_model": False,
    }
    base.update(kwargs)
    return SanitizedTab.model_validate(base)


def test_two_listings_are_comparing() -> None:
    tab = _tab()
    assert infer_intention(tab, sibling_count_same_host=3) is Intention.COMPARING


def test_chase_never_closes() -> None:
    tab = _tab(
        url="https://secure.chase.com/dashboard",
        host="secure.chase.com",
        host_class=HostClass.MONEY,
        blocked_from_model=True,
    )
    hint, _reason = close_hint(tab, intention=Intention.REFERENCE, is_duplicate=False)
    assert hint is CloseHint.NEVER


def test_duplicate_keeps_newest() -> None:
    a = _tab(tab_id=1, last_accessed_ms=10, url="https://zillow.com/x")
    b = _tab(tab_id=2, last_accessed_ms=20, url="https://www.zillow.com/x/")
    assert duplicate_ids([a, b]) == {1}
