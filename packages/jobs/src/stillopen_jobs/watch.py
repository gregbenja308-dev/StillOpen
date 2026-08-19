"""Watch job entrypoint (Cloud Scheduler → Cloud Run)."""

from __future__ import annotations

import os

from stillopen_core.watch.fetch import fetch_forbidden, hash_only_fetch
from stillopen_core.watch.tick import tick


def main() -> None:
    live = (
        os.environ.get("STILLOPEN_ENV") == "cloud"
        or os.environ.get("STILLOPEN_WATCH_FETCH") == "1"
    )
    fetcher = hash_only_fetch if live else fetch_forbidden
    acted = tick(fetcher=fetcher)
    print(f"stillopen-jobs watch: acted={len(acted)}")


if __name__ == "__main__":
    main()
