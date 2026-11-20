"""Merge independently sampled GAL state into the latest committed research state.

Network polling must not wait for the collector-state writer lock. Every
sample is fetched independently and merged only inside a serialized writer
job. This module never infers coverage for time windows not actually polled.
"""
from __future__ import annotations
import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from discovery import _datetime
from editorial import evaluate, non_article_reason
from gal import MAX_RUN_HISTORY


def _timestamp(item, field):
    stamp = _datetime(item.get(field))
    return stamp.astimezone(timezone.utc) if stamp and stamp.tzinfo else None


def _first_seen(a, b):
    stamps = [x for x in (_timestamp(a, "first_collector_observed_utc"),
                         _timestamp(b, "first_collector_observed_utc")) if x]
    return min(stamps).isoformat() if stamps else None


def _union_lead(existing, sampled):
    """Keep latest known source links while preserving earliest local observation."""
    row = dict(existing)
    for key, value in sampled.items():
        if key not in row or row[key] in (None, "", []):
            row[key] = value
    for key in ("topics", "discovery_providers"):
        value = set(existing.get(key) or []) | set(sampled.get(key) or [])
        if value:
            row[key] = sorted(value)
    providers = set(row.get("discovery_providers") or [])
    for item in (existing, sampled):
        if item.get("discovery_provider"):
            providers.add(item["discovery_provider"])
    if providers:
        row["discovery_providers"] = sorted(providers)
    first = _first_seen(existing, sampled)
    if first:
        row["first_collector_observed_utc"] = first
    # A second provider's claim is never enough to verify publisher time.
    if "gdelt_first_seen_utc" in row:
        row["publisher_published_utc"] = None
        row["published_time_verified"] = False
    quality = evaluate(row.get("title", ""))
    row.update(category=quality["category"], relevance_score=quality["relevance_score"],
               relevance_evidence=quality["evidence"])
    return row


def merge(base: dict, sampled: dict, *, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Merge clock must include timezone")
    now = now.astimezone(timezone.utc)
    for label, state in (("base", base), ("sampled", sampled)):
        if not isinstance(state, dict) or not isinstance(state.get("leads"), list):
            raise ValueError(f"{label} state must contain list of leads")
        if not isinstance(state.get("gal_runs", []), list):
            raise ValueError(f"{label} gal_runs must be a list")
    merged = dict(base)
    by_url = {}
    for record in base["leads"]:
        if isinstance(record, dict) and isinstance(record.get("url"), str):
            by_url[record["url"]] = dict(record)
    sample_urls = set()
    for record in sampled["leads"]:
        if not isinstance(record, dict) or not isinstance(record.get("url"), str):
            raise ValueError("Sampled news record missing URL")
        url = record["url"]
        sample_urls.add(url)
        if url in by_url:
            by_url[url] = _union_lead(by_url[url], record)
        else:
            by_url[url] = dict(record)

    # A full snapshot is produced by gal.py. It may contain base records
    # from minutes earlier, so deletion in that old snapshot is not a delete
    # instruction against the newer committed research history.
    age_cutoff = now - timedelta(days=7)
    records = []
    for row in by_url.values():
        if non_article_reason(row.get("title", ""), row.get("url", "")):
            continue
        quality = evaluate(row.get("title", ""))
        if (quality["relevance_score"] < 22 and
            row.get("discovery_provider") == "GDELT GAL RSS" and
            "GDELT DOC 2.0" not in row.get("discovery_providers", [])):
            continue
        first = _timestamp(row, "gdelt_first_seen_utc")
        if first is not None and first < age_cutoff:
            continue
        records.append(row)
    records.sort(key=lambda row: (row.get("relevance_score", 0),
                                  row.get("gdelt_first_seen_utc", "")), reverse=True)
    merged["leads"] = records[:4000]

    # The sample run may have been fetched before other writers committed.
    # Merge by unique observed-start and finish timestamps, never append
    # blindly, and never let a delayed writer erase newer successful polls.
    runs = {}
    for source in (base.get("gal_runs", []), sampled.get("gal_runs", [])):
        for run in source:
            if not isinstance(run, dict):
                continue
            started = _timestamp(run, "run_utc")
            if started is None or started > now + timedelta(minutes=10):
                continue
            if started < now - timedelta(days=8):
                continue
            key = (run.get("run_utc"), run.get("completed_utc", ""))
            runs[key] = run
    chronological = sorted(runs.values(),
                           key=lambda row: (_timestamp(row, "run_utc"),
                                            row.get("completed_utc") or ""))
    merged["gal_runs"] = chronological[-MAX_RUN_HISTORY:]

    # Preserve any newer DOC cooldown or topic bookkeeping written during
    # the time between sampling and committing.
    for key in ("topics", "runs", "provider_cooldown_until_utc",
                "provider_throttle_streak"):
        if key not in merged and key in sampled:
            merged[key] = sampled[key]
    return merged


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--base", type=Path, required=True)
    p.add_argument("--sample", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args(argv)
    def load(path):
        if not path.is_file():
            raise FileNotFoundError(f"Required GAL merge state missing: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Invalid GAL merge state object")
        return data
    merged = merge(load(args.base), load(args.sample))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.output.with_suffix(".tmp")
    tmp.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    tmp.replace(args.output)
    print(json.dumps({"gal_runs": len(merged["gal_runs"]),
                      "research_links": len(merged["leads"]),
                      "mode": "serialized_merge_after_independent_fetch"}, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
