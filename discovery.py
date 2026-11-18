"""Broad energy-news discovery using GDELT DOC 2.0, separate from official RSS.

IMPORTANT: GDELT 'seendate' is an index observation, NOT original publication
time. Every discovered URL stays in a private unverified research queue.
No scraping of article pages, redistribution, auto-approval, or email delivery.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from collector import clean_url
from editorial import evaluate

API = "https://api.gdeltproject.org/api/v2/doc/doc"
USER_AGENT = "EnergyBrewResearchCollector/2.0 (+https://github.com/AbdulHassan0/EnergyBrew)"
MAX_BYTES = 1_500_000
MAX_RESULTS = 75
DEFAULT_QUERIES_PER_RUN = 4
TOPICS = (
    ("us_natural_gas", '("natural gas" OR "Henry Hub" OR "Haynesville" OR "gas pipeline")'),
    ("lng_exports", '("LNG export" OR "LNG terminal" OR "LNG cargo" OR "liquefied natural gas")'),
    ("lng_global", '("LNG supply" OR "LNG contract" OR "LNG project" OR "regasification")'),
    ("oil_prices_supply", '("crude oil" OR "Brent crude" OR "WTI crude" OR "OPEC")'),
    ("us_upstream", '("Permian Basin" OR "oil drilling" OR "shale production" OR "offshore oil")'),
    ("gas_pipelines", '("gas transmission" OR "pipeline expansion" OR "pipeline capacity" OR "midstream")'),
    ("power_markets", '("PJM" OR "ERCOT" OR "MISO" OR "power grid" OR "power generation")'),
    ("data_centers", '("data center" OR "AI electricity demand" OR "large load")'),
    ("energy_investment", '("energy acquisition" OR "LNG investment" OR "power investment" OR "energy infrastructure")'),
    ("energy_policy", '("FERC" OR "DOE LNG" OR "energy regulation" OR "electricity regulation")'),
    ("oil_refining", '("refinery" OR "diesel market" OR "gasoline supply" OR "petroleum refining")'),
    ("renewables_nuclear", '("nuclear power" OR "renewable energy" OR "battery storage" OR "offshore wind")'),
)


def utc_stamp(dt):
    return dt.astimezone(timezone.utc).isoformat()


def parse_first_seen(value):
    """Index-first-seen time, deliberately never labeled publication time."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    if re.fullmatch(r"\d{14}", value):
        return datetime.strptime(value, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    if re.fullmatch(r"\d{8}T\d{6}Z", value):
        return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
    except ValueError:
        return None


def api_url(query):
    return API + "?" + urlencode({
        "query": query + " sourcelang:english",
        "mode": "artlist",
        "maxrecords": MAX_RESULTS,
        "timespan": "36h",
        "sort": "datedesc",
        "format": "json",
    })


def fetch_json(url):
    request = Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    })
    with urlopen(request, timeout=20) as response:
        payload = response.read(MAX_BYTES + 1)
        if len(payload) > MAX_BYTES:
            raise ValueError("GDELT response exceeded 1.5 MB limit")
        return payload, response.status


def retry_after_seconds(headers, now):
    default = 90 * 60
    if not headers:
        return default
    raw = headers.get("Retry-After")
    if not raw:
        return default
    try:
        amount = max(0, int(raw))
    except (TypeError, ValueError, OverflowError):
        try:
            target = parsedate_to_datetime(raw)
            if target.tzinfo is None:
                return default
            amount = max(0, int((target.astimezone(timezone.utc) - now).total_seconds()))
        except (TypeError, ValueError, OverflowError, IndexError):
            return default
    # Never hammer the API; also never suppress collection longer than one day.
    return min(24 * 3600, max(30 * 60, amount))


