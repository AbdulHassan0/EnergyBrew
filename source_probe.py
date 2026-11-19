"""Measure real energy-specialist RSS endpoints before making them production sources.

The probe collects public headline/link metadata only. It does not scrape articles,
copy bodies, bypass paywalls, or claim that public feeds grant reuse rights.
"""
from __future__ import annotations
import argparse
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from collector import MAX_BYTES, USER_AGENT, parse_feed

# Directly advertised publisher endpoints, staged for hosted validation.
CANDIDATES = (
    # Provider RSS available from verified site RSS directories; staged, not enabled.
    ("Utility Dive Latest News", "https://www.utilitydive.com/feeds/news/"),
    ("PJM Inside Lines", "https://insidelines.pjm.com/feed/"),
    ("EIA What's New", "https://www.eia.gov/about/new/WNtest3.php"),
    ("EIA Gasoline & Diesel Update", "https://www.eia.gov/petroleum/gasdiesel/includes/gas_diesel_rss.xml"),
    ("EIA Heating Oil & Propane Update", "https://www.eia.gov/petroleum/heatingoilpropane/includes/hopu_rss.xml"),
    # Official US federal agency endpoints: public metadata-only availability probes.
    ("DOE HGEO Press Releases", "https://www.energy.gov/hgeo/listings/hgeo-press-releases-and-techlines?view=rss"),
    ("DOE Resource Sustainability", "https://www.energy.gov/hgeo/listings/office-resource-sustainability-news?view=rss"),
    ("FERC eForms RSS", "https://ecollection.ferc.gov/api/rssfeed"),
    ("Offshore Energy News", "https://www.offshore-energy.biz/feed"),
    ("OilPrice.com News", "https://oilprice.com/rss.xml"),
    # Staged feeds: connection/volume probe ONLY, not production-enabled or licensed.
    ("POWER Magazine", "https://www.powermag.com/feed/"),
    ("Power Engineering", "https://www.power-eng.com/feed/"),
    ("Energy Storage News", "https://www.energy-storage.news/feed/"),
    ("LNG Prime", "https://lngprime.com/feed/"),
    ("LNG Industry", "https://www.lngindustry.com/feed/"),
)

# Explicitly distinguish a reachable RSS URL from authorized commercial use.
# Blocking is for adding a DIRECT AUTOMATED source to collection; a public link
# discovered through a search index remains a source for human verification.
PROBE_RIGHTS_STATUS = {
    "LNG Prime": "blocked_direct_feed_pending_permission",
    "Energy Storage News": "blocked_direct_feed_pending_permission",
    "POWER Magazine": "rights_review_pending",
    "Power Engineering": "rights_review_pending",
    "LNG Industry": "rights_review_pending",
}
SIZE_LIMIT = min(MAX_BYTES, 1_500_000)
SOURCE_TIMEOUT = 12


def fetch(url: str) -> tuple[bytes, int]:
    request = Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/rss+xml,application/atom+xml,text/xml,application/xml",
    })
    with urlopen(request, timeout=SOURCE_TIMEOUT) as response:
        data = response.read(SIZE_LIMIT + 1)
        if len(data) > SIZE_LIMIT:
            raise ValueError("Candidate RSS exceeds 1.5 MB safety limit")
        return data, response.status


