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
from event_dedup import same_event
from public_collector_guard import validate_records, ensure_sources_public
from research_desk import assemble, as_time, load

DEFAULT_ZONE = "America/Chicago"
CUTOFF_LOCAL = time(6, 30)
SEND_TARGET_LOCAL = time(7, 0)
MAX_RSS_AGE_MINUTES = 90
MAX_GAL_AGE_MINUTES = 20
MAX_PREPARATION_LAG_MINUTES = 20
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


def collection_completion(run):
    """A scan cannot be credited at a cutoff before its network work ends."""
    return as_time(run.get("completed_utc") or run.get("run_utc"))


def last_successful_run(runs, cutoff, *, success):
    good = [stamp for r in (runs or [])
            if isinstance(r, dict) and success(r)
            if (stamp := collection_completion(r)) is not None and stamp <= cutoff]
    return max(good) if good else None


def eligible_article(row, lane, cutoff, lookback, local_day, tz):
    if not isinstance(row, dict):
        return False
    if lane == "rss":
        stamp = as_time(row.get("published_utc"))
        if row.get("published_precision") == "day":
            # A day-only notice is NOT proven to be available at 06:30.
            # Previous-day notices can be reviewed without fabricated hours.
            return bool(stamp and local_day - timedelta(days=1) <= stamp.date() < local_day)
    elif lane == "release":
        stamp = as_time(row.get("feed_published_utc"))
    else:
        stamp = as_time(row.get("gdelt_first_seen_utc"))
    return stamp is not None and lookback <= stamp <= cutoff


def record_time(row, lane):
    key = "published_utc" if lane == "rss" else "feed_published_utc" if lane == "release" else "gdelt_first_seen_utc"
    return as_time(row.get(key)) if isinstance(row, dict) else None


def mark_morning_research(stories, prior_cutoff, overnight_start, previous_research):
    previous = previous_research.get("research_desk",{}).get("stories",[]) if isinstance(previous_research, dict) else []
    previous = [p for p in previous if isinstance(p,dict)]
    prior_urls = {p.get("url") for p in previous}
    for story in stories:
        stamp = as_time(story["observed_time_utc"])
        if story["time_basis"] == "official_publication_date_only":
            bucket = "date_only_prior_day_context"
        elif stamp and stamp >= overnight_start:
            bucket = "overnight_on_source_time_basis"
        elif stamp and stamp >= prior_cutoff:
            bucket = "since_previous_cutoff_on_source_time_basis"
        else:
            bucket = "older_background_context"
        story["morning_time_bucket"] = bucket
        story["morning_time_basis"] = story["time_basis"]
        story["prior_research_repeat_review"] = (
            "same_url_previous_research" if story["url"] in prior_urls else
            "likely_same_event_previous_research" if any(same_event(story,p) for p in previous)
            else None
        )
        # Yesterday's candidate list does not imply it was ever approved or sent.
        # Only flag possible repeats for editors; never automatically discard.
    return stories


