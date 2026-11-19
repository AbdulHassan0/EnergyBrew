"""Reliable single-host GDELT sampling daemon for an internet-connected worker.

Unlike GitHub Actions cron, a continuously running worker owns its scheduling.
It requires a persistent local volume and an external supervisor to restart it.
Missing runs are reported; historical GDELT data are NEVER invented or backfilled.
No subscriber mail, article bodies, or unlicensed RSS sources.
Portable Windows/POSIX state locks prevent duplicate daemon instances.
"""
from __future__ import annotations
import argparse
from portable_lock import lock_exclusive_nonblocking
import json
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from gal import collect_gal
from public_collector_guard import ensure_sources_public, validate_records

DEFAULT_INTERVAL_SECONDS = 300
MIN_INTERVAL_SECONDS = 120


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_name(path.name + ".tmp")
    staging.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    staging.replace(path)


def sample_once(state_path, output_dir, *, now=None, fetcher=None):
    """Collect on a staging state; safety-check before swapping durable state."""
    now = now or datetime.now(timezone.utc)
    state_path, output_dir = Path(state_path), Path(output_dir)
    ensure_sources_public()
    state_path.parent.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    staging = state_path.with_name(state_path.name + ".staging")
    if staging.exists():
        raise RuntimeError("Stale staged state: resolve before collector continues")
    if state_path.exists():
        shutil.copyfile(state_path, staging)
    try:
        report = collect_gal(
            staging, output_dir, now=now, fetcher=fetcher,
            completion_clock=(lambda: datetime.now(timezone.utc))
            if fetcher is None else None)
        # The same public-metadata safety gate used by GitHub Actions is
        # mandatory even for the independent worker.
        validate_records(staging, "leads")
        staging.replace(state_path)
        return report
    finally:
        if staging.exists():
            staging.unlink()


def update_health(path, report, *, now=None):
    now = now or datetime.now(timezone.utc)
    path = Path(path)
    if path.exists():
        previous = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(previous, dict):
            raise ValueError("Malformed collector heartbeat")
    else:
        previous = {}
    good = report.get("status") == "ok"
    failures = 0 if good else int(previous.get("consecutive_failures", 0)) + 1
    heartbeat = {
        "checked_utc": now.isoformat(),
        "last_success_utc": now.isoformat() if good else previous.get("last_success_utc"),
        "status": "healthy" if good else "critical" if failures >= 3 else "degraded",
        "consecutive_failures": failures,
        "upstream_feed_status": report.get("status"),
        "upstream_index_lag_minutes": report.get("feed_index_lag_minutes"),
        "new_unique_links": report.get("new_unique_links", 0),
        "latest_error": None if good else str(report.get("error", "unknown failure"))[:160],
    }
    atomic_json(path, heartbeat)
    return heartbeat


def collect_cycle(state, output, *, now=None, fetcher=None):
    report = sample_once(state, output, now=now, fetcher=fetcher)
    # Heartbeats must mark the END of the live GDELT request. Using the
    # injected/start time here makes a slow request look recent prematurely.
    finished = report.get("completed_utc")
    if not isinstance(finished, str):
        raise ValueError("GAL report has no authoritative completion time")
    finished = datetime.fromisoformat(finished.replace("Z","+00:00"))
    if finished.tzinfo is None or finished.utcoffset() is None:
        raise ValueError("GAL report completion time lacks timezone")
    heartbeat = update_health(Path(output) / "worker_health.json", report,
                              now=finished)
    return report, heartbeat


def recover_abandoned_stage(state_path):
    """Discard ONLY a leftover uncommitted staging file under exclusive lock.

    The durable committed state is never replaced with possibly partial data.
    This must be called only while holding the worker's volume-level flock.
    """
    state_path=Path(state_path)
    staging=state_path.with_name(state_path.name+".staging")
    if not staging.exists():
        return False
    if state_path.exists():
        # Do not discard a temp file when the supposedly durable history is
        # already corrupt: require operator intervention instead of data loss.
        data=json.loads(state_path.read_text(encoding="utf-8"))
        if not isinstance(data,dict) or not isinstance(data.get("leads"),list):
            raise ValueError("Durable discovery state malformed; staged data retained")
    staging.unlink()
    return True


def run_forever(state, output, interval_seconds=DEFAULT_INTERVAL_SECONDS):
    if interval_seconds < MIN_INTERVAL_SECONDS:
        raise ValueError("Minimum safe polling interval is 120 seconds")
    state, output = Path(state), Path(output)
    state.parent.mkdir(parents=True, exist_ok=True)
    lock_path = state.parent / "worker.lock"
    with open(lock_path, "a+", encoding="utf-8") as lock:
        try:
            lock_exclusive_nonblocking(lock)
        except BlockingIOError as exc:
            raise RuntimeError("Another collector holds this persistent volume lock") from exc
        if recover_abandoned_stage(state):
            print(json.dumps({"event":"recovered_abandoned_staging_write",
                              "state":str(state)}),flush=True)
        next_due = time.monotonic()
        while True:
            try:
                report, heartbeat = collect_cycle(state, output)
                print(json.dumps({
                    "checked_utc": heartbeat["checked_utc"],
                    "status": heartbeat["status"],
                    "upstream": report["status"],
                    "new_links": report.get("new_unique_links", 0),
                }), flush=True)
            except Exception as exc:
                # Do not silently swallow corruption, invalid state schemas,
                # public-metadata guard violations or permission/config errors.
                if not isinstance(exc, OSError):
                    raise
                update_health(output / "worker_health.json",
                              {"status":"degraded","error":type(exc).__name__+": "+str(exc)[:130]})
            next_due += interval_seconds
            if next_due < time.monotonic():
                # A late network request does not trigger burst backfill or
                # pretend missed collection intervals were recovered.
                next_due = time.monotonic() + interval_seconds
            time.sleep(max(0, next_due - time.monotonic()))


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--state", type=Path, default=Path(os.environ.get("ENERGYBREW_STATE", "/data/discovery.json")))
    p.add_argument("--output", type=Path, default=Path(os.environ.get("ENERGYBREW_OUTPUT", "/data/output")))
    p.add_argument("--interval-seconds", type=int, default=DEFAULT_INTERVAL_SECONDS)
    p.add_argument("--once", action="store_true")
    a = p.parse_args(argv)
    if a.once:
        report, health = collect_cycle(a.state, a.output)
        print(json.dumps(health, indent=2))
        return 0 if report["status"] == "ok" else 2
    run_forever(a.state, a.output, a.interval_seconds)
    return 0


if __name__=="__main__":
    raise SystemExit(main())
