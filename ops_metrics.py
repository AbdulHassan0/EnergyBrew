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

EXPECTED_GAL_MINUTES = 15
MAX_GAL_GAP_MINUTES = 20
MAX_RSS_AGE_HOURS = 12
MAX_GAL_AGE_MINUTES = 35

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
    recent=lambda d: d is not None and cutoff<=d<=now+timedelta(minutes=5)
    r_runs=sorted((a for a in rss.get("runs",[]) if isinstance(a,dict) and recent(as_time(a.get("run_utc")))),
                  key=lambda a:a["run_utc"])
    g_runs=sorted((a for a in discovery.get("gal_runs",[]) if isinstance(a,dict) and recent(as_time(a.get("run_utc")))),
                  key=lambda a:a["run_utc"])
    successful_r_runs=[x for x in r_runs if int(x.get("feeds_connected", 0) or 0) > 0]
    successful_g_runs=[x for x in g_runs if x.get("status") == "ok"]
    latest_r=as_time(successful_r_runs[-1]["run_utc"]) if successful_r_runs else None
    latest_g=as_time(successful_g_runs[-1]["run_utc"]) if successful_g_runs else None
    gal_gaps=[]
    for earlier,later in zip(successful_g_runs,successful_g_runs[1:]):
        a,b=as_time(earlier["run_utc"]),as_time(later["run_utc"])
        if a is None or b is None:
            continue
        minutes=round((b-a).total_seconds()/60,1)
        if minutes > MAX_GAL_GAP_MINUTES:
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
    official_candidates=Counter()
    for row in articles:
        stamp=as_time(row.get("published_utc"))
        if not recent(stamp):
            continue
        date=stamp.date().isoformat()
        if row.get("published_precision","timestamp")=="timestamp":
            if row.get("source_class")=="specialist_publisher":
                specialist_counts[date]+=1
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
        warnings.append(f"{len(gal_gaps)} observed GAL intervals exceeded 20 minutes")
    first_observed=min(([as_time(x["run_utc"]) for x in r_runs+g_runs if as_time(x["run_utc"])]),default=None)
    history_days=((now-first_observed).total_seconds()/86400) if first_observed else 0
    pilot_complete=history_days>=7 and all(x["successful_scanning_observed"] for x in data) and not gal_gaps
    if not pilot_complete:
        warnings.append("Seven-day operating pilot is not yet complete")
    return {
        "generated_utc":now.isoformat(),
        "status":"degraded" if any("missing" in x.lower() for x in warnings) or gal_gaps else "incomplete_pilot" if not pilot_complete else "observations_available",
        "seven_day_pilot_complete":pilot_complete,
        "history_span_days":round(history_days,2),
        "official_scan_runs":len(r_runs),"official_successful_scans":len(successful_r_runs),
        "official_failed_scans":len(r_runs)-len(successful_r_runs),
        "gal_sample_runs":len(g_runs),
        "gal_successful_samples":sum(x.get("status")=="ok" for x in g_runs),
        "gal_failed_samples":sum(x.get("status")!="ok" for x in g_runs),
        "observed_sampling_gaps":gal_gaps[-30:],
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
           f"Official RSS scans: **{r['official_scan_runs']}** (successful: {r['official_successful_scans']}, failed: {r['official_failed_scans']})",
           f"GDELT GAL samples: **{r['gal_sample_runs']}** (successful: {r['gal_successful_samples']}, degraded: {r['gal_failed_samples']})",
           f"Observed sampling gaps over 20 minutes: **{len(r['observed_sampling_gaps'])}**","",
           "| UTC day | Official scans | GAL samples | Timestamped official | Specialist RSS | High-signal official | GDELT first-seen URLs | Release-feed URLs |",
           "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for x in r["daily"]:
        lines.append(f"| {x['date_utc']} | {x['official_scans']} | {x['gal_samples']} | {x['publisher_timestamped_official_links']} | {x['specialist_publisher_timestamped_links']} | {x['high_signal_official_links']} | {x['gdelt_index_first_seen_urls']} | {x['press_release_feed_date_urls']} |")
    lines+=["","## Warnings"]+["- "+x for x in r["warnings"]]+[
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
