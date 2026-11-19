"""Read-only assessment of a free locally running EnergyBrew news collector.

A green source poll does not imply the PC was running all night or that a
newsletter is ready. Local pilot status is never a production SLA.
"""
from __future__ import annotations
import argparse
import json
from datetime import datetime, timedelta, timezone, time
from pathlib import Path
from zoneinfo import ZoneInfo

from ops_metrics import create
from research_desk import as_time


def _state(root, name):
    path=Path(root)/name
    if not path.exists():
        return {}
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict):
        raise ValueError("Invalid persisted news state: "+name)
    return value


def _recent(stamp, now, minutes):
    parsed=as_time(stamp)
    return parsed is not None and -timedelta(minutes=1) <= now-parsed <= timedelta(minutes=minutes)


def inspect(root, *, now=None, zone="America/Chicago"):
    now=now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Pilot report requires a timezone-aware clock")
    now=now.astimezone(timezone.utc)
    root=Path(root)
    rss=_state(root,"articles.json")
    gal=_state(root,"discovery.json")
    releases=_state(root,"press_releases.json")
    heartbeat=_state(root,"render_worker_heartbeat.json")
    health=_state(root,"output/gal-worker/worker_health.json")
    schedule=_state(root,"render_schedule.json")
    metrics=create(rss,gal,releases,now=now)
    problems=[]
    if not _recent(heartbeat.get("checked_utc"),now,2):
        problems.append("no_recent_local_worker_heartbeat")
    if heartbeat.get("gal_thread_alive") is not True:
        problems.append("gal_thread_not_confirmed_alive")
    if health.get("status")!="healthy" or not _recent(health.get("last_success_utc"),now,15):
        problems.append("live_gdelt_not_healthy_or_fresh")
    if not _recent(metrics.get("latest_official_scan_utc"),now,180):
        problems.append("publisher_rss_quorum_not_observed_within_three_hours")
    local=now.astimezone(ZoneInfo(zone))
    edition=local.date().isoformat()
    jobs=schedule.get("dates",{}).get(edition,{})
    if not isinstance(jobs,dict):
        raise ValueError("Invalid local morning job record")
    final=jobs.get("research_final",{})
    if not isinstance(final,dict):
        raise ValueError("Invalid final research job state")
    if local.time().replace(tzinfo=None)>=time(7,0):
        if final.get("status") not in ("ok","blocked","failed","missed"):
            problems.append("morning_final_job_not_recorded_after_0700")
        elif final.get("status")!="ok":
            problems.append("morning_final_job_"+final["status"])
        else:
            # A ledger saying "ok" does not prove that a safe frozen research
            # snapshot was durably created for this morning's local edition.
            snapshot = root / "morning" / ("research_" + edition + ".json")
            if not snapshot.exists():
                problems.append("morning_frozen_research_snapshot_missing")
            else:
                record=_state(root, "morning/research_" + edition + ".json")
                if record.get("edition",{}).get("edition_date")!=edition:
                    problems.append("morning_frozen_research_edition_mismatch")
    if not metrics["seven_day_pilot_complete"]:
        problems.append("seven_day_sampling_reliability_not_yet_proven")
    return {
        "checked_utc":now.isoformat(),
        "state_directory":str(root),
        "status":"needs_attention" if problems else "pilot_observations_healthy_not_production",
        "last_worker_heartbeat_utc":heartbeat.get("checked_utc"),
        "last_successful_gdelt_utc":health.get("last_success_utc"),
        "last_healthy_publisher_scan_utc":metrics.get("latest_official_scan_utc"),
        "morning_date_local":edition,
        "morning_final_status":final.get("status","unknown"),
        "gal_24h_potential_coverage_upper_bound_pct":metrics["gal_sampled_window_24h"]["potential_coverage_upper_bound_pct"],
        "seven_day_pilot_complete":metrics["seven_day_pilot_complete"],
        "problems":problems,
        "meaning":"Local collection evidence only. Not verified publisher completeness, editorial approval or a newsletter delivery guarantee.",
    }


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("--root",type=Path,required=True)
    parser.add_argument("--time-zone",default="America/Chicago")
    parser.add_argument("--output",type=Path)
    args=parser.parse_args(argv)
    report=inspect(args.root,zone=args.time_zone)
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,indent=2))
    return 0 if report["status"]=="pilot_observations_healthy_not_production" else 2


if __name__=="__main__":
    raise SystemExit(main())