def normalize_results(payload, topic, now):
    """Accept URL/title metadata only; reject impossible index timestamps."""
    if isinstance(payload, bytes):
        try:
            data = json.loads(payload)
        except (ValueError, UnicodeDecodeError):
            raise ValueError("GDELT returned non-JSON data (possibly throttled)")
    elif isinstance(payload, dict):
        data = payload
    else:
        raise ValueError("Invalid GDELT response structure")
    articles = data.get("articles", [])
    if not isinstance(articles, list):
        raise ValueError("GDELT articles is not a list")
    leads = []
    errors = {"invalid_url": 0, "invalid_first_seen": 0, "outside_window": 0}
    for raw in articles[:MAX_RESULTS]:
        if not isinstance(raw, dict):
            continue
        url = clean_url(raw.get("url") or "")
        title = re.sub(r"\s+", " ", str(raw.get("title") or "")).strip()[:300]
        index_time = parse_first_seen(raw.get("seendate"))
        if not url or not title:
            errors["invalid_url"] += 1
            continue
        if index_time is None:
            errors["invalid_first_seen"] += 1
            continue
        if index_time > now + timedelta(hours=1) or index_time < now - timedelta(hours=48):
            errors["outside_window"] += 1
            continue
        q = evaluate(title)
        leads.append({
            "url": url,
            "title": title,
            "domain": urlsplit(url).netloc.lower(),
            "gdelt_first_seen_utc": utc_stamp(index_time),
            "publisher_published_utc": None,
            "published_time_verified": False,
            "discovery_provider": "GDELT DOC 2.0",
            "discovery_topic": topic,
            "topics": [topic],
            "relevance_score": q["relevance_score"],
            "category": q["category"],
            "relevance_evidence": q["evidence"],
            "status": "discovery_only_requires_publisher_verification",
        })
    return leads, errors, len(articles)


def _load_state(path):
    if not path.exists():
        return {"leads": [], "topics": {}, "runs": [], "provider_cooldown_until_utc": None}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("Unusable discovery state; refusing to overwrite") from exc
    if not isinstance(doc, dict) or not isinstance(doc.get("leads"), list):
        raise ValueError("Invalid discovery state schema; refusing to overwrite")
    return doc


def _datetime(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc) if dt.tzinfo else None
    except (TypeError, ValueError):
        return None


