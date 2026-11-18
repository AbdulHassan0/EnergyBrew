"""Build the dependency-free EnergyBrew static site from private collector state.

Only source-linked metadata is exported. No fabricated stories, source dates, or
editorial approvals are ever generated.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

CATEGORIES = ("Natural Gas & LNG", "Power & Electricity", "Oil & Energy", "Infrastructure & Investment")
ORIGINS = ("official_rss", "regulatory_notice", "global_discovery", "company_announcement")
ASSETS = ("index.html", "styles.css", "app.js")


def read_json(path: Path, required: bool = False) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (OSError, ValueError):
        pass
    if required:
        raise ValueError(f"Missing or invalid research JSON: {path}")
    return {}


def safe_url(raw: object) -> str | None:
    if not isinstance(raw, str):
        return None
    url = raw.strip()
    parsed = urlparse(url)
    if parsed.scheme not in ("https", "http") or not parsed.hostname or parsed.username or parsed.password:
        return None
    return url[:2048]


def clean_text(value: object, limit: int = 200) -> str:
    return " ".join(str(value or "").split())[:limit]


def export_story(row: object) -> dict | None:
    if not isinstance(row, dict):
        return None
    title = clean_text(row.get("title"), 300)
    url = safe_url(row.get("url"))
    origin = row.get("origin")
    if not title or not url or origin not in ORIGINS:
        return None
    category = row.get("category")
    if category not in CATEGORIES:
        category = "Oil & Energy"
    themes = row.get("coverage_themes")
    themes = [x for x in themes if x in CATEGORIES] if isinstance(themes, list) else []
    if category not in themes:
        themes.insert(0, category)
    flags = row.get("needs_editor_review")
    return {
        "id": hashlib.sha256(url.encode("utf-8")).hexdigest()[:18],
        "title": title,
        "url": url,
        "domain": clean_text(row.get("domain"), 100),
        "source": clean_text(row.get("source") or row.get("domain"), 120),
        "category": category,
        "coverage_themes": list(dict.fromkeys(themes)),
        "origin": origin,
        "observed_time_utc": clean_text(row.get("observed_time_utc"), 50),
        "time_basis": clean_text(row.get("time_basis"), 80),
        "publisher_time_verified": bool(row.get("publisher_time_verified")) if origin == "official_rss" else False,
        "needs_editor_review": [clean_text(x, 80) for x in flags[:6]] if isinstance(flags, list) else [],
        "editorial_status": "research_only_not_approved",
    }


def build_data(desk: dict, metrics: dict | None = None, health: dict | None = None) -> dict:
    if not isinstance(desk.get("stories"), list):
        raise ValueError("No valid research desk stories. Refusing to invent a feed.")
    stories = []
    seen = set()
    for row in desk["stories"]:
        story = export_story(row)
        if story and story["id"] not in seen:
            seen.add(story["id"])
            stories.append(story)
    metrics = metrics or {}
    health = health or {}
    counts = desk.get("selected_topic_coverage_counts") or {}
    if not isinstance(counts, dict):
        counts = {}
    return {
        "status": "research_only_not_approved",
        "disclaimer": "Source-linked research leads only. Not independently verified, approved, or licensed for newsletter publication.",
        "generated_utc": clean_text(desk.get("generated_utc"), 50),
        "build_utc": datetime.now(timezone.utc).isoformat(),
        "unique_relevant_urls_7d": max(0, int(desk.get("unique_relevant_urls_7d") or len(stories))),
        "unique_domains_in_selection": len({s["domain"] for s in stories if s["domain"]}),
        "selected_topic_coverage_counts": {c:max(0,int(counts.get(c,0) or 0)) for c in CATEGORIES},
        "stories": stories,
        "metrics": {
            "status": clean_text(metrics.get("status"), 50),
            "seven_day_pilot_complete": metrics.get("seven_day_pilot_complete") is True,
            "latest_official_scan_utc": clean_text(metrics.get("latest_official_scan_utc"), 50),
            "latest_gal_sample_utc": clean_text(metrics.get("latest_gal_sample_utc"), 50),
            "warnings": [clean_text(x, 160) for x in (metrics.get("warnings") or [])[:8] if isinstance(x, str)]
        },
        "health": {
            "status": clean_text(health.get("status"), 50),
            "official_feeds_connected": max(0,int(health.get("official_feeds_connected",0) or 0)),
            "warnings": [clean_text(x, 160) for x in (health.get("warnings") or [])[:8] if isinstance(x, str)]
        }
    }


def create_site(desk: dict, metrics: dict, health: dict, assets: Path, destination: Path) -> dict:
    payload = build_data(desk, metrics, health)
    destination.mkdir(parents=True, exist_ok=True)
    for filename in ASSETS:
        source = assets / filename
        if not source.is_file():
            raise FileNotFoundError(f"Required frontend asset is missing: {source}")
        shutil.copy2(source, destination / filename)
    data_dir = destination / "data"
    data_dir.mkdir(exist_ok=True)
    (data_dir / "feed.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    (destination / "robots.txt").write_text("User-agent: *\nDisallow: /\n", encoding="utf-8")
    (destination / ".nojekyll").write_text("", encoding="utf-8")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--desk", type=Path, required=True)
    parser.add_argument("--metrics", type=Path, required=True)
    parser.add_argument("--health", type=Path, required=True)
    parser.add_argument("--assets", type=Path, default=Path("frontend"))
    parser.add_argument("--out", type=Path, default=Path("dist"))
    args = parser.parse_args(argv)
    result = create_site(read_json(args.desk, required=True), read_json(args.metrics), read_json(args.health), args.assets, args.out)
    print(f"Built {args.out} with {len(result['stories'])} real research leads.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
