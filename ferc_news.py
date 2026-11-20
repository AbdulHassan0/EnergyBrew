"""FERC public newsroom index: official HEADLINE metadata, not an RSS feed.

The listing contains day-precision publication dates only. Never infer an
intraday publication timestamp or treat an HTML headline as verified reporting.
No article pages are fetched and no publisher body text is saved.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen

from collector import clean_url
from editorial import evaluate

INDEX_URL = "https://www.ferc.gov/news-events/news/news-releases-headlines"
SOURCE_NAME = "FERC News Releases"
MAX_BYTES = 2_000_000
MONTHS = ("January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December")
DATE_PATTERN = re.compile(
    r"\\b(" + "|".join(MONTHS) + r")\\s+(\\d{1,2}),?\\s+(20\\d{2})\\b",
    re.IGNORECASE,
)
REJECT_SLUGS = {"news-releases-headlines", "news", "headlines", "news-releases"}


class ListingParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.length = 0
        self.links = []
        self.link = None
        self.ignored = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "svg"):
            self.ignored += 1
        if self.ignored:
            return
        if tag == "a":
            href = dict(attrs).get("href", "")
            self.link = {"href": href, "start": self.length, "title": []}

    def handle_data(self, data):
        if self.ignored:
            return
        text = " ".join(data.split())
        if text:
            chunk = " " + text + " "
            self.parts.append(chunk)
            self.length += len(chunk)
            if self.link is not None:
                self.link["title"].append(text)

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg") and self.ignored:
            self.ignored -= 1
            return
        if self.ignored:
            return
        if tag == "a" and self.link is not None:
            self.link["end"] = self.length
            self.link["title"] = " ".join(self.link["title"])
            self.links.append(self.link)
            self.link = None


def parse_listing(body: bytes, *, now: datetime):
    if not isinstance(body, bytes) or not body or len(body) > MAX_BYTES:
        raise ValueError("FERC listing missing or exceeds size limit")
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("FERC observation clock must be timezone-aware")
    text = body.decode("utf-8", errors="replace")
    if "<html" not in text[:2000].lower() and "<!doctype html" not in text[:2000].lower():
        raise ValueError("FERC index response was not an HTML document")
    parser = ListingParser()
    parser.feed(text)
    visible = "".join(parser.parts)
    matches = []
    seen = set()
    for i, link in enumerate(parser.links):
        url = clean_url(urljoin(INDEX_URL, link["href"]))
        if not url or url in seen:
            continue
        parsed = urlsplit(url)
        if parsed.hostname not in ("www.ferc.gov", "ferc.gov"):
            continue
        path = parsed.path.lower()
        if not path.startswith("/news-events/news/") or path.rstrip("/").rsplit("/", 1)[-1] in REJECT_SLUGS:
            continue
        title = " ".join(link["title"].split())[:300]
        if not 18 <= len(title) <= 300:
            continue
        # Listing design puts each item's publication DAY after its linked
        # headline. Never borrow a date after the NEXT newsroom article link.
        next_item = next(
            (l["start"] for l in parser.links[i+1:]
             if "/news-events/news/" in l.get("href", "")),
            len(visible),
        )
        adjacent = visible[link["end"]:min(link["end"] + 480, next_item)]
        match = DATE_PATTERN.search(adjacent)
        if not match:
            continue
        try:
            day = datetime.strptime(" ".join(match.groups()), "%B %d %Y").date()
        except ValueError:
            continue
        if day > now.date() or day < (now - timedelta(days=7)).date():
            continue
        quality = evaluate(title)
        if not quality["editorial_candidate"]:
            continue
        # Midnight UTC is a date placeholder, NOT a publisher release time.
        date_midnight = datetime.combine(day, datetime.min.time(), timezone.utc)
        matches.append({
            "id": hashlib.sha256(url.encode("utf-8")).hexdigest()[:24],
            "title": title, "url": url, "source": SOURCE_NAME,
            "source_class": "official_agency",
            "published_utc": date_midnight.isoformat(),
            "published_precision": "day",
            "source_date_basis": "ferc_official_newsroom_calendar_date",
            "publisher_time_verified": False,
            "first_collector_observed_utc": now.astimezone(timezone.utc).isoformat(),
            "category": quality["category"],
            "relevance_score": quality["relevance_score"],
            "relevance_evidence": quality["evidence"],
            "editorial_candidate": False,
            "status": "research_date_only",
        })
        seen.add(url)
    if not matches:
        raise ValueError("No dated, relevant FERC headlines parsed; markup or source activity requires review")
    return matches


def fetch_listing(url=INDEX_URL):
    req = Request(url, headers={
        "User-Agent": "EnergyBrewResearchCollector/1.0 (+https://github.com/AbdulHassan0/EnergyBrew)",
        "Accept": "text/html",
    })
    with urlopen(req, timeout=20) as response:
        body = response.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            raise ValueError("FERC response exceeds 2MB")
        return body, response.status


def collect(state_path: Path, output: Path, *, now=None, fetcher=None,
            completion_clock=None):
    injected_clock = now is not None
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("FERC completion timestamp must be timezone-aware")
    fetcher = fetcher or fetch_listing
    state_path = Path(state_path)
    output = Path(output)
    if not state_path.exists():
        raise ValueError("Run the primary publisher RSS collector before FERC index polling")
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("Invalid RSS state: refusing to erase publisher history") from exc
    if not isinstance(state, dict) or not isinstance(state.get("articles"), list) or not isinstance(state.get("runs"), list):
        raise ValueError("Invalid RSS state schema")
    raw, status = fetcher(INDEX_URL)
    if not isinstance(status, int) or not 200 <= status < 300:
        raise ValueError(f"FERC returned HTTP {status}")
    items = parse_listing(raw, now=now)
    completed = (completion_clock() if completion_clock else
                 now if injected_clock else datetime.now(timezone.utc))
    if completed.tzinfo is None or completed.utcoffset() is None:
        raise ValueError("FERC completion time must be timezone-aware")
    completed = completed.astimezone(timezone.utc)
    # A headline is not locally observed until the request and parsing end.
    for item in items:
        item["first_collector_observed_utc"] = completed.isoformat()
    existing = {}
    for row in state["articles"]:
        if not isinstance(row, dict):
            raise ValueError("RSS history contains non-object record")
        url = clean_url(row.get("url"))
        if url:
            existing[url] = row
    added = 0
    for row in items:
        prior = existing.get(row["url"])
        if prior is None:
            existing[row["url"]] = row
            added += 1
        elif prior.get("source") == SOURCE_NAME:
            # Do not reset the earliest observed time on later scans.
            old_first = prior.get("first_collector_observed_utc")
            if old_first:
                row["first_collector_observed_utc"] = old_first
            existing[row["url"]] = row
        # Another source may already have an independently supplied timestamp;
        # do not replace its higher-confidence publisher provenance.
    state["articles"] = list(existing.values())
    source_health = state.setdefault("source_health", {})
    if not isinstance(source_health, dict):
        raise ValueError("RSS state has malformed source-health information")
    source_health[SOURCE_NAME] = {
        "connected": True,
        "last_successful_scan_utc": completed.isoformat(),
        "last_relevant_listing_links": len(items),
        "publication_precision": "day_only",
    }
    output.mkdir(parents=True, exist_ok=True)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    temp = state_path.with_suffix(".ferc.tmp")
    temp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(state_path)
    summary = {
        "run_utc": now.astimezone(timezone.utc).isoformat(),
        "completed_utc": completed.isoformat(),
        "status": "ok", "source": SOURCE_NAME,
        "official_day_only_links": len(items), "new_links": added,
        "not_article_publication_timestamp": True,
        "reporting": "Official FERC newsroom listing links and dates only; no article bodies",
    }
    (output / "latest.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--state", type=Path, default=Path("state/articles.json"))
    p.add_argument("--output", type=Path, default=Path("output/ferc"))
    args = p.parse_args(argv)
    try:
        summary = collect(args.state, args.output)
        code = 0
    except (OSError, ValueError) as exc:
        # Preserve all existing source records. Persist a separate failure
        # report so a previous healthy FERC poll cannot masquerade as current.
        summary = {
            "run_utc": datetime.now(timezone.utc).isoformat(),
            "status": "degraded",
            "source": SOURCE_NAME,
            "official_day_only_links": 0,
            "new_links": 0,
            "error": f"{type(exc).__name__}: {str(exc)[:200]}",
            "not_article_publication_timestamp": True,
        }
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output / "latest.json").write_text(
            json.dumps(summary, indent=2) + "\\n", encoding="utf-8")
        code = 2
    print(json.dumps(summary, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
