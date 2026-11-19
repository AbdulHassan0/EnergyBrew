"""Single-disk EnergyBrew Render worker: GAL sampling plus morning research.

Render cron jobs cannot share a worker's persistent disk. This service runs
both lanes on ONE paid disk-backed background worker, without publishing or
sending email. Every scheduled attempt is durably recorded; missed windows
remain missed and historical GDELT samples are never fabricated.
"""
from __future__ import annotations

import argparse
import json
import os
import queue
import threading
import time
from dataclasses import dataclass
from datetime import datetime, time as wall_time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from collector_daemon import atomic_json, run_forever as collect_gal_forever
from host_rss_refresh import run_refresh
from morning_host_runner import run_morning
from morning_readiness import main as morning_preview_main
from public_collector_guard import SafetyError, ensure_sources_public


@dataclass(frozen=True)
class ScheduledJob:
    name: str
    hour: int
    minute: int
    latest_hour: int
    latest_minute: int

    def start(self):
        return wall_time(self.hour, self.minute)

    def deadline(self):
        return wall_time(self.latest_hour, self.latest_minute)


JOBS = (
    ScheduledJob("rss_early", 5, 35, 5, 44),
    ScheduledJob("research_preview", 5, 45, 6, 0),
    ScheduledJob("rss_pre_cutoff", 6, 24, 6, 30),
    ScheduledJob("research_final", 6, 38, 6, 45),
)
MAX_ATTEMPTS = 2
RETRY_AFTER_SECONDS = 75
DEFAULT_WAKE_SECONDS = 10


def read_state(path):
    path = Path(path)
    if not path.exists():
        return {"dates": {}}
    record = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(record, dict) or not isinstance(record.get("dates"), dict):
        raise ValueError("Persistent Render scheduling ledger is invalid")
    return record


def run_job(name, root, zone):
    """Execute just one news-only operation, preserving the public-data guard."""
    root = Path(root)
    ensure_sources_public()
    if name in ("rss_early", "rss_pre_cutoff"):
        outcome = run_refresh(root)
        return ("ok" if outcome["status"] in ("healthy", "degraded")
                else "failed", outcome["status"])
    if name == "research_preview":
        code = morning_preview_main([
            "--rss", str(root / "articles.json"),
            "--discovery", str(root / "discovery.json"),
            "--releases", str(root / "press_releases.json"),
            "--output", str(root / "morning"),
            "--time-zone", zone,
            "--preflight",
        ])
        return ("ok" if code == 0 else "failed", "unfrozen_preflight_research_only")
    if name == "research_final":
        outcome = run_morning(root, zone=zone)
        status = outcome["status"]
        return ("ok" if status == "ready_for_editor_review" else "blocked",
                status)
    raise ValueError("Unknown scheduled research task: " + name)


