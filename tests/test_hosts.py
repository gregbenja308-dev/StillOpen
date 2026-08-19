from stillopen_core.schemas.tab import HostClass
from stillopen_core.security.hosts import blocked_from_model, classify_host


def test_chase_is_money_and_blocked() -> None:
    cls = classify_host("secure.chase.com")
    assert cls is HostClass.MONEY
    assert blocked_from_model(cls)


def test_zillow_is_listing_and_allowed() -> None:
    cls = classify_host("www.zillow.com")
    assert cls is HostClass.LISTING
    assert not blocked_from_model(cls)


def test_accounts_google_is_auth() -> None:
    assert classify_host("accounts.google.com") is HostClass.AUTH
