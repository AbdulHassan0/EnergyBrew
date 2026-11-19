"""Prepare a frozen, review-only energy news candidate set before the 07:00 briefing.

Only collection/processing logic: NO email, no automatic editorial approval,
no newsletter formatting, no claimed coverage where sources are stale.
Default launch timezone America/Chicago; stdlib zoneinfo handles DST.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from coverage_windows import estimate_sampling_coverage
from public_collector_guard import validate_records, ensure_sources_public
from research_desk import assemble, as_time, load

DEFAULT_ZONE = "America/Chicago"
CUTOFF_LOCAL = time(6, 30)
SEND_TARGET_LOCAL = time(7, 0)
MAX_RSS_AGE_MINUTES = 90
MAX_GAL_AGE_MINUTES = 20
MIN_GAL_OVERNIGHT_PCT = 75.0
MIN_RSS_CONNECTED_RATIO = .8
CANDIDATE_LOOKBACK_HOURS = 36
OVERNIGHT_WINDOW_HOURS = 6


def local_schedule(day, zone=DEFAULT_ZONE):
    if isinstance(day, str):
        day = date.fromisoformat(day)
    tz = ZoneInfo(zone)
    cutoff = datetime.combine(day, CUTOFF_LOCAL, tzinfo=tz)
    target = datetime.combine(day, SEND_TARGET_LOCAL, tzinfo=tz)
    return {
        "edition_date": day.isoformat(), "time_zone": zone,
        "news_cutoff_local": cutoff.isoformat(),
        "news_cutoff_utc": cutoff.astimezone(timezone.utc).isoformat(),
        "target_delivery_local": target.isoformat(),
        "target_delivery_utc": target.astimezone(timezone.utc).isoformat(),
    }


def last_successful_run(runs, cutoff, *, success):
    good = [as_time(r.get("run_utc")) for r in (runs or [])
            if isinstance(r, dict) and success(r)
            and (stamp := as_time(r.get("run_utc"))) is not None
            and stamp <= cutoff]
    return max(good) if good else None


def eligible_article(row, lane, cutoff, lookback, local_day, tz):
    if not isinstance(row, dict):
        return False
    if lane == "rss":
        stamp = as_time(row.get("published_utc"))
        if row.get("published_precision") == "day":
            # A day-only notice is NOT proven to be available at 06:30.
            # Previous-day notices can be reviewed without fabricated hours.
            return bool(stamp and stamp.date() < local_day
                        and stamp >= lookback)
    elif lane == "release":
        stamp = as_time(row.get("feed_published_utc"))
    else:
        stamp = as_time(row.get("gdelt_first_seen_utc"))
    return stamp is not None and lookback <= stamp <= cutoff


def prepare(rss, discovery, releases, *, now=None, edition_date=None,
            zone=DEFAULT_ZONE, max_stories=32):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    now = now.astimezone(timezone.utc)
    local_now = now.astimezone(ZoneInfo(zone))
    edition_date = edition_date or local_now.date()
    schedule = local_schedule(edition_date, zone=zone)
    cutoff = as_time(schedule["news_cutoff_utc"])
    lookback = cutoff - timedelta(hours=CANDIDATE_LOOKBACK_HOURS)
    tz = ZoneInfo(zone)
    issues = []
    warnings = []
    if now < cutoff:
        issues.append("edition_cutoff_not_reached")
    if now >= as_time(schedule["target_delivery_utc"]):
        warnings.append("edition_target_time_has_passed_do_not_claim_on_time_delivery")

    rss_runs = rss.get("runs", []) if isinstance(rss, dict) else []
    gal_runs = discovery.get("gal_runs", []) if isinstance(discovery, dict) else []
    last_rss = last_successful_run(rss_runs, cutoff,
                                  success=lambda r: r.get("scan_state") in ("healthy","degraded")
                                  and r.get("feeds_connected", 0) > 0)
    last_gal = last_successful_run(gal_runs, cutoff,
                                  success=lambda r: r.get("status") == "ok")
    age_rss = round((cutoff - last_rss).total_seconds()/60, 1) if last_rss else None
    age_gal = round((cutoff - last_gal).total_seconds()/60, 1) if last_gal else None
    if age_rss is None or age_rss > MAX_RSS_AGE_MINUTES:
        issues.append("publisher_rss_not_recent_at_cutoff")
    if age_gal is None or age_gal > MAX_GAL_AGE_MINUTES:
        issues.append("gdelt_gal_not_recent_at_cutoff")
    latest_rss = next((r for r in reversed(rss_runs)
                       if as_time(r.get("run_utc")) == last_rss), None)
    ratio = None
    if latest_rss:
        total = int(latest_rss.get("feeds_checked", 0) or 0)
        good = int(latest_rss.get("feeds_connected", 0) or 0)
        ratio = round(good/total, 3) if total else None
    if ratio is None or ratio < MIN_RSS_CONNECTED_RATIO:
        issues.append("publisher_rss_below_minimum_quorum")
    elif ratio < 1:
        warnings.append("some_rss_feeds_failed_at_cutoff")

    coverage = estimate_sampling_coverage(
        gal_runs, now=cutoff, hours=OVERNIGHT_WINDOW_HOURS)
    if coverage["potential_coverage_upper_bound_pct"] < MIN_GAL_OVERNIGHT_PCT:
        issues.append("overnight_gdelt_sampling_below_minimum")
    if coverage["potential_coverage_upper_bound_pct"] < 100:
        warnings.append("some_overnight_index_windows_unobserved")

    edition_local_day = date.fromisoformat(schedule["edition_date"])
    rss_articles = [x for x in (rss.get("articles",[]) if isinstance(rss,dict) else [])
                    if eligible_article(x,"rss",cutoff,lookback,edition_local_day,tz)]
    discovered = [x for x in (discovery.get("leads",[]) if isinstance(discovery,dict) else [])
                  if eligible_article(x,"discovery",cutoff,lookback,edition_local_day,tz)]
    released = [x for x in (releases.get("leads",[]) if isinstance(releases,dict) else [])
                if eligible_article(x,"release",cutoff,lookback,edition_local_day,tz)]
    desk = assemble(rss_articles,discovered,released,now=cutoff,max_stories=max_stories)
    if desk["selected_research_links"] == 0:
        issues.append("no_qualifying_research_leads")
    if desk["missing_categories"]:
        warnings.append("some_energy_beats_unobserved_not_proof_of_absence")

    return {
        "edition": schedule,
        "prepared_at_utc": now.isoformat(),
        "status": "ready_for_editor_review" if not issues else "blocked_collection_readiness",
        "blocking_issues": issues,
        "warnings": warnings,
        "publisher_rss_age_at_cutoff_minutes": age_rss,
        "gdelt_gal_age_at_cutoff_minutes": age_gal,
        "publisher_rss_connection_ratio": ratio,
        "overnight_gdelt_window": coverage,
        "candidate_window_utc": {"from":lookback.isoformat(),"through":cutoff.isoformat()},
        "eligible_source_records": {"rss":len(rss_articles),"discovery":len(discovered),"releases":len(released)},
        "research_desk": desk,
        "publication_status":"research_only_not_approved_not_sent",
        "disclaimer":"A ready research snapshot is NOT fact-checked, licensed for republication, or approved for distribution.",
    }


def write_preparation(result, directory):
    directory = Path(directory)
    directory.mkdir(parents=True,exist_ok=True)
    # Blocked reports can be overwritten to reflect the latest diagnostics.
    report = directory / ("readiness_"+result["edition"]["edition_date"]+".json")
    report.write_text(json.dumps({
        k:v for k,v in result.items() if k!="research_desk"
    }, indent=2)+"\n",encoding="utf-8")
    if result["status"] != "ready_for_editor_review":
        return False
    freeze = directory / ("research_"+result["edition"]["edition_date"]+".json")
    stable = {
        "edition": result["edition"],
        "candidate_window_utc": result["candidate_window_utc"],
        "research_desk": result["research_desk"],
        "publication_status": result["publication_status"],
        "disclaimer": result["disclaimer"],
    }
    body = json.dumps(stable,sort_keys=True,ensure_ascii=False,indent=2)+"\n"
    if freeze.exists():
        if freeze.read_text(encoding="utf-8") != body:
            raise ValueError("Immutable morning research snapshot already exists; refusing to overwrite")
        return False
    tmp=freeze.with_suffix(".tmp")
    tmp.write_text(body,encoding="utf-8")
    tmp.replace(freeze)
    return True


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--rss",type=Path,default=Path("state/articles.json"))
    p.add_argument("--discovery",type=Path,default=Path("state/discovery.json"))
    p.add_argument("--releases",type=Path,default=Path("state/press_releases.json"))
    p.add_argument("--output",type=Path,default=Path("output/morning"))
    p.add_argument("--time-zone",default=DEFAULT_ZONE)
    p.add_argument("--edition-date",default=None)
    args=p.parse_args(argv)
    ensure_sources_public()
    # Reuse the existing public-metadata state validator before freezing a desk.
    for path,key in ((args.rss,"articles"),(args.discovery,"leads"),(args.releases,"leads")):
        validate_records(path,key)
    def read(path):
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))
    data=prepare(read(args.rss),read(args.discovery),read(args.releases),
                 edition_date=args.edition_date,zone=args.time_zone)
    froze=write_preparation(data,args.output)
    print(json.dumps({
        "date":data["edition"]["edition_date"],"status":data["status"],
        "issues":data["blocking_issues"],"frozen":froze,
        "research_candidates":data["research_desk"]["selected_research_links"]
    },indent=2))
    return 0 if data["status"]=="ready_for_editor_review" else 2

if __name__=="__main__":
    raise SystemExit(main())
