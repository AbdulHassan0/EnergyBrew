"""Sample GDELT's public Global Article List RSS as discovery-only backup.

GDELT GAL is an unfiltered rolling ~15-minute publisher-link firehose.
A four-times-a-day sample is INCOMPLETE coverage. No publisher timestamp,
licensed article text, fact checking, automatic publication, or subscriber mail.
"""
from __future__ import annotations
import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

from collector import article_link, child_text, clean_url, local, published_date
from discovery import _datetime, _load_state, utc_stamp
from editorial import evaluate, non_article_reason

FEED_URL = "https://data.gdeltproject.org/gdeltv3/gal/feed.rss"
MAX_BYTES = 15_000_000
MAX_RELEVANT = 400


def fetch_gal(url=FEED_URL):
    req=Request(url,headers={
        "User-Agent":"EnergyBrewResearchCollector/2.0 (+https://github.com/AbdulHassan0/EnergyBrew)",
        "Accept":"application/rss+xml, text/xml, application/xml"})
    with urlopen(req,timeout=25) as response:
        raw=response.read(MAX_BYTES+1)
        if len(raw)>MAX_BYTES:
            raise ValueError("GAL RSS exceeded 15MB limit")
        return raw,response.status


def parse_gal(xml, now):
    if len(xml)>MAX_BYTES:
        raise ValueError("GAL RSS exceeded 15MB limit")
    root=ET.fromstring(xml)
    if local(root.tag) not in ("rss","rdf","feed"):
        raise ValueError("Not an RSS/Atom document")
    nodes=[x for x in root.iter() if local(x.tag) in ("item","entry")]
    rejected={"missing_link":0,"missing_index_time":0,"stale_index_time":0,"off_topic":0,"non_article":0}
    results=[]
    for node in nodes:
        url=clean_url(article_link(node))
        title=child_text(node,("title",))[:300]
        observed=published_date(node)
        if not url or not title:
            rejected["missing_link"]+=1
            continue
        if observed is None:
            rejected["missing_index_time"]+=1
            continue
        if observed>now+timedelta(hours=1) or observed<now-timedelta(hours=48):
            rejected["stale_index_time"]+=1
            continue
        if non_article_reason(title, url):
            rejected["non_article"]+=1
            continue
        quality=evaluate(title)
        if not quality["editorial_candidate"]:
            rejected["off_topic"]+=1
            continue
        results.append({
            "url":url,"title":title,
            "domain":url.split("/")[2].lower(),
            "gdelt_first_seen_utc":utc_stamp(observed),
            "index_timestamp_source":"GAL RSS pubDate (not publisher publication date)",
            "publisher_published_utc":None,
            "published_time_verified":False,
            "discovery_provider":"GDELT GAL RSS",
            "discovery_topic":"gal_rolling_sample",
            "topics":["gal_rolling_sample"],
            "relevance_score":quality["relevance_score"],
            "category":quality["category"],
            "relevance_evidence":quality["evidence"],
            "status":"discovery_only_requires_publisher_verification",
        })
    results.sort(key=lambda x:(x["relevance_score"],x["gdelt_first_seen_utc"]),reverse=True)
    return results[:MAX_RELEVANT],rejected,len(nodes)


