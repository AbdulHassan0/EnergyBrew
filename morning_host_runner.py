"""One-shot 06:30–06:49 local preparation on a persistent EnergyBrew host.

Collect publisher RSS metadata, read the atomic GAL daemon state, and produce
an immutable review-only morning research snapshot. Never send any email.
"""
from __future__ import annotations
import argparse
import fcntl
import json
import os
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from collector import collect
from morning_readiness import local_schedule, prepare, write_preparation
from public_collector_guard import ensure_sources_public, validate_records
from research_desk import as_time


def read_json(path):
    path = Path(path)
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Research state must be a JSON object: " + str(path))
    return data


def refresh_rss_safely(state_path, output, *, now, fetcher=None):
    """Uncommitted RSS state is validated before replacing durable history."""
    state_path = Path(state_path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    staging = state_path.with_name(state_path.name + ".morning-stage")
    if staging.exists():
        raise RuntimeError("An uncommitted morning RSS staging file requires inspection")
    if state_path.exists():
        shutil.copyfile(state_path, staging)
    try:
        report = collect(staging, Path(output), now=now, fetcher=fetcher)
        validate_records(staging, "articles")
        staging.replace(state_path)
        return report
    finally:
        if staging.exists():
            staging.unlink()


def run_morning(root, *, now=None, zone="America/Chicago", fetcher=None,
                completion_clock=None, refresh_rss=True, prerequisite_issues=()):
    # A fixed clock is accepted for deterministic offline regression tests.
    # The live host must validate the ACTUAL completion time before freezing.
    fixed_test_clock = now is not None
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Clock must be timezone aware")
    now = now.astimezone(timezone.utc)
    root = Path(root)
    local_date = now.astimezone(ZoneInfo(zone)).date()
    schedule = local_schedule(local_date, zone)
    cutoff = as_time(schedule["news_cutoff_utc"])
    if not cutoff <= now < cutoff + timedelta(minutes=20):
        raise RuntimeError("Outside 06:30–06:49 local research preparation window; nothing sent or frozen")
    ensure_sources_public()
    root.mkdir(parents=True, exist_ok=True)
    with (root / "morning-runner.lock").open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("Another morning job holds the persistent lock") from exc
        rss_path = root / "articles.json"
        # The Render worker already polls RSS at 06:24; repeating a sequential
        # 15-source scan at 06:38 can overrun the human review window.
        # The independent systemd runner retains its legacy refresh default.
        if refresh_rss:
            rss_report = refresh_rss_safely(
                rss_path, root / "output/rss-morning", now=now, fetcher=fetcher)
        else:
            rss_report = {"scan_state": "pre_cutoff_cached_snapshot"}
        # The GAL worker owns discovery.json; it atomically replaces each
        # committed sample. Morning research only READS that independent state.
        discovery = read_json(root / "discovery.json")
        releases = read_json(root / "press_releases.json")
        prior_date = local_date - timedelta(days=1)
        prior_file = root / "morning" / ("research_" + prior_date.isoformat() + ".json")
        previous_research = read_json(prior_file) if prior_file.exists() else None
        result = prepare(read_json(rss_path), discovery, releases,
                         now=now, edition_date=local_date, zone=zone,
                         previous_research=previous_research)
        if rss_report.get("scan_state") == "critical":
            result["blocking_issues"].append("final_publisher_refresh_critical")
            result["status"] = "blocked_collection_readiness"
        result["final_rss_scan_status"] = rss_report.get("scan_state")
        for issue in prerequisite_issues:
            if issue not in result["blocking_issues"]:
                result["blocking_issues"].append(issue)
                result["status"] = "blocked_collection_readiness"
        completed = (completion_clock() if completion_clock else
                     now if fixed_test_clock else datetime.now(timezone.utc))
        if completed.tzinfo is None or completed.utcoffset() is None:
            raise ValueError("Completion timestamp must include a timezone")
        completed = completed.astimezone(timezone.utc)
        result["host_collection_completed_utc"] = completed.isoformat()
        # An on-time START cannot disguise a slow network scan that finishes
        # too late to leave a meaningful human review window before 07:00.
        if completed >= cutoff + timedelta(minutes=20):
            result["blocking_issues"].append("host_research_completed_after_0650")
            result["status"] = "blocked_collection_readiness"
        frozen = write_preparation(result, root / "morning")
        return {"date":local_date.isoformat(), "status":result["status"],
                "blocking_issues":result["blocking_issues"],
                "frozen":frozen,"selected_research_links":result["research_desk"]["selected_research_links"],
                "latest_rss_status":rss_report.get("scan_state"),
                "publication":"research_only_not_approved_not_sent"}


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--root",type=Path,default=Path(os.environ.get("ENERGYBREW_STATE_ROOT","/data")))
    p.add_argument("--time-zone",default="America/Chicago")
    args=p.parse_args(argv)
    report=run_morning(args.root, zone=args.time_zone)
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "ready_for_editor_review" else 2

if __name__=="__main__":
    raise SystemExit(main())
