"""Audit news-collection coverage without confusing connectivity with editorial readiness.

All thresholds are operational heuristics, not proof of complete news coverage.
Discovery API first-seen times are never treated as article publication times.
"""
from __future__ import annotations
import argparse
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from coverage_windows import estimate_sampling_coverage


REQUIRED_BEATS = (
    "Natural Gas",
    "LNG",
    "Power & Electricity",
    "Oil & Energy",
    "Infrastructure & Investment",
    "Geopolitics",
)
TARGET_CANDIDATES_24H = 12
MAX_RUN_AGE_HOURS = 12


def dt(value):
    if not isinstance(value, str):
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return stamp.astimezone(timezone.utc) if stamp.tzinfo else None


def load_json(path, *, default=None):
    if not path or not Path(path).exists():
        return default
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def audit(rss_state, rss_report, discovery_state=None, discovery_report=None, *, release_state=None, release_report=None, gal_report=None, now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now must be timezone aware")
    rss_state = rss_state if isinstance(rss_state, dict) else {}
    rss_report = rss_report if isinstance(rss_report, dict) else {}
    discovery_state = discovery_state if isinstance(discovery_state, dict) else {}
    discovery_report = discovery_report if isinstance(discovery_report, dict) else {}
    release_state = release_state if isinstance(release_state, dict) else {}
    release_report = release_report if isinstance(release_report, dict) else {}
    gal_report = gal_report if isinstance(gal_report, dict) else {}
    cutoff = now-timedelta(hours=24)
    articles = rss_state.get("articles") if isinstance(rss_state.get("articles"),list) else []
    discovery = discovery_state.get("leads") if isinstance(discovery_state.get("leads"),list) else []
    candidates = {}
    for article in articles:
        if not isinstance(article, dict):
            continue
        published = dt(article.get("published_utc"))
        if not published or published < cutoff or published > now+timedelta(minutes=10):
            continue
        if article.get("published_precision","timestamp")!="timestamp":
            continue
        if article.get("editorial_candidate") is not True:
            continue
        url=article.get("url")
        if url:
            candidates[url] = article
    official_candidates=[a for a in candidates.values() if a.get("source_class") not in ("specialist_publisher","system_operator_primary")]
    specialist_candidates=[a for a in candidates.values() if a.get("source_class")=="specialist_publisher"]
    grid_operator_candidates=[a for a in candidates.values() if a.get("source_class")=="system_operator_primary"]
    beats = Counter(a.get("category","Cross-sector") for a in candidates.values())
    missing = [topic for topic in REQUIRED_BEATS if not beats[topic]]
    research_24 = {}
    research_high = {}
    for lead in discovery:
        if not isinstance(lead,dict):
            continue
        index_time = dt(lead.get("gdelt_first_seen_utc"))
        if not index_time or index_time < cutoff or index_time > now+timedelta(hours=1):
            continue
        url=lead.get("url")
        if not url:
            continue
        research_24[url] = lead
        if lead.get("relevance_score",0)>=22:
            research_high[url] = lead
    release_rows = release_state.get("leads") if isinstance(release_state.get("leads"),list) else []
    release_links = set()
    for release in release_rows:
        if not isinstance(release,dict):
            continue
        stamp=dt(release.get("feed_published_utc"))
        uri=release.get("url")
        if uri and stamp and cutoff <= stamp <= now+timedelta(hours=1):
            release_links.add(uri)
    last_rss = dt(rss_report.get("run_utc"))
    last_discovery = dt(discovery_report.get("run_utc"))
    last_gal = dt(gal_report.get("run_utc"))
    gal_recent_ok = bool(last_gal and now-last_gal <= timedelta(minutes=25)
                         and gal_report.get("status") == "ok")
    runs = discovery_state.get("gal_runs")
    gal_coverage = (estimate_sampling_coverage(runs, now=now, hours=24)
                    if isinstance(runs, list) and runs else None)
    gal_coverage_pct = (gal_coverage["potential_coverage_upper_bound_pct"]
                        if gal_coverage else None)
    # A healthy latest poll does not repair hours of missed rolling windows.
    gal_continuity_adequate = bool(gal_coverage_pct is not None
                                  and gal_coverage_pct >= 75.0)
    connected = int(rss_report.get("feeds_connected",0) or 0)
    checked = int(rss_report.get("feeds_checked",0) or 0)
    warnings=[]
    critical=[]
    if not last_rss or now-last_rss > timedelta(hours=MAX_RUN_AGE_HOURS):
        critical.append("Official RSS collection has no recent verified run (12h threshold)")
    if checked and connected/checked < .8:
        critical.append(f"RSS connectivity below quorum: {connected}/{checked} sources (<80%)")
    elif checked and connected<checked:
        warnings.append(f"RSS source degradation: {checked-connected}/{checked} feeds failed")
    if connected == 0:
        critical.append("No publisher RSS feed successfully parsed in latest run")
    if len(candidates)==0:
        warnings.append("No high-signal timestamped leads in 24 hours; editorial coverage thin but connectivity may still be healthy")
    if 0 < len(candidates) < TARGET_CANDIDATES_24H:
        warnings.append(f"Only {len(candidates)} editorial leads within 24h; target {TARGET_CANDIDATES_24H}")
    # Geopolitical developments are event-driven. A quiet geopolitical day is
    # NOT by itself evidence of collector failure; still report the absent beat.
    daily_expected_missing=[beat for beat in missing if beat!="Geopolitics"]
    if daily_expected_missing:
        warnings.append("No observed high-signal stories in: " + ", ".join(daily_expected_missing))
    if not last_discovery:
        warnings.append("No recorded global news discovery run")
    elif now-last_discovery > timedelta(hours=MAX_RUN_AGE_HOURS):
        warnings.append("Global discovery report is older than 12h")
    elif discovery_report.get("status") not in ("ok","attempted"):
        if gal_recent_ok and gal_continuity_adequate:
            warnings.append("GDELT DOC query API is degraded or rate limited; rolling GAL backup is recently successful with measured continuity")
        elif gal_recent_ok:
            warnings.append("GDELT DOC query API is degraded or rate limited; recent GAL poll does not establish continuous coverage")
        else:
            warnings.append("Global discovery is degraded or rate limited")
    if gal_report and not gal_recent_ok:
        warnings.append("Rolling GDELT GAL sample failed or is older than 25 minutes")
    if gal_report.get("potential_sampling_gap"):
        warnings.append("A missed rolling GAL sample interval was observed")
    if gal_coverage and not gal_continuity_adequate:
        warnings.append(
            f"Rolling GAL 24h sampling continuity weak: at most {gal_coverage_pct}% "
            f"of windows potentially sampled; at least "
            f"{gal_coverage['unobserved_minutes_at_least']} minutes unobserved")
    elif gal_report and not gal_coverage:
        warnings.append("Rolling GAL sampling continuity is unmeasured; one recent poll is not 24h coverage")
    if not research_high:
        warnings.append("No high-signal global research leads first seen within 24h")
    if release_report and release_report.get("status")!="ok":
        warnings.append("Energy company-announcement feed is degraded or unavailable")
    summary={
        "audit_utc":now.isoformat(),
        "status":"critical" if critical else "degraded" if warnings else "operational_coverage_target_met",
        "official_feeds_connected":connected,
        "official_feeds_checked":checked,
        "rss_scan_state":rss_report.get("scan_state","unknown"),
        "rss_connection_ratio":round(connected/checked,3) if checked else 0,
        "official_rss_last_run_utc":rss_report.get("run_utc"),
        "timestamped_editorial_leads_24h":len(candidates),
        "official_agency_editorial_leads_24h":len(official_candidates),
        "specialist_publisher_editorial_leads_24h":len(specialist_candidates),
        "system_operator_primary_editorial_leads_24h":len(grid_operator_candidates),
        "editorial_target_24h":TARGET_CANDIDATES_24H,
        "observed_beat_counts_24h":{b:beats[b] for b in REQUIRED_BEATS},
        "unobserved_beats":missing,
        "event_driven_beats_with_no_observed_stories":[x for x in missing if x=="Geopolitics"],
        "geopolitical_energy_leads_24h":beats["Geopolitics"],
        "research_first_seen_links_24h":len(research_24),
        "research_high_signal_links_24h":len(research_high),
        "research_publisher_dates_verified":0,
        "company_announcement_links_24h":len(release_links),
        "company_announcement_feed_status":release_report.get("status","not_run"),
        "company_announcement_publisher_dates_verified":0,
        "rolling_gal_status":gal_report.get("status","not_run"),
        "rolling_gal_recent_healthy":gal_recent_ok,
        "rolling_gal_sampling_gap":bool(gal_report.get("potential_sampling_gap")),
        "rolling_gal_24h_coverage_upper_bound_pct":gal_coverage_pct,
        "rolling_gal_24h_unobserved_minutes_at_least":(
            gal_coverage["unobserved_minutes_at_least"] if gal_coverage else None),
        "rolling_gal_24h_longest_unobserved_minutes":(
            gal_coverage["longest_unobserved_minutes"] if gal_coverage else None),
        "rolling_gal_24h_continuity_adequate":gal_continuity_adequate,
        "discovery_latest_status":discovery_report.get("status","not_run"),
        "discovery_latest_run_utc":discovery_report.get("run_utc"),
        "critical":critical,
        "warnings":warnings,
        "limitations":[
            "No result proves zero market stories or comprehensive industry coverage.",
            "Editorial lead counts are distinct links, not independently verified events.",
            "GDELT first-seen times cannot establish original publisher dates.",
            "Company or newswire releases are issuer claims and their feed timestamps do not independently verify original publisher publication time.",
            "Only editorial review and independent publisher verification can approve a story.",
        ],
    }
    return summary


def report(rss_state_path, rss_report_path, discovery_state_path, discovery_report_path, output_dir, *, release_state_path=None, release_report_path=None, gal_report_path=None, now=None):
    result=audit(load_json(rss_state_path),
                 load_json(rss_report_path),
                 load_json(discovery_state_path),
                 load_json(discovery_report_path),
                 release_state=load_json(release_state_path),
                 release_report=load_json(release_report_path),
                 gal_report=load_json(gal_report_path),now=now)
    output_dir=Path(output_dir)
    output_dir.mkdir(parents=True,exist_ok=True)
    (output_dir/"health.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    lines=["# EnergyBrew Newsroom Collection Health","",
           f"Audit time: {result['audit_utc']}",
           f"Status: **{result['status']}**",
           f"Official feeds connected: **{result['official_feeds_connected']}/{result['official_feeds_checked']}**",
           f"Timestamped high-signal editorial leads (24h): **{result['timestamped_editorial_leads_24h']}** / target {TARGET_CANDIDATES_24H} (agency: {result['official_agency_editorial_leads_24h']}, grid operator: {result['system_operator_primary_editorial_leads_24h']}, specialist RSS: {result['specialist_publisher_editorial_leads_24h']})",
           f"GDELT links first seen (24h): **{result['research_first_seen_links_24h']}**, of which **{result['research_high_signal_links_24h']}** headline-score as high signal",
           "GDELT publisher-verified times: **0** (requires a separate check)",
           f"Company/newswire release leads (last 24h feed date): **{result['company_announcement_links_24h']}**",
           f"Company release provider status: **{result['company_announcement_feed_status']}**",
           f"Rolling GAL latest sample: **{result['rolling_gal_status']}** (recent success: {result['rolling_gal_recent_healthy']})",
           f"Rolling GAL 24h potential sampling coverage upper bound: **{result['rolling_gal_24h_coverage_upper_bound_pct'] if result['rolling_gal_24h_coverage_upper_bound_pct'] is not None else 'unmeasured'}%**; continuity adequate: **{result['rolling_gal_24h_continuity_adequate']}**",
           "Company release publication times and issuer claims independently verified: **0**",
           "", "## Missing coverage"]
    lines += [f"- {b}: {result['observed_beat_counts_24h'][b]} verified-source editorial leads" for b in REQUIRED_BEATS]
    lines += ["", "## Critical problems"]
    lines += ["- "+s for s in result["critical"]] or ["- None detected"]
    lines += ["", "## Warnings"]
    lines += ["- "+s for s in result["warnings"]] or ["- None detected"]
    lines += ["", "These are coverage observations, not proof of article correctness or licensing."]
    (output_dir/"health.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    return result


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--rss-state",default="state/articles.json")
    p.add_argument("--rss-run",default="output/collector/latest.json")
    p.add_argument("--discovery-state",default="state/discovery.json")
    p.add_argument("--discovery-run",default="output/discovery/latest.json")
    p.add_argument("--releases-state",default="state/press_releases.json")
    p.add_argument("--releases-run",default="output/releases/latest.json")
    p.add_argument("--gal-run",default="output/gal/latest.json")
    p.add_argument("--output",default="output/health")
    args=p.parse_args(argv)
    r=report(args.rss_state,args.rss_run,args.discovery_state,args.discovery_run,args.output,
             release_state_path=args.releases_state,release_report_path=args.releases_run,
             gal_report_path=args.gal_run)
    print(json.dumps({k:r[k] for k in ("status","official_feeds_connected",
        "timestamped_editorial_leads_24h","research_first_seen_links_24h",
        "research_high_signal_links_24h","company_announcement_links_24h",
        "critical","warnings")},indent=2))
    # Do not prevent ingestion or state persistence because editorial coverage is thin.
    return 0


if __name__=="__main__":
    raise SystemExit(main())
