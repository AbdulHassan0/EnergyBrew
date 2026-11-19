"""Read-only quality gate for completed EnergyBrew pilot newsletters.

Checks copy, sector balance, article age and publisher concentration without
reintroducing fact-check attestations. Source timestamps are evaluated
conservatively: GDELT index dates and day-only notices never prove 06:30
availability. A complete email is not evidence of on-time collection.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, date, time, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from newsletter import EditorialError, TOPICS, validate_pilot_preview, word_count, parse_utc


def _key(raw):
    if not isinstance(raw, str):
        return ""
    try:
        parts = urlsplit(raw)
    except ValueError:
        return ""
    if parts.scheme.lower() != "https" or not parts.hostname:
        return ""
    # Never assume a different slug or host is the same publisher article.
    path = parts.path.rstrip("/") or "/"
    return parts.hostname.lower() + path + ("?" + parts.query if parts.query else "")


def _publisher_domain(url):
    host = (urlsplit(url).hostname or "").lower().removeprefix("www.")
    bits = host.split(".")
    size = 3 if host.endswith((".co.uk", ".com.au", ".co.nz")) else 2
    return ".".join(bits[-size:]) if len(bits) >= size else host


def _as_date(s):
    if not isinstance(s, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def audit_pilot(edition, desk=None, *, raw_sources=None):
    """Return separate copy-readiness and 06:30 evidence assessments.

    An edition may be copy-ready while its time-of-day evidence is unproven.
    Never silently infer a publisher date, fact-check or successful delivery.
    """
    validate_pilot_preview(edition)  # Pilot status, real briefs, no fact-check gate.
    day = _as_date(edition["edition_date"])
    cutoff = datetime.combine(day, time(6,30), tzinfo=ZoneInfo(
        "America/Chicago")).astimezone(timezone.utc)
    errors, warnings = [], []
    beat_counts = Counter()
    domain_counts = Counter()
    seen_keys = set()
    indexed = {}
    selected_urls = set()
    if isinstance(desk, dict):
        for record in desk.get("stories", []):
            if isinstance(record,dict):
                key=_key(record.get("url"))
                if key:
                    selected_urls.add(key)
                    indexed.setdefault(key, [])
                    indexed[key].append(record)
    # Include all retained source metadata, not only 32 shortlisted leads.
    # Publisher time and index-first-seen are NEVER first collector observations.
    for lane,records in (raw_sources or {}).items():
        if lane not in ("rss","discovery","releases"):
            raise EditorialError("Unknown source lane in pilot audit")
        if not isinstance(records,list):
            raise EditorialError("Pilot audit source lane requires a list")
        for record in records:
            if isinstance(record,dict):
                key=_key(record.get("url"))
                if key:
                    indexed.setdefault(key, [])
                    indexed[key].append(record)
    matched = 0
    matched_selected = 0
    missing_sources = []
    time_evidence = 0
    after_cutoff = []
    unknown_clock = []
    rows = []
    for item in edition["stories"]:
        beat = item["section"]
        url = item["source_url"]
        key = _key(url)
        if not key or key in seen_keys:
            errors.append("Repeated or invalid canonical source link: " + url)
        seen_keys.add(key)
        beat_counts[beat] += 1
        domain = _publisher_domain(url)
        domain_counts[domain] += 1
        published = _as_date(item.get("source_date"))
        if published is None:
            errors.append("Missing valid source date: " + item["title"])
        elif published > day:
            errors.append("Source published after the edition date: " + item["title"])
        elif (day - published).days > 2:
            errors.append("Source older than two calendar days: " + item["title"])
        combined = " ".join(str(item.get(key) or "") for key in
                            ("summary","why_it_matters"))
        if re.search(r"\b(?:pending (?:fact.check|review)|lorem ipsum|tbd|insert summary)\b",
                     combined, flags=re.I):
            errors.append("Unwritten or placeholder brief: " + item["title"])
        candidates = indexed.get(key) or []
        observed = None
        if candidates:
            matched += 1
            observed_times = [
                stamp for record in candidates
                if (stamp := parse_utc(record.get("first_collector_observed_utc")
                                       or record.get("first_collected_utc")))
                is not None
            ]
            if observed_times:
                observed = min(observed_times)
        else:
            missing_sources.append(url)
        if key in selected_urls:
            matched_selected += 1
        if observed is None:
            unknown_clock.append(url)
        elif observed > cutoff:
            after_cutoff.append(url)
        else:
            time_evidence += 1
        rows.append({
            "section": beat, "title": item["title"], "url": url,
            "domain": domain, "source_date": item.get("source_date",""),
            "matched_in_research_desk": key in selected_urls,
            "matched_in_saved_sources": bool(candidates),
            "first_observed_utc": observed.isoformat() if observed else None,
            "as_of_cutoff": ("unproven" if observed is None else
                            "observed_after_cutoff" if observed > cutoff else
                            "observed_before_cutoff"),
        })
    missing = [beat for beat in TOPICS if beat_counts[beat] == 0]
    if missing:
        errors.append("Six-category pilot missing: " + ", ".join(missing))
    for beat, count in beat_counts.items():
        if count > 2:
            errors.append("Too many stories in one beat: " + beat)
    if len(domain_counts) < 4:
        errors.append("Pilot needs at least four distinct publisher domains")
    if domain_counts and max(domain_counts.values()) > 3:
        errors.append("A single publisher supplies more than three of eight stories")
    if after_cutoff:
        warnings.append("Some source links were first collected AFTER the 06:30 cutoff")
    if unknown_clock:
        warnings.append("First EnergyBrew collection time unproven for some source links")
    if not isinstance(desk, dict):
        warnings.append("No selected research desk supplied; evidence limited to raw saved state")
    elif matched_selected != len(edition["stories"]):
        warnings.append("Some pilot links are not in the 32-story shortlist; checked retained raw source state")
    if missing_sources:
        warnings.append("Some pilot links are not in any supplied saved source state")
    if desk and parse_utc(desk.get("generated_utc")) and parse_utc(
            desk["generated_utc"]) > cutoff:
        warnings.append("Research snapshot generated after 06:30; not a frozen morning edition")
    word_total = word_count(edition.get("intro")) + sum(
        sum(word_count(story.get(k)) for k in ("title","summary","why_it_matters"))
        for story in edition["stories"]
    )
    return {
        "edition_date": edition["edition_date"],
        "status": "pilot_copy_ready" if not errors else "pilot_copy_blocked",
        "six_beats_present": len(missing) == 0,
        "beat_counts": {beat: beat_counts[beat] for beat in TOPICS},
        "publisher_domains": dict(sorted(domain_counts.items())),
        "total_stories": len(edition["stories"]),
        "reading_words": word_total,
        "matched_research_links": matched_selected,
        "matched_saved_source_links": matched,
        "links_missing_in_saved_sources": missing_sources,
        "cutoff_utc": cutoff.isoformat(),
        "cutoff_collection_evidence": ("supported" if time_evidence == len(rows)
                                       and isinstance(desk, dict) and matched == len(rows)
                                       else "not_established"),
        "source_links_observed_after_cutoff": after_cutoff,
        "source_links_with_unknown_collection_time": unknown_clock,
        "errors": errors, "warnings": warnings,
        "stories": rows,
        "newsletter_delivery": "disabled",
        "meaning": "Pilot copy QA only, not independent source verification, 7am timeliness, or permission to send.",
    }


def write_report(report, output):
    output = Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",
                      encoding="utf-8")
    lines = [
        "# EnergyBrew pilot newsletter quality",
        "",
        "**"+report["status"].replace("_"," ")+"** — "+report["edition_date"],
        "",
        f"Briefs: **{report['total_stories']}** · Reading copy: **{report['reading_words']} words**",
        f"Publisher domains: **{len(report['publisher_domains'])}**",
        f"Matching saved source URLs: **{report['matched_saved_source_links']} / {report['total_stories']}**",
        f"Matching selected desk URLs: **{report['matched_research_links']} / {report['total_stories']}**",
        f"Morning 06:30 evidence: **{report['cutoff_collection_evidence']}**",
        "",
        "| Beat | Stories |", "|---|---:|",
    ]
    for beat, count in report["beat_counts"].items():
        lines.append(f"| {beat} | {count} |")
    lines.extend(["","## Blocking copy defects"])
    lines.extend(["- "+e for e in report["errors"]] or ["- None"])
    lines.extend(["","## Operating cautions"])
    lines.extend(["- "+w for w in report["warnings"]] or ["- None"])
    lines.extend(["","**No automated email is sent.** Copy readiness is not fact-check approval.",
                  ""])
    output.with_suffix(".md").write_text("\n".join(lines),encoding="utf-8")


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("--pilot",type=Path,required=True)
    parser.add_argument("--desk",type=Path)
    parser.add_argument("--rss",type=Path)
    parser.add_argument("--discovery",type=Path)
    parser.add_argument("--releases",type=Path)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args(argv)
    pilot=json.loads(args.pilot.read_text(encoding="utf-8"))
    desk=json.loads(args.desk.read_text(encoding="utf-8")) if args.desk else None
    raw_sources={}
    for lane,field in (("rss","articles"),("discovery","leads"),
                       ("releases","leads")):
        path=getattr(args,lane)
        if path:
            contents=json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(contents,dict) or not isinstance(contents.get(field),list):
                raise EditorialError("Invalid saved source state for pilot audit: "+lane)
            raw_sources[lane]=contents[field]
    result=audit_pilot(pilot,desk,raw_sources=raw_sources)
    write_report(result,args.output)
    print(json.dumps({k:result[k] for k in (
        "status","six_beats_present","total_stories","reading_words",
        "cutoff_collection_evidence","errors","warnings")},indent=2))
    return 0 if result["status"]=="pilot_copy_ready" else 2


if __name__=="__main__":
    raise SystemExit(main())
