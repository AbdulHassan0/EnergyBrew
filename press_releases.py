"""Corporate energy press-release discovery via Press Release Feed (metadata only).

Provider explicitly documents open RSS integration. These are issuer claims,
NOT independent news verification. Time is the aggregator's RSS published date,
NOT independently checked original-publisher publication time. Store only
headlines, original source URLs, issuer metadata, and indexing diagnostics.
"""
from __future__ import annotations
import argparse
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

from collector import MAX_BYTES, clean_url, child_text, local, published_date
from editorial import evaluate, non_article_reason

def promotional_non_energy(title):
    """Marketing vendors addressing energy companies are not energy events."""
    t=(title or "").lower()
    return any(word in t for word in (
        "seo and ai search","seo services","search engine optimization",
        "marketing services","social media marketing",
        "online marketing agency","digital marketing agency",
        "launches new website","press release distribution service",
    ))

URL="https://pressreleasefeed.org/feed.xml?topic=energy&language=en&limit=100"
AGENT="EnergyBrewResearchCollector/2.0 (+https://github.com/AbdulHassan0/EnergyBrew)"


def fetch_feed(url=URL):
    req=Request(url,headers={"User-Agent":AGENT, "Accept":"application/rss+xml, text/xml, application/xml"})
    with urlopen(req,timeout=25) as resp:
        data=resp.read(MAX_BYTES+1)
        if len(data)>MAX_BYTES:
            raise ValueError("Energy press-release feed too large")
        return data,resp.status


def parse_releases(xml, now):
    root=ET.fromstring(xml)
    if local(root.tag) not in ("rss","rdf","feed"):
        raise ValueError("Energy press-release provider returned non-RSS data")
    nodes=[n for n in root.iter() if local(n.tag) in ("item","entry")]
    results=[]
    skipped={"missing_original_source_url":0, "missing_feed_timestamp":0,
             "outside_window":0, "off_topic":0,"non_article":0,
             "marketing_only":0}
    for node in nodes:
        title=child_text(node,("title",))[:300]
        # The RSS <link> points to the aggregator; <source url="...">
        # points to the original issuer/newswire release.
        original=""
        issuer=child_text(node,("creator",))
        for ch in node:
            if local(ch.tag)=="source":
                original=clean_url(ch.attrib.get("url") or "")
                if not issuer:
                    issuer=(ch.text or "").strip()[:160]
                break
        if not title or not original:
            skipped["missing_original_source_url"]+=1
            continue
        if non_article_reason(title,original):
            skipped["non_article"]+=1
            continue
        if promotional_non_energy(title):
            skipped["marketing_only"]+=1
            continue
        observed=published_date(node)
        if observed is None:
            skipped["missing_feed_timestamp"]+=1
            continue
        if observed>now+timedelta(hours=1) or observed<now-timedelta(hours=48):
            skipped["outside_window"]+=1
            continue
        quality=evaluate(title)
        if not quality["editorial_candidate"]:
            skipped["off_topic"]+=1
            continue
        results.append({
            "url":original,
            "title":title,
            "feed_creator_label":issuer[:160],
            "named_issuer_verified":False,
            "feed_source_url":original,
            "feed_source_url_may_be_newsroom_or_wire_mirror":True,
            "feed_published_utc":observed.isoformat(),
            "publisher_published_utc":None,
            "published_time_verified":False,
            "category":quality["category"],
            "relevance_score":quality["relevance_score"],
            "relevance_evidence":quality["evidence"],
            "provider":"Press Release Feed",
            "content_kind":"company_or_newswire_press_release",
            "status":"promotional_issuer_claim_requires_editorial_verification",
        })
    return results,skipped,len(nodes)