def collect_gal(state_path, outdir, *, now=None, fetcher=None):
    now=now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now must include timezone")
    fetcher=fetcher or fetch_gal
    state=_load_state(state_path)
    previously=state.get("leads",[])
    by_url={}
    historical_noise_removed=0
    historical_rescored=0
    for raw in previously:
        if not isinstance(raw,dict) or not raw.get("url"):
            continue
        item=dict(raw)
        if non_article_reason(item.get("title",""),item.get("url","")):
            historical_noise_removed+=1
            continue
        quality=evaluate(item.get("title",""))
        # GAL's high-signal queue must not retain entries that the current
        # classifier no longer considers articles or sector-relevant.
        # DOC search leads stay in its broader research queue even if low score.
        if (item.get("discovery_provider") == "GDELT GAL RSS" and
                not quality["editorial_candidate"] and
                "GDELT DOC 2.0" not in item.get("discovery_providers", [])):
            historical_noise_removed+=1
            continue
        if item.get("relevance_score") != quality["relevance_score"]:
            historical_rescored+=1
        item["category"]=quality["category"]
        item["relevance_score"]=quality["relevance_score"]
        item["relevance_evidence"]=quality["evidence"]
        # Indexer first-seen time is not publisher publication time,
        # even if the stored record was written by an older scoring version.
        item["publisher_published_utc"]=None
        item["published_time_verified"]=False
        by_url[item["url"]]=item
    previous_runs=state.get("gal_runs",[])
    last_attempt=max((_datetime(x.get("run_utc")) for x in previous_runs if _datetime(x.get("run_utc"))),default=None)
    interval_minutes=round((now-last_attempt).total_seconds()/60,1) if last_attempt else None
    summary={"run_utc":utc_stamp(now),"provider":"GDELT GAL RSS",
             "minutes_since_previous_sample":interval_minutes,
             "potential_sampling_gap":bool(interval_minutes is not None and interval_minutes>20),
             "coverage":"rolling_15min_sample_only_not_full_day",
             "status":"pending","raw_feed_items":0,"high_signal_items":0,
             "new_unique_links":0,"rejected":{},
             "historical_noise_removed":historical_noise_removed,
             "historical_rescored":historical_rescored}
    try:
        payload,status=fetcher(FEED_URL)
        if not 200<=status<300:
            raise ValueError(f"GAL returned HTTP {status}")
        parsed,rejected,raw_count=parse_gal(payload,now)
        summary.update(status="ok",raw_feed_items=raw_count,
                       high_signal_items=len(parsed),rejected=rejected,http_status=status)
        for lead in parsed:
            uri=lead["url"]
            if uri in by_url:
                prior=by_url[uri]
                topics=set(prior.get("topics",[]))
                topics.add("gal_rolling_sample")
                prior["topics"]=sorted(topics)
                providers=set(prior.get("discovery_providers",[]))
                providers.add(prior.get("discovery_provider","unknown"))
                providers.add("GDELT GAL RSS")
                prior["discovery_providers"]=sorted(providers)
                # Always use the latest scorer, not a historical inflated maximum.
                # Different providers may find the same URL under multiple beats.
                quality=evaluate(prior.get("title") or lead["title"])
                prior["relevance_score"]=quality["relevance_score"]
                prior["category"]=quality["category"]
                prior["relevance_evidence"]=quality["evidence"]
            else:
                by_url[uri]=lead
                summary["new_unique_links"]+=1
    except Exception as exc:
        summary.update(status="degraded",error=f"{type(exc).__name__}: {str(exc)[:200]}")
    cutoff=now-timedelta(days=7)
    retained=[v for v in by_url.values() if
              (_datetime(v.get("gdelt_first_seen_utc")) or datetime.min.replace(tzinfo=timezone.utc))>=cutoff]
    retained.sort(key=lambda x:(x.get("relevance_score",0),x["gdelt_first_seen_utc"]),reverse=True)
    retained=retained[:4000]
    recent=[x for x in retained if (_datetime(x.get("gdelt_first_seen_utc")) or cutoff) >= now-timedelta(hours=24)]
    summary["combined_research_leads_24h"]=len(recent)
    state["leads"]=retained
    state.setdefault("gal_runs",[]).append({k:summary[k] for k in
        ("run_utc","status","raw_feed_items","high_signal_items","new_unique_links")})
    state["gal_runs"]=[r for r in state["gal_runs"] if
        (_datetime(r.get("run_utc")) or cutoff)>=cutoff][-800:]
    outdir=Path(outdir)
    outdir.mkdir(parents=True,exist_ok=True)
    state_path.parent.mkdir(parents=True,exist_ok=True)
    temp=state_path.with_suffix(".tmp")
    temp.write_text(json.dumps(state,indent=2)+"\n",encoding="utf-8")
    temp.replace(state_path)
    (outdir/"latest.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
    (outdir/"leads_7d.json").write_text(json.dumps(retained,indent=2)+"\n",encoding="utf-8")
    (outdir/"leads_24h.json").write_text(json.dumps(recent,indent=2)+"\n",encoding="utf-8")
    lines=[
        "# GDELT Global Article List — sampled backup", "",
        f"Run: {summary['run_utc']}",
        f"Status: **{summary['status']}**",
        f"RSS entries examined: **{summary['raw_feed_items']}**",
        f"High-signal sampled entries: **{summary['high_signal_items']}**",
        f"Minutes since previous scheduled sample: **{summary['minutes_since_previous_sample']}**",
        f"Potential gap in rolling feed sampling: **{summary['potential_sampling_gap']}**",
        f"New unique URLs in research state: **{summary['new_unique_links']}**",
        f"Previously stored non-article pages removed: **{summary['historical_noise_removed']}**",
        f"Previously stored scores corrected: **{summary['historical_rescored']}**",
        "", "This is a rolling 15-minute SAMPLE only, not full daily source coverage.",
        "Dates are supplied by the GDELT RSS index, NOT independently verified publisher publication times.",
        "No external article pages were scraped or republished.",
    ]
    if summary.get("error"):
        lines.append("Error: "+summary["error"])
    (outdir/"latest.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    return summary


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--state",default="state/discovery.json")
    p.add_argument("--output",default="output/gal")
    args=p.parse_args(argv)
    report=collect_gal(Path(args.state),Path(args.output))
    print(json.dumps(report,indent=2))
    return 0 if report["status"]=="ok" else 2


if __name__=="__main__":
    raise SystemExit(main())
