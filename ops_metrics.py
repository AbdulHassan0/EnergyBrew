"""Operational measurement for the independent EnergyBrew news collection services.

Counts source-linked observations, not independent verified market events.
A day with no observations is explicitly unknown unless scanning actually ran.
"""
from __future__ import annotations
import argparse
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from research_desk import as_time

EXPECTED_GAL_MINUTES = 10
MAX_GAL_GAP_MINUTES = 15
MAX_RSS_AGE_HOURS = 12
MAX_GAL_AGE_MINUTES = 25
MIN_FEED_RATIO = 0.8

def read_state(path):
    try:
        obj=json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(obj,dict):
            return {}
        return obj
    except (OSError,ValueError,TypeError):
        return {}

def create(rss, discovery, releases=None, *, now=None):
    now=now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now requires a timezone")
    rss=rss if isinstance(rss,dict) else {}
    discovery=discovery if isinstance(discovery,dict) else {}
    releases=releases if isinstance(releases,dict) else {}
    cutoff=now-timedelta(days=7)
    history_cutoff=now-timedelta(days=8)
    recent=lambda d: d is not None and cutoff<=d<=now+timedelta(minutes=5)
    recent_run=lambda d: d is not None and history_cutoff<=d<=now+timedelta(minutes=5)
    r_runs=sorted((a for a in rss.get("runs",[]) if isinstance(a,dict) and recent_run(as_time(a.get("run_utc")))),
                  key=lambda a:a["run_utc"])
    g_runs=sorted((a for a in discovery.get("gal_runs",[]) if isinstance(a,dict) and recent_run(as_time(a.get("run_utc")))),
                  key=lambda a:a["run_utc"])
    def rss_above_quorum(run):
        connected=int(run.get("feeds_connected",0) or 0)
        checked=int(run.get("feeds_checked",0) or connected)
        return (connected>0 and checked>0 and connected / checked >= MIN_FEED_RATIO
                and run.get("scan_state")!="critical")
    successful_r_runs=[x for x in r_runs if rss_above_quorum(x)]
    fully_connected_r_runs=[x for x in r_runs if x.get("feeds_connected",0)>0
                             and x.get("feeds_connected")==x.get("feeds_checked",x.get("feeds_connected"))]
    successful_g_runs=[x for x in g_runs if x.get("status") == "ok"]
    latest_r=as_time(successful_r_runs[-1]["run_utc"]) if successful_r_runs else None
    latest_g=as_time(successful_g_runs[-1]["run_utc"]) if successful_g_runs else None
    gal_gaps=[]
    for earlier,later in zip(successful_g_runs,successful_g_runs[1:]):
        a,b=as_time(earlier["run_utc"]),as_time(later["run_utc"])
        if a is None or b is None:
            continue
        minutes=round((b-a).total_seconds()/60,1)
        if minutes > MAX_GAL_GAP_MINUTES and b >= cutoff:
            gal_gaps.append({"from_utc":a.isoformat(),"to_utc":b.isoformat(),"minutes":minutes})
    articles=[x for x in rss.get("articles",[]) if isinstance(x,dict)]
    leads=[x for x in discovery.get("leads",[]) if isinstance(x,dict)]
    pr=[x for x in releases.get("leads",[]) if isinstance(x,dict)]
    days=[(now.date()-timedelta(days=i)).isoformat() for i in range(6,-1,-1)]
    r_scan=Counter(as_time(x.get("run_utc")).date().isoformat() for x in r_runs if as_time(x.get("run_utc")))
    g_scan=Counter(as_time(x.get("run_utc")).date().isoformat() for x in g_runs if as_time(x.get("run_utc")))
    r_success=Counter(as_time(x["run_utc"]).date().isoformat() for x in successful_r_runs)
    g_success=Counter(as_time(x["run_utc"]).date().isoformat() for x in successful_g_runs)
    article_counts=Counter()
    specialist_counts=Counter()
    grid_operator_counts=Counter()
    official_candidates=Counter()
    for row in articles:
        stamp=as_time(row.get("published_utc"))
        if not recent(stamp):
            continue
        date=stamp.date().isoformat()
        if row.get("published_precision","timestamp")=="timestamp":
            if row.get("source_class")=="specialist_publisher":
                specialist_counts[date]+=1
            elif row.get("source_class")=="system_operator_primary":
                grid_operator_counts[date]+=1
            else:
                article_counts[date]+=1
                if row.get("editorial_candidate") is True:
                    official_candidates[date]+=1
    discovery_links={}
    for row in leads:
        stamp=as_time(row.get("gdelt_first_seen_utc"))
        uri=row.get("url")
        if recent(stamp) and uri:
            discovery_links[uri]=stamp.date().isoformat()
    index_counts=Counter(discovery_links.values())
    release_links={}
    for row in pr:
        stamp=as_time(row.get("feed_published_utc"))
        uri=row.get("url")
        if recent(stamp) and uri:
            release_links[uri]=stamp.date().isoformat()
    release_counts=Counter(release_links.values())
    data=[{"date_utc":d,"official_scans":r_scan[d],"gal_samples":g_scan[d],
           "publisher_timestamped_official_links":article_counts[d],
           "specialist_publisher_timestamped_links":specialist_counts[d],
           "grid_operator_primary_timestamped_links":grid_operator_counts[d],
           "high_signal_official_links":official_candidates[d],
           "gdelt_index_first_seen_urls":index_counts[d],
           "press_release_feed_date_urls":release_counts[d],
           "scanning_observed":bool(r_scan[d] or g_scan[d]),
           "successful_official_scans":r_success[d], "successful_gal_samples":g_success[d],
           "successful_scanning_observed":bool(r_success[d] and g_success[d])} for d in days]
    warnings=[]
    if not latest_r or now-latest_r>timedelta(hours=MAX_RSS_AGE_HOURS):
        warnings.append("Official RSS scan missing or older than 12 hours")
    if not latest_g or now-latest_g>timedelta(minutes=MAX_GAL_AGE_MINUTES):
        warnings.append("GDELT rolling-feed sample missing or older than 35 minutes")
    if gal_gaps:
        warnings.append(f"{len(gal_gaps)} observed GAL intervals exceeded {MAX_GAL_GAP_MINUTES} minutes")
    if len(fully_connected_r_runs)<len(r_runs):
        warnings.append(f"{len(r_runs)-len(fully_connected_r_runs)} RSS scans had incomplete source connectivity")
    successful_g_in_window=[as_time(r["run_utc"]) for r in successful_g_runs
                            if as_time(r["run_utc"]) and as_time(r["run_utc"])>=cutoff]
    start_gap=round((successful_g_in_window[0]-cutoff).total_seconds()/60,1) if successful_g_in_window else None
    tail_gap=round((now-successful_g_in_window[-1]).total_seconds()/60,1) if successful_g_in_window else None
    first_observed=min(([as_time(x["run_utc"]) for x in r_runs+g_runs if as_time(x["run_utc"])]),default=None)
    history_days=((now-first_observed).total_seconds()/86400) if first_observed else 0
    pilot_complete=(history_days>=7
                    and all(x["successful_scanning_observed"] for x in data)
                    and not gal_gaps and len(fully_connected_r_runs)==len(r_runs)
                    and start_gap is not None and start_gap<=MAX_GAL_GAP_MINUTES
                    and tail_gap is not None and tail_gap<=MAX_GAL_GAP_MINUTES)
    if history_days>=7 and (start_gap is None or start_gap>MAX_GAL_GAP_MINUTES):
        warnings.append("Seven-day GAL pilot start has an unobserved index window")
    if tail_gap is not None and tail_gap>MAX_GAL_GAP_MINUTES:
        warnings.append("Latest GAL successful sample exceeds rolling index window")
    if not pilot_complete:
        warnings.append("Seven-day operating pilot is not yet complete")
    source_health=rss.get("source_health",{})
    source_health=source_health if isinstance(source_health,dict) else {}
    failing_sources=sorted([
        {"source":name,"consecutive_failures":row.get("consecutive_failures",0),
         "last_success_utc":row.get("last_success_utc"),"last_error_type":row.get("last_error_type")}
        for name,row in source_health.items()
        if isinstance(row,dict) and row.get("consecutive_failures",0)>0
    ], key=lambda x:(-x["consecutive_failures"],x["source"]))
    return {
        "generated_utc":now.isoformat(),
        "status":"degraded" if any(("missing" in x.lower() or "incomplete source" in x.lower() or "unobserved index" in x.lower() or "exceeds rolling" in x.lower()) for x in warnings) or gal_gaps else "incomplete_pilot" if not pilot_complete else "observations_available",
        "seven_day_pilot_complete":pilot_complete,
        "history_span_days":round(history_days,2),
        "official_scan_runs":len(r_runs),"official_successful_scans":len(successful_r_runs),
        "official_fully_connected_scans":len(fully_connected_r_runs),
        "failing_sources":failing_sources,
        "official_failed_scans":len(r_runs)-len(successful_r_runs),
        "gal_sample_runs":len(g_runs),
        "gal_successful_samples":sum(x.get("status")=="ok" for x in g_runs),
        "gal_failed_samples":sum(x.get("status")!="ok" for x in g_runs),
        "observed_sampling_gaps":gal_gaps[-30:],
        "seven_day_start_gap_minutes":start_gap,
        "latest_gal_age_minutes":tail_gap,
        "expected_gal_interval_minutes":EXPECTED_GAL_MINUTES,
        "latest_official_scan_utc":latest_r.isoformat() if latest_r else None,
        "latest_official_attempt_utc":as_time(r_runs[-1]["run_utc"]).isoformat() if r_runs else None,
        "latest_gal_attempt_utc":as_time(g_runs[-1]["run_utc"]).isoformat() if g_runs else None,
        "latest_gal_sample_utc":latest_g.isoformat() if latest_g else None,
        "daily":data,
        "warnings":warnings,
        "definitions":"Article totals are source links, GAL totals are index-first-seen links. Neither measures independently verified news events. Blank scan history does not mean zero energy stories."
    }

