"""Auditable six-beat morning source evidence and empty writing handoff.

Research only. A source title or GDELT discovery is never sufficient to
create a factual news summary or claim editorial approval. The packet
distinguishes publisher-dated items, date-only notices, discovery-index links,
unverified issuer claims, and unknown first-collection times.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from newsletter import TOPICS, valid_url
from research_desk import as_time, entry

ZONE = "America/Chicago"
PER_BEAT_LIMIT = 3
KIND_RANK = {"publisher_rss": 4, "regulatory_date_only": 3,
             "global_discovery": 2, "issuer_claim": 1}
BUCKETS = ("publisher_rss", "regulatory_date_only",
           "global_discovery", "issuer_claim", "unknown_collection_time")


def _validated_day(value):
    if value is None:
        return None
    if isinstance(value,date) and not isinstance(value,datetime):
        return value
    if not isinstance(value,str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}",value):
        raise ValueError("Edition date must be YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("Edition date must exist") from exc


def _source_rows(state, key):
    if not isinstance(state,dict):
        raise ValueError("News state must be a JSON object")
    rows=state.get(key,[])
    if not isinstance(rows,list):
        raise ValueError("News source records must be a JSON array: "+key)
    return rows


def _identity(raw):
    if not valid_url(raw):
        return ""
    parts=urlsplit(raw)
    return (parts.hostname or "").lower()+parts.path.rstrip("/")+("?" + parts.query if parts.query else "")


def _md_label(raw):
    # Publisher-controlled headlines must not inject Markdown headings,
    # images, tags, pipes or additional article links into a research packet.
    return re.sub(r"\s+"," ",re.sub(r"[\[\]<>*!_`|#]","",str(raw or ""))).strip()[:240]


def build(rss, discovery, releases, *, now=None, edition_date=None, zone=ZONE):
    now=now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Morning evidence clock must be timezone-aware")
    now=now.astimezone(timezone.utc)
    local=now.astimezone(ZoneInfo(zone))
    day=_validated_day(edition_date) or local.date()
    tz=ZoneInfo(zone)
    cutoff=datetime.combine(day,time(6,30),tzinfo=tz).astimezone(timezone.utc)
    observation_limit=min(now,cutoff)
    # DST-safe previous *local civil day* cutoff, not UTC minus 24 hours.
    previous=datetime.combine(day-timedelta(days=1),time(6,30),
                              tzinfo=tz).astimezone(timezone.utc)
    source_records=(
        ("publisher_rss",_source_rows(rss,"articles")),
        ("global_discovery",_source_rows(discovery,"leads")),
        ("issuer_claim",_source_rows(releases,"leads")),
    )
    reviewed={}
    late=Counter()
    unproven=Counter()
    examined=Counter()
    for kind,records in source_records:
        for raw in records:
            if not isinstance(raw,dict) or not valid_url(raw.get("url")):
                continue
            is_date_only=(kind=="publisher_rss" and
                          raw.get("published_precision")=="day")
            actual_kind="regulatory_date_only" if is_date_only else kind
            desk_kind=(
                "official_rss" if actual_kind=="publisher_rss"
                else "regulatory_notice" if is_date_only
                else "global_discovery" if kind=="global_discovery"
                else "company_announcement"
            )
            lead=entry(raw,desk_kind,observation_limit)
            if not lead or lead.get("category") not in TOPICS:
                continue
            if any(flag in ("promotional_or_generic_marketing",
                            "low_commercial_impact",
                            "translation_and_source_review")
                   for flag in lead.get("needs_editor_review",[])):
                continue
            # Day-only notices have no credible 06:30 publish time. Treat
            # previous-day official notice as background only, never exact
            # pre-cutoff publisher-dated article.
            provider_stamp=as_time(lead.get("observed_time_utc"))
            if is_date_only:
                # Day-only official records often encode a calendar date at
                # midnight UTC. Converting midnight into Chicago would
                # silently shift the official publication date backward.
                pubday=provider_stamp.date() if provider_stamp else None
                if pubday!=day-timedelta(days=1):
                    continue
            elif not provider_stamp or not previous<=provider_stamp<=observation_limit:
                continue
            examined[actual_kind]+=1
            first=as_time(raw.get("first_collector_observed_utc")
                          or raw.get("first_collected_utc"))
            if first and first>observation_limit:
                late[actual_kind]+=1
                continue
            if first is None:
                unproven[actual_kind]+=1
            rec={
                "title":lead["title"], "url":lead["url"],
                "category":lead["category"],"origin":actual_kind,
                "first_collector_observed_utc":first.isoformat() if first else None,
                "provider_time_utc":provider_stamp.isoformat() if provider_stamp else None,
                "provider_time_basis":lead["time_basis"],
                "original_publisher_date":(
                    provider_stamp.date().isoformat() if actual_kind=="publisher_rss"
                    else None),
                "original_publication_date_verified":False,
                "local_collection_known":first is not None,
                "can_prove_collected_before_cutoff":bool(first and first<=observation_limit),
                "source_class":lead.get("source_class"),
                "review_flags":lead.get("needs_editor_review",[]),
                "rank":int(lead.get("relevance_score",0)),
                "notes":(
                    "Original RSS publisher timestamp, not independently verified"
                    if actual_kind=="publisher_rss" else
                    "Official publication DAY only; intraday availability unknown"
                    if is_date_only else
                    "GDELT indexing date, NOT publisher publication proof"
                    if kind=="global_discovery" else
                    "Issuer or wire claim; not independently confirmed reporting"
                ),
            }
            key=_identity(rec["url"])
            old=reviewed.get(key)
            # Prefer a primary publisher record for the same URL, but
            # never replace a known first collection timestamp with unknown.
            if old is None or (
                rec["can_prove_collected_before_cutoff"] and
                not old["can_prove_collected_before_cutoff"]
            ) or (
                rec["can_prove_collected_before_cutoff"]==old["can_prove_collected_before_cutoff"]
                and KIND_RANK[rec["origin"]]>KIND_RANK[old["origin"]]
            ):
                reviewed[key]=rec
    sections={}
    brief_template=[]
    for beat in TOPICS:
        candidates=[x for x in reviewed.values() if x["category"]==beat]
        candidates.sort(key=lambda x:(
            int(x["can_prove_collected_before_cutoff"]),KIND_RANK[x["origin"]],
            x["rank"],x["provider_time_utc"] or ""
        ),reverse=True)
        top=candidates[:PER_BEAT_LIMIT]
        proven=[x for x in top if x["can_prove_collected_before_cutoff"]]
        direct=sum(x["origin"]=="publisher_rss" for x in proven)
        discovered=sum(x["origin"]=="global_discovery" for x in proven)
        if direct:
            status="publisher_evidence_present"
        elif discovered:
            status="discovery_only_verify_original_source"
        elif proven:
            status="date_only_or_issuer_evidence_only"
        elif candidates:
            status="source_first_collection_time_unknown"
        else:
            status="no_current_source_evidence"
        sections[beat]={
            "status":status, "publisher_links_confirmed_collected":direct,
            "discovery_links_confirmed_collected":discovered,
            "total_candidate_links":len(candidates),
            "links":top,
        }
        if top:
            source=top[0]
            brief_template.append({
                "section":beat,"source_url":source["url"],
                "title":source["title"],
                "source_date":source["original_publisher_date"] or "",
                "publisher":"",
                "summary":"",
                "why_it_matters":"",
                "research_notes":source["notes"],
                "requires_original_publisher_review":True,
            })
    missing=[beat for beat,section in sections.items()
             if section["status"]=="no_current_source_evidence"]
    without_direct=[beat for beat,section in sections.items()
                    if section["publisher_links_confirmed_collected"]==0]
    # This is deliberately stricter than "any candidate link". A legacy
    # indexed headline with no first-observation clock does not prove
    # the 07:00 morning research had that sector covered.
    without_proven=[beat for beat,section in sections.items()
                    if not any(x["can_prove_collected_before_cutoff"]
                               for x in section["links"])]
    return {
        "edition_date":day.isoformat(),
        "generated_utc":now.isoformat(),
        "time_zone":zone,
        "news_cutoff_utc":cutoff.isoformat(),
        "observation_limit_utc":observation_limit.isoformat(),
        "previous_cutoff_utc":previous.isoformat(),
        "status":"research_evidence_only_never_email_approved",
        "section_statuses":sections,
        "missing_beats":missing,
        "beats_without_confirmed_direct_publisher_evidence":without_direct,
        "beats_without_proven_pre_cutoff_collection":without_proven,
        "pre_cutoff_collection_evidence_status":(
            "all_six_beats_observed_by_cutoff" if not without_proven
            else "insufficient_time_proven_coverage"
        ),
        "observed_candidate_counts":dict(examined),
        "late_first_collection_exclusions":dict(late),
        "unknown_first_collection_counts":dict(unproven),
        "researcher_brief_template":{
            "edition_date":day.isoformat(),
            "intro":"",
            "briefs":brief_template,
        },
        "policy":"Template contains no invented summaries, publisher dates, verification, approvals or email delivery.",
    }


def write_packet(packet,output):
    output=Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(packet,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    lines=[
        "# EnergyBrew morning source evidence — "+packet["edition_date"],"",
        "**Research only. No factual summaries or fact-checks generated.**","",
        "06:30 Central cutoff: "+packet["news_cutoff_utc"],"",
        "**Morning time evidence:** "+packet["pre_cutoff_collection_evidence_status"],"",
        "**Beats with no proven pre-cutoff collection:** "+
            (", ".join(packet["beats_without_proven_pre_cutoff_collection"]) or "None"),"",
        "| Energy beat | Coverage status | Direct RSS | GDELT |",
        "|---|---|---:|---:|",
    ]
    for beat in TOPICS:
        row=packet["section_statuses"][beat]
        lines.append(f"| {beat} | {row['status']} | {row['publisher_links_confirmed_collected']} | {row['discovery_links_confirmed_collected']} |")
    lines.extend(["","## Source links for original-article review"])
    for beat in TOPICS:
        lines.extend(["","### "+beat])
        rows=packet["section_statuses"][beat]["links"]
        if not rows:
            lines.append("- No qualifying source link; do not fabricate a story")
        for item in rows:
            lines.append("- "+_md_label(item["title"]))
            lines.append("  - Source URL: "+item["url"].replace("`",""))
            lines.append("  - Evidence: "+item["notes"])
            lines.append("  - First collected: "+(item["first_collector_observed_utc"] or "unknown"))
    lines.extend(["","No public distribution or automated email is authorized.",""])
    output.with_suffix(".md").write_text("\n".join(lines),encoding="utf-8")
    template=output.with_name(output.stem+"_brief_template.json")
    template.write_text(json.dumps(packet["researcher_brief_template"],
                                   indent=2,ensure_ascii=False)+"\n",encoding="utf-8")


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--rss",type=Path,required=True)
    p.add_argument("--discovery",type=Path,required=True)
    p.add_argument("--releases",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--date")
    p.add_argument("--zone",default=ZONE)
    args=p.parse_args(argv)
    data=[]
    for path in (args.rss,args.discovery,args.releases):
        obj=json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(obj,dict):
            raise ValueError("Invalid source JSON: "+str(path))
        data.append(obj)
    packet=build(*data,edition_date=args.date,zone=args.zone)
    write_packet(packet,args.output)
    print(json.dumps({
        "edition_date":packet["edition_date"],
        "missing_beats":packet["missing_beats"],
        "beats_without_direct_evidence":packet["beats_without_confirmed_direct_publisher_evidence"],
        "beats_without_proven_pre_cutoff_collection":packet["beats_without_proven_pre_cutoff_collection"],
        "research_only":True
    },indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
