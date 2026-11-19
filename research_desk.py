"""Consolidate EnergyBrew's independent research lanes into one auditable desk.

The desk ranks links for an editor. It NEVER promotes discovery timestamps or
company-release feed timestamps to verified publisher publication dates.
No article body scraping, newsletter approval, distribution, or automated fact-checking.
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from collector import clean_url
from editorial import evaluate, non_article_reason
from event_dedup import attach_related, same_event

LIMIT_PER_DOMAIN = 4
TOP_PER_CATEGORY = 8
MAX_COMPANY_RELEASES = 2
ORIGIN_RANK_BOOST = {"official_rss": 75, "regulatory_notice": 40,
                     "global_discovery": 12, "company_announcement": 0}
CATEGORY_ORDER = ("Natural Gas", "LNG", "Power & Electricity",
                  "Oil & Energy", "Infrastructure & Investment", "Geopolitics")
ORIGIN_PRIORITY = {"official_rss": 4, "regulatory_notice": 3,
                   "company_announcement": 2, "global_discovery": 1}

def as_time(value):
    if not isinstance(value, str):
        return None
    try:
        obj = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return obj.astimezone(timezone.utc) if obj.tzinfo else None

def load(path, key):
    if not path or not Path(path).exists():
        return []
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        records = data.get(key, []) if isinstance(data, dict) else data
        return records if isinstance(records, list) else []
    except (OSError, ValueError) as exc:
        raise ValueError(f"Unreadable research state is not a clean empty feed: {path}") from exc

def is_english_script(title):
    letters=[c for c in (title or "") if c.isalpha()]
    return bool(letters) and sum("LATIN" in unicodedata.name(c,"") for c in letters)/len(letters)>=.9

def marketing_signal(title):
    s = (title or "").lower()
    return any(x in s for x in (
        "seo services", "search engine optimization", "ai search visibility",
        "marketing agency", "social media marketing", "press release distribution",
        "launches new website", "sector analysis examining",
    ))

def low_market_impact_signal(title):
    s = (title or "").lower()
    return any(re.search(pat, s) for pat in (
        r"students?.*(?:conserve|learn|saving).*(?:electricity|energy)",
        r"(?:school|students?).*(?:energy|electricity) awareness",
        r"how to save (?:electricity|energy) at home",
        r"energy-saving tips",
        r"^(?:rupee|indian rupee|currenc(?:y|ies)).*(?:crude|oil|brent)",
        r"^(?:stocks?|shares?|equities).*(?:rall(?:y|ies)|drop|fall|gain).*(?:crude|oil)",
    ))

def coverage_themes(title, primary):
    # Secondary topic labels indicate subject overlap, not independent news events.
    themes = [primary]
    s = (title or "").lower()
    infrastructure = ("pipeline", "terminal", "expansion", "construction",
                      "interconnection", "infrastructure", "acquisition",
                      "investment", "project", "grid reliability", "capital expenditure")
    if any(k in s for k in infrastructure) and "Infrastructure & Investment" not in themes:
        themes.append("Infrastructure & Investment")
    if primary == "Geopolitics":
        # A single geopolitical event can impact several commodity markets.
        impacts = {
            "Natural Gas": ("natural gas", "gas transit", "gas pipeline"),
            "LNG": ("lng", "liquefied natural gas", "regasification"),
            "Oil & Energy": ("oil", "crude", "refinery", "refineries", "tanker", "brent"),
            "Power & Electricity": ("power grid", "electricity", "power plant", "solar panels"),
        }
        for beat, terms in impacts.items():
            if any(re.search(r"(?<![a-z0-9])" + re.escape(k) + r"(?![a-z0-9])", s) for k in terms):
                if beat not in themes:
                    themes.append(beat)
    return themes

def entry(record, kind, now):
    if not isinstance(record, dict):
        return None
    title = " ".join(str(record.get("title") or "").split())[:300]
    url = clean_url(str(record.get("url") or ""))
    if not title or not url or non_article_reason(title, url):
        return None
    if kind == "official_rss":
        if record.get("published_precision", "timestamp") != "timestamp":
            return None
        stamp = as_time(record.get("published_utc"))
        is_specialist = record.get("source_class") == "specialist_publisher"
        time_basis = ("specialist_publisher_rss_timestamp" if is_specialist
                      else "system_operator_rss_timestamp" if record.get("source_class") == "system_operator_primary"
                      else "publisher_feed_publication_time")
        date_verification = "publisher_rss_timestamp"
        has_publisher_date = True
    elif kind == "regulatory_notice":
        if record.get("published_precision") != "day":
            return None
        stamp = as_time(record.get("published_utc"))
        time_basis = "official_publication_date_only"
        date_verification = "date_only"
        has_publisher_date = False
    elif kind == "company_announcement":
        stamp = as_time(record.get("feed_published_utc"))
        time_basis = "third_party_release_feed_date_unverified"
        date_verification = "feed_only"
        has_publisher_date = False
    else:
        stamp = as_time(record.get("gdelt_first_seen_utc"))
        providers = record.get("discovery_providers") or []
        time_basis = ("gdelt_gal_rss_provider_time_unverified"
                      if record.get("discovery_provider")=="GDELT GAL RSS" or "GDELT GAL RSS" in providers
                      else "discovery_index_first_seen_only")
        date_verification = "not_verified"
        has_publisher_date = False
    if stamp is None or stamp > now + timedelta(hours=1) or stamp < now - timedelta(days=7):
        return None
    quality = evaluate(title, record.get("summary_excerpt", "") if kind == "official_rss" else "")
    if quality["relevance_score"] < 22:
        return None
    flagged = []
    if marketing_signal(title):
        flagged.append("promotional_or_generic_marketing")
    if low_market_impact_signal(title):
        flagged.append("low_commercial_impact")
    if not is_english_script(title):
        flagged.append("translation_and_source_review")
    # Index first-seen cannot stand in for original publication freshness.
    recent = stamp >= now - timedelta(hours=24)
    source = (record.get("source") if kind in ("official_rss", "regulatory_notice")
              else record.get("provider") or record.get("discovery_provider") or "Research provider")
    from urllib.parse import urlsplit
    domain = urlsplit(url).hostname or ""
    return {
        "title": title, "url": url, "domain": domain.lower(),
        "source": str(source), "source_class": record.get("source_class") or "unclassified",
        "category": quality["category"],
        "coverage_themes": coverage_themes(title, quality["category"]),
        "relevance_score": quality["relevance_score"],
        "relevance_evidence": quality["evidence"],
        "origin": kind, "time_basis": time_basis,
        "observed_time_utc": stamp.isoformat(),
        "publisher_time_verified": has_publisher_date,
        "date_confidence": date_verification,
        "within_24h_on_own_time_basis": recent,
        "needs_editor_review": flagged,
        "editorial_status": "research_only_not_approved",
        "other_origins": [],
        "independent_corroboration_verified": False,
    }

def assemble(rss, discovered, releases, now=None, max_stories=32):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now must have timezone")
    rows = []
    rss = rss or []
    for a in rss:
        if not isinstance(a, dict):
            continue
        kind = "regulatory_notice" if a.get("published_precision") == "day" else "official_rss"
        x = entry(a, kind, now)
        if x:
            rows.append(x)
    for a in discovered or []:
        x = entry(a, "global_discovery", now)
        if x:
            rows.append(x)
    for a in releases or []:
        x = entry(a, "company_announcement", now)
        if x:
            rows.append(x)
    # One URL = one editorial research item even when multiple data paths see it.
    index = {}
    for x in rows:
        old = index.get(x["url"])
        if old is None:
            index[x["url"]] = x
        elif ORIGIN_PRIORITY[x["origin"]] > ORIGIN_PRIORITY[old["origin"]]:
            x["other_origins"] = sorted(set(old["other_origins"] + [old["origin"]]))
            index[x["url"]] = x
        elif x["origin"] != old["origin"]:
            old["other_origins"] = sorted(set(old["other_origins"] + [x["origin"]]))
    all_rows = list(index.values())
    for x in all_rows:
        x["queue"] = (
            "system_operator_primary_24h" if x["origin"] == "official_rss" and x.get("source_class") == "system_operator_primary" and x["within_24h_on_own_time_basis"]
            else "specialist_publisher_24h" if x["origin"] == "official_rss" and x.get("source_class") == "specialist_publisher" and x["within_24h_on_own_time_basis"]
            else "timestamped_official" if x["origin"] == "official_rss" and x["within_24h_on_own_time_basis"]
            else "regulatory_date_only" if x["origin"] == "regulatory_notice"
            else "company_release_unverified" if x["origin"] == "company_announcement"
            else "discovery_unverified" if x["origin"] == "global_discovery"
            else "older_official_context"
        )
        x["rank"] = x["relevance_score"] + ORIGIN_RANK_BOOST[x["origin"]]
        if x.get("source_class") == "specialist_publisher":
            x["rank"] -= 20  # distinguish publisher journalism from agency primary-source records
        if x["queue"] == "older_official_context":
            x["rank"] -= 25
        if "translation_and_source_review" in x["needs_editor_review"]:
            x["rank"] -= 25
        if "promotional_or_generic_marketing" in x["needs_editor_review"]:
            x["rank"] -= 45
        if "low_commercial_impact" in x["needs_editor_review"]:
            x["rank"] -= 40
    all_rows.sort(key=lambda x: (x["rank"], x["observed_time_utc"]), reverse=True)
    # Balance beats and publishers without pretending different sites independently confirm an event.
    counts = Counter()
    domains = Counter()
    selected = []
    release_selected = 0
    duplicate_links_suppressed = 0
    for x in all_rows:
        existing = next((s for s in selected if same_event(s, x)), None)
        if existing is not None:
            attach_related(existing, x)
            duplicate_links_suppressed += 1
            continue
        if counts[x["category"]] >= TOP_PER_CATEGORY or domains[x["domain"]] >= LIMIT_PER_DOMAIN:
            continue
        if x["origin"] == "company_announcement" and release_selected >= MAX_COMPANY_RELEASES:
            continue
        # Obvious promotional announcements are retained in raw research data
        # but must not crowd out industry headlines in the curated view.
        if "promotional_or_generic_marketing" in x["needs_editor_review"]:
            continue
        selected.append(x)
        if x["origin"] == "company_announcement":
            release_selected += 1
        counts[x["category"]] += 1
        domains[x["domain"]] += 1
        if len(selected) >= max_stories:
            break
    queue_count = Counter(x["queue"] for x in all_rows)
    beats = Counter(x["category"] for x in selected)
    themes = Counter(t for x in selected for t in x["coverage_themes"])
    return {
        "generated_utc": now.isoformat(),
        "status": "research_only_not_approved",
        "unique_relevant_urls_7d": len(all_rows),
        "selected_research_links": len(selected),
        "unique_domains_in_selection": len({x["domain"] for x in selected}),
        "queue_counts": dict(queue_count),
        "selected_category_counts": {name: beats[name] for name in CATEGORY_ORDER},
        "selected_topic_coverage_counts": {name: themes[name] for name in CATEGORY_ORDER},
        "missing_categories": [name for name in CATEGORY_ORDER if not themes[name]],
        "publisher_timestamped_official_24h": queue_count["timestamped_official"],
        "publisher_timestamped_specialist_24h": queue_count["specialist_publisher_24h"],
        "system_operator_primary_24h": queue_count["system_operator_primary_24h"],
        "likely_same_event_links_suppressed":duplicate_links_suppressed,
        "discovery_publisher_dates_verified": 0,
        "promotional_or_language_review_count": sum(bool(x["needs_editor_review"]) for x in selected),
        "stories": selected,
        "definitions": {
            "timestamped_official": "Publisher-supplied publication datetime on original feeds (official agencies and specialist publishers); content not independently fact-checked",
            "specialist_publisher_24h": "Specialist publisher RSS timestamp, NOT official government news or independently verified content",
            "system_operator_primary_24h": "Original electric-grid system operator RSS timestamp, not a government agency or independent editorial fact check",
            "regulatory_date_only": "Government record with publication DATE, no reliable intraday release timestamp",
            "discovery_unverified": "GDELT index observed a linked article; neither publisher publication date nor facts verified",
            "company_release_unverified": "Third-party press-release aggregator feed date and issuer claims, not independent reporting",
        },
        "disclaimer": "This is a research desk, not a publishable newsletter. Source permissions and facts require editorial review."
    }

def generate(rss_file, discovered_file, release_file, output_dir, now=None):
    result = assemble(load(rss_file, "articles"), load(discovered_file, "leads"),
                      load(release_file, "leads"), now=now)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "desk.json").write_text(json.dumps(result, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    rows = ["# EnergyBrew — private research desk", "",
            "**Research links only. Not fact-checked, approved, or ready for publication.**", "",
            f"Generated (UTC): {result['generated_utc']}",
            f"Distinct relevant URLs in retained data: **{result['unique_relevant_urls_7d']}**",
            f"Selected diverse research leads: **{result['selected_research_links']}**",
            f"Publisher-timestamped official leads within 24h: **{result['publisher_timestamped_official_24h']}**",
            f"Specialist-publisher timestamped links within 24h: **{result['publisher_timestamped_specialist_24h']}**",
            f"Grid-operator original timestamped links within 24h: **{result['system_operator_primary_24h']}**",
            f"Likely duplicate links suppressed in the selection: **{result['likely_same_event_links_suppressed']}**",
            f"Discovery publisher dates verified: **0**", "",
            "## Candidate list", ""]
    if not result["stories"]:
        rows += ["No qualifying news leads observed. Check upstream collection reports."]
    for i, x in enumerate(result["stories"], 1):
        title = x["title"].replace("[", "\\[").replace("]", "\\]").replace("|","/")
        url = x["url"].replace(")", "%29")
        rows.append(f"{i}. **[{title}]({url})** — {x['category']} | {x['origin']} | score {x['relevance_score']}")
        rows.append(f"   - Timestamp basis: {x['time_basis']} ({x['observed_time_utc']}). Editorial status: **unapproved**.")
        if x["needs_editor_review"]:
            rows.append("   - Review flags: " + ", ".join(x["needs_editor_review"]))
        if x["other_origins"]:
            rows.append("   - Also discovered by: " + ", ".join(x["other_origins"]))
        if x.get("related_reports"):
            rows.append(f"   - {len(x['related_reports'])} likely same-event publisher links preserved for review (not independent corroboration).")
    rows += ["", "## Coverage gaps", ""]
    rows += ["- "+cat for cat in result["missing_categories"]] or ["- No missing category observed in the selected set (not proof of complete coverage)."]
    rows += ["", "## Source-date rules", "",
             "- Official publisher feed timestamp: source-supplied, **not independent fact verification**.",
             "- Government regulatory record: publication date only.",
             "- GDELT: first-seen/index timestamp only; cannot establish article publication time.",
             "- Press releases: feed date and company claims, not independent journalism.",
             "- No source material is automatically published or distributed."]
    (output_dir / "desk.md").write_text("\n".join(rows)+"\n", encoding="utf-8")
    return result

def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--rss-state", default="state/articles.json")
    p.add_argument("--discovery-state", default="state/discovery.json")
    p.add_argument("--releases-state", default="state/press_releases.json")
    p.add_argument("--output", default="output/desk")
    args=p.parse_args(argv)
    r=generate(args.rss_state,args.discovery_state,args.releases_state,args.output)
    print(json.dumps({k:r[k] for k in ("unique_relevant_urls_7d","selected_research_links","queue_counts","missing_categories")},indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