def measure(candidates=CANDIDATES, *, now=None, fetcher=None) -> dict:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Probe clock must be timezone-aware")
    fetcher = fetcher or fetch
    results = []
    for name, url in candidates:
        started = time.monotonic()
        row = {"name": name, "url": url, "status": "degraded",
               "rights_status": PROBE_RIGHTS_STATUS.get(name, "not_assessed_by_probe"),
               "fresh_links_24h": 0,
               "fresh_links_48h": 0, "high_signal_48h": 0, "error": None}
        if row["rights_status"] in ("blocked_direct_feed_pending_permission", "rights_review_pending"):
            row["status"] = "skipped_rights_review"
            row["error"] = "No automated request made; rights not cleared for recurrent polling"
            row["duration_ms"] = 0
            results.append(row)
            continue
        try:
            payload, status = fetcher(url)
            if not 200 <= status < 300:
                raise ValueError(f"Publisher RSS returned HTTP {status}")
            items, rejected, count = parse_feed(payload, name, now, 48)
            distinct = {}
            for story in items:
                # The same generic item URL repeated 500 times is ONE link, not 500.
                prior = distinct.get(story["url"])
                if prior is None or story["published_utc"] > prior["published_utc"]:
                    distinct[story["url"]] = story
            unique = list(distinct.values())
            generic_only = count > 0 and rejected.get("homepage_link", 0) / count >= 0.8
            row.update(
                status="ok",
                http_status=status,
                rss_item_count=count,
                raw_window_entries_48h=len(items),
                fresh_links_48h=sum(datetime.fromisoformat(x["published_utc"]) <= now for x in unique),
                fresh_links_24h=sum(now - timedelta(hours=24) <= datetime.fromisoformat(x["published_utc"]) <= now for x in unique),
                high_signal_48h=sum(bool(x["editorial_candidate"]) and datetime.fromisoformat(x["published_utc"]) <= now for x in unique),
                future_dated_links=sum(datetime.fromisoformat(x["published_utc"]) > now for x in unique),
                duplicate_article_urls=len(items) - len(unique),
                link_quality="homepage_only" if generic_only else "actionable_links" if unique else "no_recent_items",
                rejected=rejected,
                sample_headlines=[{"title": x["title"], "url": x["url"]} for x in unique[:3]],
            )
        except Exception as exc:
            row["error"] = f"{type(exc).__name__}: {str(exc)[:160]}"
        row["duration_ms"] = round((time.monotonic() - started) * 1000)
        results.append(row)
    return {
        "run_utc": now.isoformat(),
        "status": "ok" if any(x["status"]=="ok" for x in results) else "degraded",
        "feeds_checked": len(results),
        "feeds_connected": sum(x["status"]=="ok" for x in results),
        "feeds_with_recent_actionable_links": sum(x.get("link_quality")=="actionable_links" for x in results),
        "generic_homepage_only_feeds": sum(x.get("link_quality")=="homepage_only" for x in results),
        "fresh_links_24h": sum(x["fresh_links_24h"] for x in results),
        "future_dated_links": sum(x.get("future_dated_links", 0) for x in results),
        "high_signal_48h": sum(x["high_signal_48h"] for x in results),
        "sources": results,
        "note": "Deduplicated actionable URLs, NOT raw feed-entry counts. Publisher timestamps and reuse rights unverified.",
    }


def write_report(data: dict, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    (output/"source_probe.json").write_text(json.dumps(data, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    lines = [
        "# EnergyBrew energy specialist RSS — connection and volume pilot", "",
        f"Probe UTC: {data['run_utc']}",
        f"Connected: **{data['feeds_connected']}/{data['feeds_checked']}**",
        f"Feeds with unique actionable URLs in the last 48h: **{data['feeds_with_recent_actionable_links']}**",
        f"Feeds pointing predominantly to a generic homepage: **{data['generic_homepage_only_feeds']}**",
        f"Fresh source-linked records in last 24h: **{data['fresh_links_24h']}**",
        f"Future-dated source links excluded from freshness: **{data['future_dated_links']}**",
        "", "| Source | Connection | Link quality | Usage review | Unique 24h links | Unique 48h links | High-signal 48h | Error |",
        "|---|---|---|---|---:|---:|---:|---|",
    ]
    for x in data["sources"]:
        error = (x.get("error") or "").replace("|","/")
        lines.append(f"| {x['name']} | {x['status']} | {x.get('link_quality', 'not_checked')} | {x['rights_status']} | {x['fresh_links_24h']} | {x['fresh_links_48h']} | {x['high_signal_48h']} | {error} |")
    lines += ["", "Freshness is based on publisher RSS timestamps, not independent confirmation.",
              "A successful HTTP/RSS connection is not evidence of unique actionable story URLs.",
              "A successful endpoint probe does NOT authorize adding a source to commercial production collection.",
              "Blocked/review-pending candidates require source-specific legal and contractual evaluation before direct automated polling."]
    (output/"source_probe.md").write_text("\n".join(lines)+"\n",encoding="utf-8")


def main(argv=None) -> int:
    p=argparse.ArgumentParser()
    p.add_argument("--output", type=Path, default=Path("output/source_probe"))
    args=p.parse_args(argv)
    data=measure()
    write_report(data,args.output)
    print(json.dumps({k:v for k,v in data.items() if k!="sources"},indent=2))
    return 0 if data["status"]=="ok" else 2


if __name__=="__main__":
    raise SystemExit(main())
