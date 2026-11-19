"""Compile source-linked, authored briefs into a six-beat EnergyBrew pilot.

This is NOT an LLM or article scraper. Every news summary and market impact
must be supplied in the briefs input. Missing source identity or original
copy blocks the edition; a headline alone never becomes a fabricated brief.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from newsletter import (EditorialError, MAX_ARTICLES, TOPICS,
                        valid_url, word_count, render_html, render_text)
from pilot_audit import _key, _publisher_domain, audit_pilot
from research_desk import as_time


def _source_index(desk, raw_sources):
    indexed={}
    for row in desk.get("stories", []):
        if isinstance(row, dict) and _key(row.get("url")):
            indexed.setdefault(_key(row["url"]), []).append(row)
    for lane,records in raw_sources.items():
        if lane not in ("rss","discovery","releases") or not isinstance(records,list):
            raise EditorialError("Invalid research source lane")
        for row in records:
            if isinstance(row,dict) and _key(row.get("url")):
                indexed.setdefault(_key(row["url"]), []).append(row)
    return indexed


def compile_pilot(desk, brief_bank, *, raw_sources=None, now=None):
    """Assemble only complete authored briefs matched to stored news URLs."""
    now=now or datetime.now(timezone.utc)
    if now.utcoffset() is None:
        raise EditorialError("Compilation clock requires a timezone")
    if not isinstance(desk,dict) or not isinstance(desk.get("stories"),list):
        raise EditorialError("Missing saved research desk")
    generated=as_time(desk.get("generated_utc"))
    if generated is None or generated>now+timedelta(minutes=5) or now-generated>timedelta(hours=24):
        raise EditorialError("Research desk is missing or stale: no daily pilot compilation")
    if not isinstance(brief_bank,dict) or not isinstance(brief_bank.get("briefs"),list):
        raise EditorialError("Briefs file requires a briefs array")
    date_value=brief_bank.get("edition_date")
    try:
        day=datetime.strptime(date_value,"%Y-%m-%d").date()
    except (ValueError,TypeError) as exc:
        raise EditorialError("Brief bank needs a real edition date") from exc
    if day.isoformat()!=date_value:
        raise EditorialError("Edition date must be canonical YYYY-MM-DD")
    source_index=_source_index(desk,raw_sources or {})
    candidates=[]
    seen=set()
    rejected=[]
    for i,entry in enumerate(brief_bank["briefs"],1):
        if not isinstance(entry,dict):
            rejected.append(f"Brief {i} is not an object")
            continue
        url=entry.get("source_url")
        key=_key(url)
        if not valid_url(url) or not key:
            rejected.append(f"Brief {i} has an invalid source URL")
            continue
        if key in seen:
            rejected.append(f"Brief {i} repeats a source URL")
            continue
        seen.add(key)
        if key not in source_index:
            rejected.append(f"Brief {i} has no matching saved publisher/index source: {url}")
            continue
        section=entry.get("section")
        if section not in TOPICS:
            rejected.append(f"Brief {i} has an invalid energy section")
            continue
        for field,lo,hi in (("title",3,45),("summary",18,110),
                            ("why_it_matters",8,65)):
            if not lo<=word_count(entry.get(field))<=hi:
                rejected.append(f"Brief {i} must supply substantive {field} copy")
                break
        else:
            if not isinstance(entry.get("source_date"),str):
                rejected.append(f"Brief {i} requires original publisher date, not GDELT time")
                continue
            priority=entry.get("priority",50)
            if isinstance(priority,bool) or not isinstance(priority,(int,float)) or not 0<=priority<=100:
                rejected.append(f"Brief {i} has invalid 0-100 priority")
                continue
            candidates.append({
                "section":section,"source_url":url,
                "title":str(entry["title"]).strip(),
                "summary":str(entry["summary"]).strip(),
                "why_it_matters":str(entry["why_it_matters"]).strip(),
                "source_date":entry["source_date"],
                "publisher":str(entry.get("publisher") or
                    source_index[key][0].get("source") or
                    source_index[key][0].get("domain") or
                    _publisher_domain(url))[:100],
                "_priority":priority,
            })
    if rejected:
        raise EditorialError("Invalid source-backed brief intake:\n- "+"\n- ".join(rejected))
    candidates.sort(key=lambda x:(-x["_priority"],x["source_url"]))
    picked=[]
    selected=set()
    domain_counts=Counter()
    beat_counts=Counter()

    def choose(item):
        key=_key(item["source_url"])
        domain=_publisher_domain(item["source_url"])
        beat=item["section"]
        if key in selected or domain_counts[domain]>=3 or beat_counts[beat]>=2:
            return False
        selected.add(key)
        beat_counts[beat]+=1
        domain_counts[domain]+=1
        picked.append({k:v for k,v in item.items() if not k.startswith("_")})
        return True

    for beat in TOPICS:
        for item in candidates:
            if item["section"]==beat and choose(item):
                break
    missing=[beat for beat in TOPICS if beat_counts[beat]==0]
    if missing:
        raise EditorialError("Insufficient authored evidence for: "+", ".join(missing))
    for item in candidates:
        if len(picked)>=MAX_ARTICLES:
            break
        choose(item)
    intro=brief_bank.get("intro") or (
        "Good morning. Here are the energy developments worth knowing "
        "before your coffee gets cold.")
    issue={
        "schema_version":1,
        "edition_date":day.isoformat(),
        "status":"pilot",
        "headline":"Your daily shot of energy.",
        "intro":intro,
        "stories":picked,
        "notice":"Source-linked authored pilot copy only; no fact-check attestation, no email send.",
        "compilation_mode":"authored_briefs_matched_to_persisted_news_sources",
        "research_snapshot_utc":desk["generated_utc"],
    }
    quality=audit_pilot(issue,desk,raw_sources=raw_sources or {})
    if quality["errors"]:
        raise EditorialError("Pilot compilation quality blocked: "+"; ".join(quality["errors"]))
    return issue,quality


def read_lane(path,field):
    if path is None:
        return []
    obj=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj,dict) or not isinstance(obj.get(field),list):
        raise EditorialError("Invalid retained source state: "+str(path))
    return obj[field]


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--desk",type=Path,required=True)
    p.add_argument("--briefs",type=Path,required=True)
    p.add_argument("--rss",type=Path)
    p.add_argument("--discovery",type=Path)
    p.add_argument("--releases",type=Path)
    p.add_argument("--out",type=Path,required=True)
    args=p.parse_args(argv)
    desk=json.loads(args.desk.read_text(encoding="utf-8"))
    brief_bank=json.loads(args.briefs.read_text(encoding="utf-8"))
    raw={"rss":read_lane(args.rss,"articles"),
         "discovery":read_lane(args.discovery,"leads"),
         "releases":read_lane(args.releases,"leads")}
    issue,quality=compile_pilot(desk,brief_bank,raw_sources=raw)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(issue,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({
        "status":quality["status"],"stories":quality["total_stories"],
        "six_beats_present":quality["six_beats_present"],
        "cutoff_collection_evidence":quality["cutoff_collection_evidence"],
        "delivery":"disabled",
    },indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