def collect(state_file,outdir,*,now=None,fetcher=None,completion_clock=None):
    injected_clock=now is not None
    now=now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now must be timezone aware")
    fetcher=fetcher or fetch_feed
    if state_file.exists():
        try:
            saved=json.loads(state_file.read_text(encoding="utf-8"))
        except (ValueError,OSError) as exc:
            raise ValueError("Cannot read existing press-release history; refusing overwrite") from exc
        if not isinstance(saved,dict) or not isinstance(saved.get("leads"),list):
            raise ValueError("Invalid press-release history schema; refusing overwrite")
    else:
        saved={"leads":[],"runs":[]}
    old={x["url"]:dict(x) for x in saved["leads"] if isinstance(x,dict) and x.get("url")}
    # Re-score old records on every run, discarding obvious nonarticle pages.
    for uri in list(old):
        item=old[uri]
        if non_article_reason(item.get("title",""),uri) or promotional_non_energy(item.get("title","")):
            del old[uri]
            continue
        q=evaluate(item.get("title",""))
        item["relevance_score"]=q["relevance_score"]
        item["category"]=q["category"]
        item["relevance_evidence"]=q["evidence"]
        item["published_time_verified"]=False
        item["publisher_published_utc"]=None
        item["named_issuer_verified"]=False
        item["feed_creator_label"]=item.pop("issuer",item.get("feed_creator_label",""))
        item["feed_source_url_may_be_newsroom_or_wire_mirror"]=True
    observed_urls=set()
    r={"run_utc":now.isoformat(), "status":"pending", "provider":"Press Release Feed",
       "raw_feed_entries":0,"high_signal_company_releases":0,"new_unique_links":0,
       "error":None,"skipped":{}}
    try:
        response,status=fetcher(URL)
        if status!=200:
            raise ValueError(f"Release RSS HTTP {status}")
        records,skips,count=parse_releases(response,now)
        r.update(status="ok",raw_feed_entries=count,
                 high_signal_company_releases=len(records),skipped=skips,http_status=status)
        for item in records:
            if item["url"] not in old:
                r["new_unique_links"]+=1
            else:
                previous_first = old[item["url"]].get("first_collector_observed_utc")
                if previous_first:
                    item["first_collector_observed_utc"]=previous_first
            observed_urls.add(item["url"])
            old[item["url"]]=item
    except Exception as exc:
        r.update(status="degraded",error=f"{type(exc).__name__}: {str(exc)[:200]}")
    completed = (completion_clock() if completion_clock else
                 now if injected_clock else datetime.now(timezone.utc))
    if completed.tzinfo is None or completed.utcoffset() is None:
        raise ValueError("Issuer collection completion clock requires timezone")
    r["completed_utc"] = completed.astimezone(timezone.utc).isoformat()
    if r["status"] == "ok":
        for uri in observed_urls:
            old[uri].setdefault("first_collector_observed_utc",
                                r["completed_utc"])
    cutoff=now-timedelta(days=7)
    def stamp(x):
        try:
            dt=datetime.fromisoformat(x["feed_published_utc"])
            return dt.astimezone(timezone.utc) if dt.tzinfo else None
        except (KeyError,ValueError,TypeError):
            return None
    all_leads=[v for v in old.values() if stamp(v) and cutoff<=stamp(v)<=now+timedelta(hours=1)]
    all_leads.sort(key=lambda x:(x["feed_published_utc"],x["relevance_score"]),reverse=True)
    recent=[v for v in all_leads if stamp(v)>=now-timedelta(hours=24)]
    r["company_release_leads_24h"]=len(recent)
    r["company_release_leads_7d"]=len(all_leads)
    saved["leads"]=all_leads[:2000]
    saved.setdefault("runs",[]).append({k:r[k] for k in
        ("run_utc","completed_utc","status","raw_feed_entries","high_signal_company_releases","new_unique_links")})
    saved["runs"]=saved["runs"][-100:]
    state_file.parent.mkdir(parents=True,exist_ok=True)
    outdir.mkdir(parents=True,exist_ok=True)
    tmp=state_file.with_suffix(".tmp")
    tmp.write_text(json.dumps(saved,indent=2)+"\n",encoding="utf-8")
    tmp.replace(state_file)
    for name,data in [("latest.json",r),("leads_24h.json",recent),("leads_7d.json",saved["leads"])]:
        (outdir/name).write_text(json.dumps(data,indent=2)+"\n",encoding="utf-8")
    lines=[
        "# EnergyBrew energy company announcements (unverified)", "",
        "Provider: Press Release Feed. This source aggregates company and newswire press releases.",
        f"Run: {r['run_utc']} | Status: **{r['status']}**",
        f"Feed records: **{r['raw_feed_entries']}** | Energy-score matches: **{r['high_signal_company_releases']}**",
        f"New unique original-source links: **{r['new_unique_links']}**",
        f"Release research leads in the 24-hour feed-date window: **{r['company_release_leads_24h']}**",
        "", "Newswire/creator labels are not verified issuer identities.",
        "Company or newswire claims are NOT independently fact-checked reporting.",
        "Feed-provided dates are NOT independently checked original publisher publication times.",
        "Store only metadata and original source links; do not reuse publisher bodies or images.",
    ]
    if r["error"]:
        lines.append("Error: "+r["error"])
    (outdir/"latest.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    return r


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--state",default="state/press_releases.json")
    p.add_argument("--output",default="output/releases")
    args=p.parse_args(argv)
    r=collect(Path(args.state),Path(args.output))
    print(json.dumps(r,indent=2))
    return 0 if r["status"]=="ok" else 2


if __name__=="__main__":
    raise SystemExit(main())