def report(rss_path, discovery_path, releases_path, outdir, *, now=None):
    r=create(read_state(rss_path),read_state(discovery_path),read_state(releases_path),now=now)
    out=Path(outdir)
    out.mkdir(parents=True,exist_ok=True)
    (out/"metrics.json").write_text(json.dumps(r,indent=2)+"\n",encoding="utf-8")
    lines=["# EnergyBrew collection reliability and volume","",
           f"Generated: {r['generated_utc']}",
           f"Status: **{r['status']}**",
           f"Seven-day pilot complete: **{r['seven_day_pilot_complete']}**",
           f"Observed history span: **{r['history_span_days']} days**",
           f"RSS scans: **{r['official_scan_runs']}** (above 80% feed quorum: {r['official_successful_scans']}, all feeds connected: {r['official_fully_connected_scans']}, below quorum: {r['official_failed_scans']})",
           f"GDELT GAL samples: **{r['gal_sample_runs']}** (successful: {r['gal_successful_samples']}, degraded: {r['gal_failed_samples']})",
           f"GDELT intervals longer than {MAX_GAL_GAP_MINUTES} minutes: **{len(r['observed_sampling_gaps'])}**",
           f"Gap from seven-day window start to first GAL sample: **{r['seven_day_start_gap_minutes']} min**",
           f"Age of latest successful GAL sample: **{r['latest_gal_age_minutes']} min**","",
           "| UTC day | Official scans | GAL samples | Timestamped agency | Specialist RSS | Grid operator | High-signal agency | GDELT first-seen URLs | Release-feed URLs |",
           "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for x in r["daily"]:
        lines.append(f"| {x['date_utc']} | {x['official_scans']} | {x['gal_samples']} | {x['publisher_timestamped_official_links']} | {x['specialist_publisher_timestamped_links']} | {x['grid_operator_primary_timestamped_links']} | {x['high_signal_official_links']} | {x['gdelt_index_first_seen_urls']} | {x['press_release_feed_date_urls']} |")
    lines+=["","## Individual feed failures"] + ([
        f"- {x['source']}: {x['consecutive_failures']} consecutive failures; last successful scan: {x['last_success_utc'] or 'never'}"
        for x in r["failing_sources"]] or ["- None in latest state"]) + [
        "", "## Warnings"] + ["- "+x for x in r["warnings"]]+[
        "","No scan activity is **unknown coverage**, not proof that no market news occurred.",
        "GDELT RSS timestamps reflect index observations, not original publication dates.",
        "Even complete scan history is not proof of complete industry coverage."]
    (out/"metrics.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    return r

def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--rss",default="state/articles.json")
    p.add_argument("--discovery",default="state/discovery.json")
    p.add_argument("--releases",default="state/press_releases.json")
    p.add_argument("--output",default="output/operations")
    args=p.parse_args(argv)
    r=report(args.rss,args.discovery,args.releases,args.output)
    print(json.dumps({k:r[k] for k in ("status","seven_day_pilot_complete","official_scan_runs","gal_sample_runs","warnings")},indent=2))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