def scheduler_tick(root, *, now=None, zone="America/Chicago", execute=None):
    """Run due jobs once per scheduled window; limited retry on failures.

    A record of a started job is persisted BEFORE execution. Interrupted
    attempts can be safely retried at most once in the same local window,
    but successful or blocked final editions are never silently rerun.
    """
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Scheduler clock must include a timezone")
    now = now.astimezone(timezone.utc)
    local_now = now.astimezone(ZoneInfo(zone))
    day = local_now.date().isoformat()
    wall = local_now.time().replace(tzinfo=None)
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    state_file = root / "render_schedule.json"
    state = read_state(state_file)
    dates = state["dates"]
    today = dates.setdefault(day, {})
    # Local date keys retain enough recent audits to diagnose missed editions.
    keep = sorted(dates)[-10:]
    for expired in list(dates):
        if expired not in keep:
            del dates[expired]
    dispatched = []
    execute = execute or (lambda name: run_job(name, root, zone))
    for spec in JOBS:
        item = today.setdefault(spec.name, {"status": "pending", "attempts": 0})
        if item.get("status") in ("ok", "blocked", "missed", "failed"):
            continue
        if wall >= spec.deadline():
            item.update(status="missed", last_checked_utc=now.isoformat())
            atomic_json(state_file, state)
            dispatched.append((spec.name, "missed"))
            continue
        if wall < spec.start():
            continue
        tries = int(item.get("attempts", 0))
        if tries >= MAX_ATTEMPTS:
            item.update(status="failed", last_checked_utc=now.isoformat())
            atomic_json(state_file, state)
            dispatched.append((spec.name, "failed"))
            continue
        retry = item.get("next_attempt_after_utc")
        if retry and datetime.fromisoformat(retry) > now:
            continue
        # Mark BEFORE calling an operation; a process crash must not silently
        # erase the fact that a possibly interrupted attempt occurred.
        item.update(status="running", attempts=tries + 1,
                    started_utc=now.isoformat(),
                    next_attempt_after_utc=(now + timedelta(
                        seconds=RETRY_AFTER_SECONDS)).isoformat())
        atomic_json(state_file, state)
        try:
            outcome, reason = execute(spec.name)
            if outcome not in ("ok", "blocked", "failed"):
                raise ValueError("Invalid job outcome: " + str(outcome))
            item.update(status=outcome if outcome != "failed" or
                        item["attempts"] >= MAX_ATTEMPTS else "retry_pending",
                        result=reason, finished_utc=datetime.now(
                            timezone.utc).isoformat())
        except SafetyError:
            item.update(status="failed", result="public_metadata_safety_failure")
            atomic_json(state_file, state)
            raise
        except Exception as exc:
            item.update(status=("failed" if item["attempts"] >= MAX_ATTEMPTS
                                else "retry_pending"),
                        result=type(exc).__name__,
                        finished_utc=datetime.now(timezone.utc).isoformat())
        atomic_json(state_file, state)
        dispatched.append((spec.name, item["status"]))
    return {"date": day, "dispatched": dispatched, "jobs": dict(today)}


def worker_loop(root, *, zone="America/Chicago", wake_seconds=DEFAULT_WAKE_SECONDS,
                gal_interval_seconds=300, sleep=time.sleep, now_fn=None,
                max_iterations=None, gal_runner=None):
    """Start GAL concurrently, while daily research uses the same mounted disk."""
    if wake_seconds < 1 or gal_interval_seconds < 120:
        raise ValueError("Unsupported polling intervals")
    ensure_sources_public()
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    # Fail immediately for a missing, read-only or full persistent disk.
    atomic_json(root / "render_worker_startup.json", {
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "role": "single_persistent_news_metadata_worker",
        "publication": "never_send_or_publish",
    })
    failures = queue.SimpleQueue()
    gal_runner = gal_runner or collect_gal_forever

    def gal_thread():
        try:
            gal_runner(root / "discovery.json", root / "output" / "gal-worker",
                       interval_seconds=gal_interval_seconds)
            failures.put("GAL collector stopped unexpectedly")
        except BaseException as exc:
            failures.put("GAL collector stopped: " + type(exc).__name__)

    gal = threading.Thread(target=gal_thread, name="energybrew-gal", daemon=True)
    gal.start()
    iterations = 0
    while True:
        if not failures.empty():
            raise RuntimeError(failures.get())
        if not gal.is_alive():
            raise RuntimeError("GDELT worker thread is no longer alive")
        now = now_fn() if now_fn else datetime.now(timezone.utc)
        report = scheduler_tick(root, now=now, zone=zone)
        for name, result in report["dispatched"]:
            print(json.dumps({"job": name, "status": result,
                              "edition_date": report["date"]}), flush=True)
        atomic_json(root / "render_worker_heartbeat.json", {
            "checked_utc": now.astimezone(timezone.utc).isoformat(),
            "gal_thread_alive": gal.is_alive(),
            "edition_date": report["date"],
            "scheduled_jobs": {name: v["status"] for name, v in
                               report["jobs"].items()},
            "source": "local_worker_heartbeat_not_external_monitoring",
            "publication": "research_only_not_approved_not_sent",
        })
        iterations += 1
        if max_iterations is not None and iterations >= max_iterations:
            return report
        sleep(wake_seconds)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path,
                        default=Path(os.environ.get("ENERGYBREW_STATE_ROOT", "/data")))
    parser.add_argument("--time-zone", default=os.getenv(
        "ENERGYBREW_TIME_ZONE", "America/Chicago"))
    parser.add_argument("--gal-interval-seconds", type=int, default=300)
    args = parser.parse_args(argv)
    worker_loop(args.root, zone=args.time_zone,
                gal_interval_seconds=args.gal_interval_seconds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
