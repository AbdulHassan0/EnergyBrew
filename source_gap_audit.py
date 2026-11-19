"""Identify GDELT-only market story leads absent from configured publisher feeds.

This is an editorial RECONCILIATION tool, not a claim that the original stories
are correct, timely, licensed, or 'missed by all sources'. An index observation
is never an independently verified original publication time.
Only public headlines, links and provider metadata may be persisted.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from collector import SOURCES
from event_dedup import same_event
from research_desk import CATEGORY_ORDER, as_time, entry, load

MAX_GAP_ROWS = 18
MAX_PER_CATEGORY = 3
MAX_PER_DOMAIN = 2
INFERRED_SIGNAL_REVIEW = frozenset(("promotional_or_generic_marketing",
                                   "low_commercial_impact",
                                   "translation_and_source_review"))


def _nearby(rows, candidate):
    """Conservatively compare headlines, never assert independent corroboration."""
    for row in rows:
        if row["url"] == candidate["url"]:
            return "exact_url"
        if same_event(row, candidate):
            return "possible_same_event"
    return None


def reconcile(rss, discovery, releases=None, *, now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Audit clock must be timezone-aware")
    now = now.astimezone(timezone.utc)
    since = now - timedelta(hours=24)
    rss = rss if isinstance(rss, dict) else {}
    discovery = discovery if isinstance(discovery, dict) else {}
    releases = releases if isinstance(releases, dict) else {}

    direct = []
    direct_active = []
    for record in rss.get("articles", []):
        if not isinstance(record, dict) or record.get("published_precision", "timestamp") != "timestamp":
            continue
        item = entry(record, "official_rss", now)
        if item and as_time(item["observed_time_utc"]) <= now:
            direct.append(item)
            if as_time(item["observed_time_utc"]) >= since:
                direct_active.append(item)

    issuer = []
    for record in releases.get("leads", []):
        item = entry(record, "company_announcement", now)
        if item and as_time(item["observed_time_utc"]) <= now:
            issuer.append(item)

    indexed = {}
    for record in discovery.get("leads", []):
        item = entry(record, "global_discovery", now)
        if not item or not (since <= as_time(item["observed_time_utc"]) <= now):
            continue
        if any(x in INFERRED_SIGNAL_REVIEW for x in item["needs_editor_review"]):
            continue
        prior = indexed.get(item["url"])
        if prior is None or item["relevance_score"] > prior["relevance_score"]:
            indexed[item["url"]] = item

    direct_urls = {item["url"] for item in direct}
    issuer_urls = {item["url"] for item in issuer}
    source_classes = Counter(item.get("source_class") or "unknown" for item in direct_active)
    direct_beats = Counter(item["category"] for item in direct_active)
    discovered_beats = Counter(item["category"] for item in indexed.values())
    status_counts = Counter()
    candidates = []
    for item in indexed.values():
        if item["url"] in direct_urls:
            label = "exact_direct_publisher_link"
        elif item["url"] in issuer_urls:
            label = "exact_unverified_issuer_announcement_link"
        elif _nearby(direct, item) == "possible_same_event":
            label = "possible_same_event_as_direct_publisher_link"
        else:
            label = "discovery_only_needs_source_verification"
            candidates.append(item)
        status_counts[label] += 1

    candidates.sort(key=lambda item:(-item["relevance_score"],
                                      item["observed_time_utc"],item["url"]),
                    reverse=False)
    selected = []
    beat_caps = Counter()
    domain_caps = Counter()
    for item in candidates:
        if len(selected) >= MAX_GAP_ROWS:
            break
        beat, domain = item["category"], item["domain"]
        if beat_caps[beat] >= MAX_PER_CATEGORY or domain_caps[domain] >= MAX_PER_DOMAIN:
            continue
        if _nearby(selected,item):
            continue
        beat_caps[beat] += 1
        domain_caps[domain] += 1
        selected.append({
            "title": item["title"], "url": item["url"],
            "domain": domain, "category": beat,
            "gdelt_first_seen_utc": item["observed_time_utc"],
            "relevance_score": item["relevance_score"],
            "timestamp_basis": "GDELT_index_first_seen_not_publisher_date",
            "editorial_status": "unverified_research_lead_not_approved",
            "requires_original_publisher_verification": True,
        })

    health = rss.get("source_health") or {}
    feed_liveness = []
    for name,url in SOURCES:
        row = health.get(name, {}) if isinstance(health, dict) else {}
        row = row if isinstance(row, dict) else {}
        last = as_time(row.get("last_success_utc"))
        published = as_time(row.get("newest_feed_published_utc"))
        hours_ago = round((now-published).total_seconds()/3600,1) if published else None
        recent_count = sum(x["source"]==name for x in direct_active)
        feed_liveness.append({
            "source": name, "feed_url": url,
            "last_success_utc": last.isoformat() if last else None,
            "newest_feed_published_utc": published.isoformat() if published else None,
            "hours_since_newest_publisher_item": hours_ago,
            "timestamped_article_links_24h": recent_count,
            "consecutive_failures":row.get("consecutive_failures",0),
            "activity": (
                "no_successful_scan_observed" if last is None
                else "publisher_item_date_unknown" if hours_ago is None
                else "future_publisher_date_anomaly" if hours_ago < -1
                else "no_publisher_item_in_7d" if hours_ago > 168
                else "recent_publisher_activity"
            ),
        })
    feed_liveness.sort(key=lambda row:(-row["consecutive_failures"],
                                        row["timestamped_article_links_24h"],
                                        row["source"]))
    return {
        "generated_utc": now.isoformat(),
        "status": "source_gap_triage_not_a_verified_recall_score",
        "publisher_dated_direct_rss_links_24h": len({r["url"] for r in direct_active}),
        "publisher_dated_direct_source_classes_24h": dict(source_classes),
        "gdelt_observed_unique_urls_24h": len(indexed),
        "gdelt_publisher_date_verified": 0,
        "cross_origin_classifications": dict(status_counts),
        "direct_publisher_category_counts_24h": {x:direct_beats[x] for x in CATEGORY_ORDER},
        "indexed_candidate_category_counts_24h": {x:discovered_beats[x] for x in CATEGORY_ORDER},
        "high_priority_discovery_only_leads_for_review": selected,
        "feed_liveness": feed_liveness,
        "warnings": [
            "Discovery-only does not establish a missed news event, editorial importance, or original publication date.",
            "Similar headlines are grouped heuristically; never count grouped links as independent corroboration.",
            "An aged government RSS feed may be legitimately quiet; connectivity and publication activity are separate.",
            "This report compares sources EnergyBrew already configured, not all energy publishers.",
        ],
    }


def _plain_markdown_label(text):
    """Publisher-controlled titles must not inject new Markdown formatting."""
    import re
    result = re.sub(r"[\\r\\n\\t]+", " ", str(text or ""))
    result = re.sub(r"[<>\\[\\]\\`*_!]", "", result)
    return result.replace("\\\\", "").replace("|", " ").strip()[:300]


def write_report(report, directory):
    directory=Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    (directory/"source_gap.json").write_text(
        json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    lines=[
        "# EnergyBrew free-source reconciliation (editorial review only)","",
        "Generated: "+report["generated_utc"],
        "**This is not proof of complete news coverage or publisher publication time.**",
        "",
        f"Publisher-dated direct RSS links (24h): **{report['publisher_dated_direct_rss_links_24h']}**",
        f"GDELT index-first-seen distinct URLs (24h): **{report['gdelt_observed_unique_urls_24h']}**",
        f"GDELT original publisher dates verified: **0**","",
        "## Potential direct-feed gaps requiring verification",
        "",
    ]
    for i,item in enumerate(report["high_priority_discovery_only_leads_for_review"],1):
        lines.append(
            f"{i}. [{_plain_markdown_label(item['title'])}]"
            f"({item['url']}) — {item['category']} | {item['domain']}"
            " (GDELT index-only timestamp; unverified)")
    if not report["high_priority_discovery_only_leads_for_review"]:
        lines.append("No shortlisted candidates in the observed index; not proof of no market news.")
    lines.extend(["","## Direct publisher-dated counts by beat","","| Beat | Direct RSS | GDELT index |",
                  "|---|---:|---:|"])
    for beat in CATEGORY_ORDER:
        lines.append(
            f"| {beat} | {report['direct_publisher_category_counts_24h'][beat]}"
            f" | {report['indexed_candidate_category_counts_24h'][beat]} |")
    lines.extend(["","## Feed liveness","","| Feed | Publisher links (24h) | Latest item age (h) | Consecutive failures | Activity |",
                  "|---|---:|---:|---:|---|"])
    for item in report["feed_liveness"]:
        lines.append(f"| {item['source']} | {item['timestamped_article_links_24h']} | "
                     f"{item['hours_since_newest_publisher_item'] if item['hours_since_newest_publisher_item'] is not None else '?'} | "
                     f"{item['consecutive_failures']} | {item['activity']} |")
    lines.extend(["","## Interpretation",""]+["- "+w for w in report["warnings"]])
    (directory/"source_gap.md").write_text("\n".join(lines)+"\n",encoding="utf-8")


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("--rss",default="state/articles.json")
    parser.add_argument("--discovery",default="state/discovery.json")
    parser.add_argument("--releases",default="state/press_releases.json")
    parser.add_argument("--output",default="output/source_gap")
    args=parser.parse_args(argv)
    report=reconcile({"articles":load(args.rss,"articles"),
                      "source_health":_source_health(args.rss)},
                     {"leads":load(args.discovery,"leads")},
                     {"leads":load(args.releases,"leads")})
    write_report(report,args.output)
    print(json.dumps({
        "publisher_dated_direct_rss_links_24h":report["publisher_dated_direct_rss_links_24h"],
        "gdelt_observed_unique_urls_24h":report["gdelt_observed_unique_urls_24h"],
        "high_priority_discovery_only_leads_for_review":len(report["high_priority_discovery_only_leads_for_review"]),
    },indent=2))
    return 0


def _source_health(path):
    path=Path(path)
    if not path.exists():
        return {}
    try:
        data=json.loads(path.read_text(encoding="utf-8"))
        return data.get("source_health",{}) if isinstance(data,dict) else {}
    except (OSError,ValueError) as exc:
        raise ValueError("Corrupt publisher state; source liveness unknown") from exc


if __name__=="__main__":
    raise SystemExit(main())
