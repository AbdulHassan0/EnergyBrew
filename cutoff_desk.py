"""Build a cutoff-proven morning research desk from retained public metadata.

This is a research handoff only. It intentionally excludes records first
collected after 06:30 Central and legacy records with no local observation
time. GDELT provider timestamps are never treated as publisher publication.
"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from morning_readiness import DEFAULT_ZONE, local_schedule, prepare
from research_desk import as_time

LANES = (("rss", "articles"), ("discovery", "leads"), ("releases", "leads"))


def cutoff_desk(rss: dict, discovery: dict, releases: dict, *,
                now: datetime | None = None, edition_date: date | str | None = None,
                zone: str = DEFAULT_ZONE) -> dict:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Current time must be timezone-aware")
    now = now.astimezone(timezone.utc)
    day = edition_date or now.astimezone(ZoneInfo(zone)).date()
    schedule = local_schedule(day, zone)
    cutoff = as_time(schedule["news_cutoff_utc"])
    if now < cutoff:
        raise ValueError("Cannot generate final morning research before 06:30 local cutoff")

    retained = []
    excluded = {}
    for (lane, key), state in zip(LANES, (rss, discovery, releases)):
        if not isinstance(state, dict) or not isinstance(state.get(key), list):
            raise ValueError(f"Missing or invalid {lane} public research state")
        selected = []
        missing_observed = 0
        after_cutoff = 0
        for item in state[key]:
            if not isinstance(item, dict):
                continue
            first = as_time(item.get("first_collector_observed_utc") or
                            item.get("first_collected_utc"))
            if first is None:
                missing_observed += 1
            elif first > cutoff:
                after_cutoff += 1
            else:
                selected.append(item)
        retained.append({**state, key: selected})
        excluded[lane] = {
            "unknown_first_collection_time": missing_observed,
            "first_collected_after_cutoff": after_cutoff,
        }
    result = prepare(*retained, now=now, edition_date=day, zone=zone)
    desk = result["research_desk"]
    desk["cutoff_provenance"] = {
        "news_cutoff_utc": cutoff.isoformat(),
        "edition_date": schedule["edition_date"],
        "selected_records_require_known_pre_cutoff_observation": True,
        "excluded_records_by_lane": excluded,
        "readiness_status": result["status"],
        "readiness_blocking_issues": result["blocking_issues"],
        "warning": "Source metadata only; no original-page fact verification or approval.",
    }
    if any(not x.get("local_collection_time_known") or
           as_time(x.get("first_collector_observed_utc")) is None or
           as_time(x["first_collector_observed_utc"]) > cutoff
           for x in desk["stories"]):
        raise ValueError("Cutoff desk unexpectedly contains unproven source observations")
    return desk


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--rss", type=Path, required=True)
    p.add_argument("--discovery", type=Path, required=True)
    p.add_argument("--releases", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--edition-date")
    p.add_argument("--zone", default=DEFAULT_ZONE)
    args = p.parse_args(argv)
    data = []
    for path in (args.rss, args.discovery, args.releases):
        obj = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(obj, dict):
            raise ValueError(f"Invalid research JSON object: {path}")
        data.append(obj)
    desk = cutoff_desk(*data, edition_date=args.edition_date, zone=args.zone)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.output.with_suffix(".tmp")
    tmp.write_text(json.dumps(desk, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(args.output)
    print(json.dumps({
        "edition_date": desk["cutoff_provenance"]["edition_date"],
        "candidate_count": desk["selected_research_links"],
        "readiness_status": desk["cutoff_provenance"]["readiness_status"],
        "cutoff_proven": True, "research_only": True,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