def prepare(rss, discovery, releases, *, now=None, edition_date=None,
            zone=DEFAULT_ZONE, max_stories=32, previous_research=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    now = now.astimezone(timezone.utc)
    local_now = now.astimezone(ZoneInfo(zone))
    edition_date = edition_date or local_now.date()
    schedule = local_schedule(edition_date, zone=zone)
    cutoff = as_time(schedule["news_cutoff_utc"])
    # Early preflight cannot use future timestamps just because the final
    # editorial cutoff is scheduled for later that morning.
    observed_cutoff = min(now, cutoff)
    lookback = cutoff - timedelta(hours=CANDIDATE_LOOKBACK_HOURS)
    tz = ZoneInfo(zone)
    issues = []
    warnings = []
    if now < cutoff:
        issues.append("edition_cutoff_not_reached")
    if now >= cutoff + timedelta(minutes=MAX_PREPARATION_LAG_MINUTES):
        issues.append("insufficient_editorial_review_time_before_7am")
    if now >= as_time(schedule["target_delivery_utc"]):
        warnings.append("edition_target_time_has_passed_do_not_claim_on_time_delivery")

    rss_runs = rss.get("runs", []) if isinstance(rss, dict) else []
    gal_runs = discovery.get("gal_runs", []) if isinstance(discovery, dict) else []
    last_rss = last_successful_run(rss_runs, observed_cutoff,
                                  success=lambda r: r.get("scan_state") in ("healthy","degraded")
                                  and r.get("feeds_connected", 0) > 0)
    last_gal = last_successful_run(gal_runs, observed_cutoff,
                                  success=lambda r: r.get("status") == "ok")
    age_rss = round(max(0, (cutoff - last_rss).total_seconds()/60), 1) if last_rss else None
    age_gal = round(max(0, (cutoff - last_gal).total_seconds()/60), 1) if last_gal else None
    if any((stamp := collection_completion(r)) and cutoff < stamp <= now
           for r in rss_runs if isinstance(r,dict)):
        warnings.append("rss_polled_after_cutoff_records_strictly_filtered_to_cutoff")
        warnings.append("postcutoff_rss_poll_not_credited_to_0630_readiness")
    if any((stamp := collection_completion(r)) and cutoff < stamp <= now
           for r in gal_runs if isinstance(r,dict)):
        warnings.append("gal_polled_after_cutoff_records_strictly_filtered_to_cutoff")
        warnings.append("postcutoff_gal_poll_not_credited_to_0630_readiness")
    if age_rss is None or age_rss > MAX_RSS_AGE_MINUTES:
        issues.append("publisher_rss_not_recent_at_cutoff")
    if age_gal is None or age_gal > MAX_GAL_AGE_MINUTES:
        issues.append("gdelt_gal_not_recent_at_cutoff")
    latest_rss = next((r for r in reversed(rss_runs)
                       if collection_completion(r) == last_rss), None)
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
                    if eligible_article(x,"rss",observed_cutoff,lookback,edition_local_day,tz)]
    discovered = [x for x in (discovery.get("leads",[]) if isinstance(discovery,dict) else [])
                  if eligible_article(x,"discovery",observed_cutoff,lookback,edition_local_day,tz)]
    released = [x for x in (releases.get("leads",[]) if isinstance(releases,dict) else [])
                if eligible_article(x,"release",observed_cutoff,lookback,edition_local_day,tz)]
    # Prefer real developments since yesterday's 06:30 local cutoff. A UTC
    # 24-hour subtraction is wrong across daylight saving transitions.
    previous_day = edition_local_day - timedelta(days=1)
    prior_cutoff = datetime.combine(previous_day, CUTOFF_LOCAL, tzinfo=tz).astimezone(timezone.utc)
    overnight_start = datetime.combine(previous_day, time(18,0), tzinfo=tz).astimezone(timezone.utc)
    fresh_rss = [x for x in rss_articles if x.get("published_precision") != "day"
                 and (record_time(x,"rss") or datetime.min.replace(tzinfo=timezone.utc)) >= prior_cutoff]
    fresh_discovery = [x for x in discovered if (record_time(x,"discovery") or datetime.min.replace(tzinfo=timezone.utc)) >= prior_cutoff]
    fresh_release = [x for x in released if (record_time(x,"release") or datetime.min.replace(tzinfo=timezone.utc)) >= prior_cutoff]
    desk = assemble(fresh_rss,fresh_discovery,fresh_release,now=observed_cutoff,max_stories=max_stories)
    mark_morning_research(desk["stories"],prior_cutoff,overnight_start,previous_research)
    # Older records are context only. Do not fill limited headline slots
    # with yesterday's articles simply because they rank highly.
    old_rss = [x for x in rss_articles if x not in fresh_rss]
    old_discovery = [x for x in discovered if x not in fresh_discovery]
    old_release = [x for x in released if x not in fresh_release]
    background = assemble(old_rss,old_discovery,old_release,now=observed_cutoff,max_stories=6)
    mark_morning_research(background["stories"],prior_cutoff,overnight_start,previous_research)
    if desk["selected_research_links"] == 0:
        issues.append("no_qualifying_research_leads")
    publisher_dated = sum(
        s.get("origin") == "official_rss" and bool(s.get("publisher_time_verified"))
        for s in desk["stories"]
    )
    if not publisher_dated:
        issues.append("no_publisher_timestamped_morning_lead")
    if desk["missing_categories"]:
        warnings.append("some_energy_beats_unobserved_not_proof_of_absence")

    return {
        "edition": schedule,
        "prepared_at_utc": now.isoformat(),
        "status": "ready_for_editor_review" if not issues else "blocked_collection_readiness",
        "blocking_issues": issues,
        "warnings": warnings,
        "publisher_rss_age_at_cutoff_minutes": age_rss,
        "publisher_rss_last_successful_scan_utc": last_rss.isoformat() if last_rss else None,
        "gdelt_gal_last_successful_scan_utc": last_gal.isoformat() if last_gal else None,
        "gdelt_gal_age_at_cutoff_minutes": age_gal,
        "publisher_rss_connection_ratio": ratio,
        "overnight_gdelt_window": coverage,
        "candidate_window_utc": {"from":lookback.isoformat(),"through":observed_cutoff.isoformat()},
        "eligible_source_records": {"rss":len(rss_articles),"discovery":len(discovered),"releases":len(released)},
        "primary_candidate_count_since_previous_cutoff":desk["selected_research_links"],
        "publisher_timestamped_primary_candidates":publisher_dated,
        "older_background_context_count":background["selected_research_links"],
        "background_context":background["stories"],
        "research_desk": desk,
        "publication_status":"research_only_not_approved_not_sent",
        "disclaimer":"A ready research snapshot is NOT fact-checked, licensed for republication, or approved for distribution.",
    }


