from stillopen_core.schemas.tab import HostClass, TabSnapshot
from stillopen_core.surveyor.sanitize import sanitize_tabs


def test_surveyor_drops_bank_extract_and_redacts_token() -> None:
    tabs = [
        TabSnapshot(
            tab_id=1,
            window_id=1,
            index=0,
            url="https://secure.chase.com/web/auth/dashboard?token=super-secret",
            title="Chase",
            extract="routing 021000021 account 123456789",
        )
    ]
    out = sanitize_tabs(tabs)
    assert len(out) == 1
    tab = out[0]
    assert tab.host_class is HostClass.MONEY
    assert tab.blocked_from_model
    assert tab.extract is None
    assert "super-secret" not in tab.url
    assert tab.redacted
