"""Crash-safe, public-metadata-only issuer-announcement refresh for one host.

Company/newswire announcements are unverified leads, not independent reporting.
Never publish them or treat the aggregator timestamp as publisher confirmation.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from press_releases import collect
from public_collector_guard import ensure_sources_public, validate_records


def run_refresh(root, *, now=None, fetcher=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Issuer refresh requires a timezone-aware clock")
    ensure_sources_public()
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    state = root / "press_releases.json"
    staging = root / "press_releases.host-stage.json"
    with (root / "press-release-runner.lock").open("a+", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("Another issuer release refresh is active") from exc
        if staging.exists():
            raise RuntimeError("Uncommitted issuer stage requires inspection")
        if state.exists():
            shutil.copyfile(state, staging)
        try:
            report = collect(staging, root / "output" / "company-releases",
                             now=now.astimezone(timezone.utc), fetcher=fetcher)
            validate_records(staging, "leads")
            staging.replace(state)
        finally:
            if staging.exists():
                staging.unlink()
    return {
        "run_utc": now.astimezone(timezone.utc).isoformat(),
        "status": report.get("status", "degraded"),
        "new_links": report.get("new_unique_links", 0),
        "leads_24h": report.get("company_release_leads_24h", 0),
        "source_class": "company_or_newswire_unverified",
        "publication": "never_send_or_autoapprove",
    }


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("--root",type=Path,
                        default=Path(os.getenv("ENERGYBREW_STATE_ROOT","/data")))
    args=parser.parse_args(argv)
    result=run_refresh(args.root)
    print(json.dumps(result,indent=2))
    return 0 if result["status"]=="ok" else 2


if __name__=="__main__":
    raise SystemExit(main())
