"""Public-repository safety gate for metadata-only EnergyBrew news collection.

This repo is public; state and Actions artifacts are not private by default.
Reject article text, credentials, or nonpublic feed configurations before push.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit
from collector import SOURCES, clean_url
from discovery import API as GDELT_DOC_URL
from gal import FEED_URL as GDELT_GAL_URL
from press_releases import URL as PRESS_FEED_URL

# Explicit stop-list for sites with published commercial redistribution/storage
# restrictions. Probe-only connectivity testing does not confer permission.
# This guards direct automated publisher feed onboarding, not public links found by GDELT.
RIGHTS_BLOCKED_DIRECT_FEED_HOSTS = frozenset({
    "lngprime.com", "energy-storage.news", "rigzone.com", "ogj.com",
})

PUBLIC_FEED_HOSTS = frozenset({
    "www.eia.gov", "www.energy.gov", "www.nrc.gov", "energy.ec.europa.eu",
    "www.federalregister.gov",
    "www.offshore-energy.biz", "oilprice.com", "www.utilitydive.com",
    "insidelines.pjm.com",
})
RESERVED_KEYS = frozenset({
    "summary_excerpt", "article_body", "full_text", "content", "description",
    "raw_html", "html", "authorization", "api_key", "apikey", "access_token",
    "password", "secret", "credential", "subscriber", "subscriber_email",
    "contact_email", "cookie", "session_token",
})
MAX_STATE_BYTES = 8_000_000


class SafetyError(ValueError):
    pass


def ensure_sources_public() -> None:
    source_urls = [url for _, url in SOURCES]
    source_urls.extend([GDELT_DOC_URL, GDELT_GAL_URL, PRESS_FEED_URL])
    for uri in source_urls:
        parsed = urlsplit(uri)
        if parsed.scheme != "https" or parsed.username or parsed.password:
            raise SafetyError("Configured sources must be public HTTPS endpoints")
        normalized_host=(parsed.hostname or "").removeprefix("www.")
        if normalized_host in RIGHTS_BLOCKED_DIRECT_FEED_HOSTS:
            raise SafetyError(f"Direct feed host requires written source permission: {normalized_host}")
        if uri in [GDELT_DOC_URL, GDELT_GAL_URL, PRESS_FEED_URL]:
            continue
        if parsed.hostname not in PUBLIC_FEED_HOSTS:
            raise SafetyError(f"Source needs a public-safe host review: {parsed.hostname}")


def sanitize_legacy_rss(path: Path) -> int:
    """One-time safe removal of historical publisher snippets; other unsafe fields still fail."""
    if not path.exists():
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SafetyError(f"{path}: cannot safely migrate malformed RSS history") from exc
    if not isinstance(data, dict) or not isinstance(data.get("articles"), list):
        raise SafetyError(f"{path}: cannot migrate invalid RSS state schema")
    changed = 0
    for item in data["articles"]:
        if not isinstance(item, dict):
            raise SafetyError(f"{path}: non-object RSS history record")
        if "summary_excerpt" in item:
            item.pop("summary_excerpt")
            changed += 1
    if changed:
        temporary = path.with_suffix(".sanitized.tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)
    return changed


def validate_records(path: Path, key: str) -> int:
    if not path.exists():
        return 0  # first-ever run or optional lane that failed
    if path.stat().st_size > MAX_STATE_BYTES:
        raise SafetyError(f"{path}: state unexpectedly exceeds {MAX_STATE_BYTES} bytes")
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SafetyError(f"{path}: invalid state JSON") from exc
    if not isinstance(record, dict) or not isinstance(record.get(key), list):
        raise SafetyError(f"{path}: invalid record format")
    for i, article in enumerate(record[key]):
        if not isinstance(article, dict):
            raise SafetyError(f"{path}: non-object news record")
        if RESERVED_KEYS.intersection(article):
            raise SafetyError(f"{path}: copyrighted content or sensitive metadata in record {i}")
        url = article.get("url")
        if not isinstance(url, str) or clean_url(url) != url:
            raise SafetyError(f"{path}: unsafe or unnormalized publisher link at record {i}")
        if not isinstance(article.get("title"), str) or not 2 <= len(article["title"]) <= 300:
            raise SafetyError(f"{path}: missing or oversized headline at record {i}")
    return len(record[key])


def validate_all(rss: Path, discovery: Path, releases: Path) -> dict:
    ensure_sources_public()
    counts = {
        "publisher_metadata": validate_records(rss, "articles"),
        "discovery_metadata": validate_records(discovery, "leads"),
        "company_release_metadata": validate_records(releases, "leads"),
    }
    if sum(counts.values()) == 0:
        raise SafetyError("No valid public research metadata available; do not advance shared state")
    return counts


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--rss", type=Path, default=Path("state/articles.json"))
    p.add_argument("--discovery", type=Path, default=Path("state/discovery.json"))
    p.add_argument("--releases", type=Path, default=Path("state/press_releases.json"))
    p.add_argument("--sanitize-legacy", action="store_true", help="Remove previously persisted RSS summary_excerpt fields only")
    args = p.parse_args()
    if args.sanitize_legacy:
        print("Removed old publisher RSS excerpts:", sanitize_legacy_rss(args.rss))
    print("Public metadata collection safety gate:", json.dumps(validate_all(args.rss,args.discovery,args.releases)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
