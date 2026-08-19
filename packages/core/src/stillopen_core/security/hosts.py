"""Host-class deny list. Deny-listed tabs never send extracts to the model."""

from __future__ import annotations

from stillopen_core.schemas.tab import HostClass

# Suffix match on hostname (lowercase, no port).
_CLASS_SUFFIXES: dict[HostClass, tuple[str, ...]] = {
    HostClass.MONEY: (
        "chase.com",
        "bankofamerica.com",
        "wellsfargo.com",
        "capitalone.com",
        "americanexpress.com",
        "paypal.com",
        "venmo.com",
        "stripe.com",
        "plaid.com",
        "coinbase.com",
        "fidelity.com",
        "vanguard.com",
        "schwab.com",
        "ally.com",
        "discover.com",
    ),
    HostClass.HEALTH: (
        "mychart.org",
        "epic.com",
        "kaiserpermanente.org",
        "cvshealth.com",
        "walgreens.com",
        "labcorp.com",
        "questdiagnostics.com",
        "teladoc.com",
    ),
    HostClass.GOV: (
        "irs.gov",
        "ssa.gov",
        "login.gov",
        "usa.gov",
        "state.gov",
        "uscis.gov",
        "va.gov",
        "dmv.ca.gov",
    ),
    HostClass.SCHOOL: (
        "instructure.com",
        "canvaslms.com",
        "powerschool.com",
        "schoology.com",
        "clever.com",
        "parentvue.com",
    ),
    HostClass.AUTH: (
        "accounts.google.com",
        "login.microsoftonline.com",
        "okta.com",
        "auth0.com",
        "id.apple.com",
    ),
    HostClass.SEARCH: ("google.com", "bing.com", "duckduckgo.com"),
    HostClass.NEWS: (
        "nytimes.com",
        "washingtonpost.com",
        "theguardian.com",
        "bbc.com",
        "cnn.com",
        "medium.com",
    ),
    HostClass.LISTING: (
        "zillow.com",
        "redfin.com",
        "realtor.com",
        "apartments.com",
        "amazon.com",
        "ebay.com",
        "craigslist.org",
    ),
    HostClass.DOCS: ("docs.google.com", "sheets.google.com", "drive.google.com"),
    HostClass.MAIL: ("mail.google.com", "outlook.live.com", "outlook.office.com"),
}

# Never send page body / never auto-close.
NEVER_MODEL_CLASSES = frozenset(
    {
        HostClass.MONEY,
        HostClass.HEALTH,
        HostClass.GOV,
        HostClass.SCHOOL,
        HostClass.AUTH,
    }
)

NEVER_CLOSE_CLASSES = NEVER_MODEL_CLASSES


def classify_host(host: str) -> HostClass:
    h = host.lower().removeprefix("www.")
    if not h:
        return HostClass.GENERIC
    # More specific classes first (money before generic .com).
    order = (
        HostClass.AUTH,
        HostClass.MONEY,
        HostClass.HEALTH,
        HostClass.GOV,
        HostClass.SCHOOL,
        HostClass.DOCS,
        HostClass.MAIL,
        HostClass.SEARCH,
        HostClass.LISTING,
        HostClass.NEWS,
    )
    for cls in order:
        for suffix in _CLASS_SUFFIXES[cls]:
            if h == suffix or h.endswith("." + suffix):
                return cls
    return HostClass.GENERIC


def blocked_from_model(host_class: HostClass) -> bool:
    return host_class in NEVER_MODEL_CLASSES


__all__ = [
    "NEVER_CLOSE_CLASSES",
    "NEVER_MODEL_CLASSES",
    "blocked_from_model",
    "classify_host",
]
