"""Safe, single-host RSS preflight refresh for a persistent EnergyBrew volume.

Keeps publisher-dated research current before the 05:45 preview and 06:30
cutoff. Research metadata only; no article content, publishing, or email.
The existing morning-runner flock prevents simultaneous RSS writers.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from morning_host_runner import refresh_rss_safely
from public_collector_guard import ensure_sources_public


def run_refresh(root, *, now=None, fetcher=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Host RSS refresh requires a timezone-aware clock")
    ensure_sources_public()
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    with (root / "morning-runner.lock").open("a+", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("RSS refresh and morning research cannot run concurrently") from exc
        summary = refresh_rss_safely(
            root / "articles.json", root / "output" / "rss-preflight",
            now=now.astimezone(timezone.utc), fetcher=fetcher,
        )
    return {
        "run_utc": now.astimezone(timezone.utc).isoformat(),
        "status": summary.get("scan_state", "unknown"),
        "feeds_checked": summary.get("feeds_checked", 0),
        "feeds_connected": summary.get("feeds_connected", 0),
        "new_article_links": summary.get("new_article_links", 0),
        "publication": "research_only_no_email_no_automatic_approval",
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path,
                        default=Path(os.environ.get("ENERGYBREW_STATE_ROOT", "/data")))
    options = parser.parse_args(argv)
    outcome = run_refresh(options.root)
    print(json.dumps(outcome, indent=2))
    return 0 if outcome["status"] != "critical" else 2


if __name__ == "__main__":
    raise SystemExit(main())