def run_discovery(state_path, output_dir, *, now=None, fetcher=None, max_queries=DEFAULT_QUERIES_PER_RUN):
    """Run budgeted GDELT discovery; a provider failure never alters RSS state."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    if not 1 <= max_queries <= len(TOPICS):
        raise ValueError("max_queries must be 1..number of topics")
    fetcher = fetcher or fetch_json
    state = _load_state(state_path)
    topic_state = state.setdefault("topics", {})
    state.setdefault("runs", [])
    prior_leads = state.get("leads", [])
    index = {x["url"]: dict(x) for x in prior_leads if clean_url(x.get("url", ""))}
    cooldown = _datetime(state.get("provider_cooldown_until_utc"))
    history = []
    seen_new = set()
    chosen = []
    if cooldown and cooldown > now:
        state_label = "provider_cooldown"
    else:
        state_label = "attempted"
        ranked = sorted(TOPICS, key=lambda x: (
            _datetime(topic_state.get(x[0], {}).get("last_attempt_utc")) or datetime.min.replace(tzinfo=timezone.utc),
            x[0],
        ))
        chosen = ranked[:max_queries]
        for topic, query in chosen:
            record = topic_state.setdefault(topic, {})
            row = {"topic": topic, "attempted_utc": utc_stamp(now), "status": "pending", "raw_results": 0, "new_urls": 0}
            record["last_attempt_utc"] = utc_stamp(now)
            try:
                body, http_status = fetcher(api_url(query))
                if http_status == 429 or http_status == 503:
                    raise HTTPError(API, http_status, "provider_rate_limit", {}, None)
                if not 200 <= http_status < 300:
                    raise ValueError(f"GDELT HTTP {http_status}")
                items, rejected, raw_count = normalize_results(body, topic, now)
                row.update(status="success", raw_results=raw_count,
                           normalized_results=len(items), rejected=rejected, http_status=http_status)
                record["last_success_utc"] = utc_stamp(now)
                record["consecutive_failures"] = 0
                for item in items:
                    uri = item["url"]
                    previous = index.get(uri)
                    if previous is None:
                        index[uri] = item
                        seen_new.add(uri)
                        row["new_urls"] += 1
                    else:
                        other_topics = set(previous.get("topics") or [])
                        other_topics.add(topic)
                        previous["topics"] = sorted(other_topics)
                        previous["relevance_score"] = max(previous.get("relevance_score", 0), item["relevance_score"])
            except HTTPError as exc:
                row.update(status="rate_limited" if exc.code in (429, 503) else "http_error",
                           http_status=exc.code, error=f"HTTP {exc.code}")
                record["consecutive_failures"] = record.get("consecutive_failures", 0) + 1
                if exc.code in (429, 503):
                    secs = retry_after_seconds(exc.headers, now)
                    state["provider_cooldown_until_utc"] = utc_stamp(now + timedelta(seconds=secs))
                    history.append(row)
                    break
            except Exception as exc:
                row.update(status="error", error=f"{type(exc).__name__}: {str(exc)[:180]}")
                record["consecutive_failures"] = record.get("consecutive_failures", 0) + 1
            history.append(row)
    cutoff = now - timedelta(days=7)
    retained = [v for v in index.values()
                if (_datetime(v.get("gdelt_first_seen_utc")) or datetime.min.replace(tzinfo=timezone.utc)) >= cutoff]
    retained.sort(key=lambda x:(x.get("relevance_score",0), x["gdelt_first_seen_utc"]), reverse=True)
    retained = retained[:4000]
    recent = [x for x in retained if (_datetime(x.get("gdelt_first_seen_utc")) or cutoff) >= now-timedelta(hours=24)]
    result = {
        "run_utc": utc_stamp(now),
        "provider": "GDELT DOC 2.0",
        "status": state_label if state_label == "provider_cooldown" else (
            "ok" if history and all(x["status"] == "success" for x in history)
            else "degraded"),
        "topics_configured": len(TOPICS),
        "topics_attempted": len(history),
        "topics_succeeded": sum(x["status"]=="success" for x in history),
        "topics_pending_or_unsearched": len(TOPICS)-len(history),
        "new_discovered_urls": len(seen_new),
        "leads_in_last_24h_first_seen": len(recent),
        "leads_in_7d_state": len(retained),
        "provider_cooldown_until_utc": state.get("provider_cooldown_until_utc"),
        "topic_attempts": history,
        "notice": "Discovery index timestamps are NOT original article publication dates. All leads need publisher verification before newsletter use.",
    }
    state["leads"] = retained
    prior_runs = [x for x in state.get("runs", [])
                  if (_datetime(x.get("run_utc")) or datetime.min.replace(tzinfo=timezone.utc)) >= cutoff]
    prior_runs.append({k: result[k] for k in ("run_utc","status","topics_attempted",
                                             "topics_succeeded","new_discovered_urls",
                                             "leads_in_last_24h_first_seen")})
    state["runs"] = prior_runs[-100:]
    state_path.parent.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    tmp = state_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2)+"\n", encoding="utf-8")
    tmp.replace(state_path)
    (output_dir/"latest.json").write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
    (output_dir/"leads_24h.json").write_text(json.dumps(recent, indent=2)+"\n", encoding="utf-8")
    (output_dir/"leads_7d.json").write_text(json.dumps(retained, indent=2)+"\n", encoding="utf-8")
    lines = [
        "# EnergyBrew — broad discovery leads", "",
        f"Run UTC: {result['run_utc']}",
        f"GDELT status: **{result['status']}**",
        f"Topics attempted/succeeded: **{result['topics_attempted']}/{result['topics_succeeded']}**",
        f"New URL leads: **{result['new_discovered_urls']}**",
        f"Links first seen by GDELT in past 24h: **{result['leads_in_last_24h_first_seen']}**",
        "", "These are NOT publisher-verified publication dates or approved newsletter stories.",
        "", "| Topic | Result | Raw | New | Error |", "|---|---|---:|---:|---|",
    ]
    for item in history:
        lines.append(f"| {item['topic']} | {item['status']} | {item['raw_results']} | {item['new_urls']} | {item.get('error','')} |")
    (output_dir/"latest.md").write_text("\n".join(lines)+"\n", encoding="utf-8")
    return result


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--state", default="state/discovery.json")
    p.add_argument("--output", default="output/discovery")
    p.add_argument("--max-queries", type=int, default=DEFAULT_QUERIES_PER_RUN)
    args=p.parse_args(argv)
    report=run_discovery(Path(args.state),Path(args.output),max_queries=args.max_queries)
    print(json.dumps({k:v for k,v in report.items() if k!="topic_attempts"},indent=2))
    # An API outage is reported as degraded, not as successfully collected news.
    return 0 if report["topics_succeeded"] else 2


if __name__ == "__main__":
    sys.exit(main())
