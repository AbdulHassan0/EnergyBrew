"""EnergyBrew: standalone, source-aware RSS collection pilot.
Python standard library only; never publishes or emails. All observations remain research leads.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

SOURCES = [
    ("EIA Today in Energy", "https://www.eia.gov/rss/todayinenergy.xml"),
    ("EIA Press Releases", "https://www.eia.gov/rss/press_rss.xml"),
    ("EIA Congressional Testimony", "https://www.eia.gov/rss/testimony.xml"),
    ("EIA Presentations", "https://www.eia.gov/rss/presentations.xml"),
    ("DOE Energy News", "https://www.energy.gov/rss/energygov/2193718"),
    ("DOE Hydrocarbons Releases", "https://www.energy.gov/rss/hgeo/2282977"),
    ("DOE Hydrocarbons Blog", "https://www.energy.gov/rss/hgeo/2283029"),
    ("European Commission DG Energy", "https://energy.ec.europa.eu/node/2/rss_en"),
]
KEYWORDS = {
    "Natural Gas & LNG": ("natural gas", "lng", "liquefied", "gas pipeline", "gas storage", "haynesville", "henry hub", "methane", "gas export"),
    "Power & Electricity": ("electricity", "electric", "power grid", "power plant", "transmission", "data center", "grid", "renewable", "generation", "nuclear"),
    "Oil & Energy": ("crude", "oil", "refinery", "petroleum", "diesel", "gasoline", "offshore", "drilling"),
    "Infrastructure & Investment": ("pipeline", "terminal", "investment", "infrastructure", "capacity", "commission", "approval", "permit", "project"),
}
USER_AGENT = "EnergyBrewResearchCollector/1.0 (+https://github.com/AbdulHassan0/EnergyBrew)"
DROP_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term", "fbclid", "gclid"}
MAX_BYTES = 2_000_000

def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()

def child_text(node, names: tuple[str, ...]) -> str:
    for ch in node:
        if local(ch.tag) in names:
            val = "".join(ch.itertext()).strip()
            if val:
                return re.sub(r"\s+", " ", val)
    return ""

def article_link(node):
    for ch in node:
        if local(ch.tag) == "link":
            candidate = ch.attrib.get("href") or (ch.text or "").strip()
            if (not ch.attrib.get("rel") or ch.attrib.get("rel") == "alternate") and candidate.startswith(("http://", "https://")):
                return candidate
    return ""

def published_date(node):
    # Do not treat 'updated', crawl time, or index time as publication time.
    for ch in node:
        if local(ch.tag) not in ("pubdate", "published", "issued", "date"):
            continue
        raw = (ch.text or "").strip()
        if not raw or re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
            continue
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            try:
                dt = parsedate_to_datetime(raw)
            except (ValueError, TypeError, IndexError):
                continue
        if dt.tzinfo is None or dt.utcoffset() is None:
            continue
        return dt.astimezone(timezone.utc)
    return None

def clean_url(url):
    p = urlsplit(url)
    if p.scheme not in ("http", "https") or not p.netloc:
        return ""
    qs = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if k.lower() not in DROP_PARAMS]
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/") or "/", urlencode(qs), ""))

def classify(title, summary):
    txt = (title + " " + summary).lower()
    matched = [(category, sum(1 for term in terms if term in txt)) for category, terms in KEYWORDS.items()]
    category, points = max(matched, key=lambda x: x[1])
    return (category if points else "Cross-sector", points)

def parse_feed(xml_bytes, source_name, now, hours):
    root = ET.fromstring(xml_bytes)
    nodes = [n for n in root.iter() if local(n.tag) in ("item", "entry")]
    if local(root.tag) not in ("rss", "rdf", "feed") and not nodes:
        raise ValueError("Not a recognizable RSS/Atom feed")
    accepted, rejected = [], {"undated": 0, "old": 0, "future": 0, "invalid_link": 0}
    for node in nodes:
        title = child_text(node, ("title",))
        link = clean_url(article_link(node))
        dt = published_date(node)
        if not title or not link:
            rejected["invalid_link"] += 1
            continue
        if dt is None:
            rejected["undated"] += 1
            continue
        if dt > now + timedelta(minutes=10):
            rejected["future"] += 1
            continue
        if dt < now - timedelta(hours=hours):
            rejected["old"] += 1
            continue
        summary = child_text(node, ("description", "summary", "content"))[:700]
        category, score = classify(title, summary)
        guid = child_text(node, ("guid", "id"))
        identity = (source_name + "|" + (guid or link)).encode("utf-8")
        accepted.append({
            "id": hashlib.sha256(identity).hexdigest()[:24],
            "title": title[:300], "url": link, "source": source_name,
            "published_utc": dt.isoformat(), "category": category,
            "keyword_matches": score,
            "status": "research_only_unverified", "summary_excerpt": summary[:350],
        })
    return accepted, rejected, len(nodes)

def fetch_feed(url):
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/atom+xml, text/xml, application/xml"})
    with urlopen(request, timeout=20) as response:
        payload = response.read(MAX_BYTES + 1)
        if len(payload) > MAX_BYTES:
            raise ValueError("Feed exceeded 2 MB safety limit")
        return payload, response.status

def collect(state_path, outdir, hours=48, now=None, fetcher=None):
    now = now or datetime.now(timezone.utc)
    fetcher = fetcher or fetch_feed
    if state_path.exists():
        try:
            previous = json.loads(state_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            raise ValueError("Existing state unreadable; refusing to erase its history")
    else:
        previous = {"articles": [], "runs": []}
    articles = {x["id"]: x for x in previous.get("articles", [])}
    results, new_count = [], 0
    for name, url in SOURCES:
        row = {"source": name, "url": url, "connected": False, "items_seen": 0, "fresh": 0, "new": 0}
        try:
            raw, status = fetcher(url)
            items, rejected, seen = parse_feed(raw, name, now, hours)
            row.update({"connected": True, "http_status": status, "items_seen": seen, "fresh": len(items), "relevant": sum(x["keyword_matches"] > 0 for x in items), "rejected": rejected})
            for item in items:
                if item["id"] not in articles:
                    new_count += 1
                    row["new"] += 1
                articles[item["id"]] = item
        except Exception as exc:
            row["error"] = f"{type(exc).__name__}: {str(exc)[:220]}"
        results.append(row)
    cutoff = now - timedelta(days=7)
    retained = [v for v in articles.values() if datetime.fromisoformat(v["published_utc"]) >= cutoff]
    retained.sort(key=lambda x: x["published_utc"], reverse=True)
    unique_titles = {re.sub(r"[^a-z0-9]+", " ", x["title"].lower()).strip() for x in retained}
    run = {"run_utc": now.isoformat(), "feeds_connected": sum(x["connected"] for x in results),
           "feeds_checked": len(results), "fresh_entries": sum(x["fresh"] for x in results),
           "new_article_links": new_count, "relevant_fresh_entries": sum(x.get("relevant", 0) for x in results), "distinct_article_links_7d": len(retained),
           "approx_distinct_titles_7d": len(unique_titles), "sources": results}
    runs = [x for x in previous.get("runs", []) if datetime.fromisoformat(x["run_utc"]) >= cutoff]
    runs.append({k: run[k] for k in ("run_utc", "feeds_connected", "feeds_checked", "fresh_entries", "new_article_links")})
    outdir.mkdir(parents=True, exist_ok=True)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    temp = state_path.with_suffix(".tmp")
    temp.write_text(json.dumps({"articles": retained, "runs": runs}, indent=2) + "\n", encoding="utf-8")
    temp.replace(state_path)
    (outdir / "latest.json").write_text(json.dumps(run, indent=2) + "\n", encoding="utf-8")
    (outdir / "articles.json").write_text(json.dumps(retained, indent=2) + "\n", encoding="utf-8")
    candidates = [x for x in retained if x["keyword_matches"] > 0]
    (outdir / "editorial_candidates.json").write_text(json.dumps(candidates, indent=2) + "\n", encoding="utf-8")
    lines = ["# EnergyBrew — live RSS collection", "",
             f"Run: {run['run_utc']}", f"Successfully parsed feeds: **{run['feeds_connected']}/{run['feeds_checked']}**",
             f"Fresh feed entries (raw): **{run['fresh_entries']}**", f"Relevant fresh entries: **{run['relevant_fresh_entries']}**", f"New links: **{new_count}**",
             f"Distinct article links in 7-day state: **{len(retained)}**", "",
             "| Source | Connected | Fresh | Relevant | New | Error |", "|---|---|---:|---:|---:|---|"]
    for r in results:
        err = r.get("error", "").replace("|", "/")
        lines.append(f"| {r['source']} | {r['connected']} | {r['fresh']} | {r.get('relevant', 0)} | {r['new']} | {err} |")
    lines += ["", "Source-linked metadata is for private editorial research only. Dates come from publishers' publication fields, not HTTP crawl times.", "No newsletter publication or subscriber email occurs."]
    (outdir / "latest.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return run

def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", default="state/articles.json")
    parser.add_argument("--output", default="output/collector")
    parser.add_argument("--hours", type=int, default=48)
    args = parser.parse_args(argv)
    if not 1 <= args.hours <= 168:
        parser.error("--hours must be 1..168")
    result = collect(Path(args.state), Path(args.output), hours=args.hours)
    print(json.dumps({k: v for k, v in result.items() if k != "sources"}, indent=2))
    return 0 if result["feeds_connected"] else 2

if __name__ == "__main__":
    sys.exit(main())