def write_preparation(result, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    report = directory / ("readiness_" + result["edition"]["edition_date"] + ".json")
    freeze = directory / ("research_" + result["edition"]["edition_date"] + ".json")
    ready = result["status"] == "ready_for_editor_review"
    snapshot = None
    if ready:
        stable = {
            "edition": result["edition"],
            "candidate_window_utc": result["candidate_window_utc"],
            "research_desk": result["research_desk"],
            "background_context": result["background_context"],
            "publication_status": result["publication_status"],
            "disclaimer": result["disclaimer"],
        }
        snapshot = json.dumps(stable,sort_keys=True,ensure_ascii=False,indent=2)+"\n"
        if freeze.exists() and freeze.read_text(encoding="utf-8") != snapshot:
            # Never leave a newly written READY report when the frozen
            # payload conflicts with the previously committed edition.
            raise ValueError("Immutable morning research snapshot already exists; refusing to overwrite")
    summary = {k:v for k,v in result.items() if k not in ("research_desk","background_context")}
    summary["frozen_research_available"] = ready
    temp_report = report.with_suffix(".tmp")
    temp_report.write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
    temp_report.replace(report)
    if not ready or freeze.exists():
        return False
    temp_freeze = freeze.with_suffix(".tmp")
    temp_freeze.write_text(snapshot,encoding="utf-8")
    temp_freeze.replace(freeze)
    return True


def write_preflight(result, directory):
    """Preliminary metadata-only editorial view; never a frozen or sendable edition."""
    directory = Path(directory)
    directory.mkdir(parents=True,exist_ok=True)
    output = directory / ("preflight_" + result["edition"]["edition_date"] + ".json")
    data = {
        "edition": result["edition"],
        "as_of_utc": result["candidate_window_utc"]["through"],
        "status": "unfrozen_preflight_research_only",
        "primary_research_candidates": result["research_desk"]["stories"],
        "background_context": result["background_context"],
        "blocking_issues_at_preflight": result["blocking_issues"],
        "disclaimer": "PREVIEW ONLY. Not cutoff-complete, fact-checked, approved or sent.",
    }
    temp = output.with_suffix(".tmp")
    temp.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    temp.replace(output)
    return output


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--rss",type=Path,default=Path("state/articles.json"))
    p.add_argument("--discovery",type=Path,default=Path("state/discovery.json"))
    p.add_argument("--releases",type=Path,default=Path("state/press_releases.json"))
    p.add_argument("--output",type=Path,default=Path("output/morning"))
    p.add_argument("--time-zone",default=DEFAULT_ZONE)
    p.add_argument("--edition-date",default=None)
    p.add_argument("--prior-research",type=Path,default=None)
    p.add_argument("--preflight",action="store_true")
    args=p.parse_args(argv)
    ensure_sources_public()
    # Reuse the existing public-metadata state validator before freezing a desk.
    for path,key in ((args.rss,"articles"),(args.discovery,"leads"),(args.releases,"leads")):
        validate_records(path,key)
    def read(path):
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))
    prior=read(args.prior_research) if args.prior_research else None
    data=prepare(read(args.rss),read(args.discovery),read(args.releases),
                 edition_date=args.edition_date,zone=args.time_zone,
                 previous_research=prior)
    if args.preflight:
        file=write_preflight(data,args.output)
        print(json.dumps({"status":"unfrozen_preflight_research_only",
                          "path":str(file),
                          "candidate_count":data["research_desk"]["selected_research_links"]}))
        return 0
    froze=write_preparation(data,args.output)
    print(json.dumps({
        "date":data["edition"]["edition_date"],"status":data["status"],
        "issues":data["blocking_issues"],"frozen":froze,
        "research_candidates":data["research_desk"]["selected_research_links"]
    },indent=2))
    return 0 if data["status"]=="ready_for_editor_review" else 2

if __name__=="__main__":
    raise SystemExit(main())
