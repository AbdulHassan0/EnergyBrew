"""Probe documented GDELT GAL minute archives without downloading article data.

HEAD-only availability and response headers; this is NOT a backfill implementation.
GDELT's 2021 documentation advertises YYYYMMDDHHMMSS.gal.json.gz archives,
but endpoint availability must be verified from a hosted collector before use.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE = "https://data.gdeltproject.org/gdeltv3/gal/"
DOCUMENTED_EXAMPLE = "20200101000100.gal.json.gz"


def targets(now: datetime) -> list[str]:
    if now.tzinfo is None:
        raise ValueError("Timezone-aware UTC clock required")
    now = now.astimezone(timezone.utc)
    # Probe sparse recent minutes, not the entire archive.
    names = [DOCUMENTED_EXAMPLE]
    for age in (20, 30, 31, 45, 60, 90):
        stamp = (now - timedelta(minutes=age)).replace(second=0, microsecond=0)
        names.append(stamp.strftime("%Y%m%d%H%M%S") + ".gal.json.gz")
    return list(dict.fromkeys(BASE + name for name in names))


def head_status(url: str) -> tuple[int, dict]:
    req = Request(url, headers={"User-Agent": "EnergyBrewArchiveAvailabilityProbe/1.0 (+https://github.com/AbdulHassan0/EnergyBrew)"}, method="HEAD")
    try:
        with urlopen(req, timeout=9) as response:
            return response.status, {
                "content_type": response.headers.get("Content-Type"),
                "content_length": response.headers.get("Content-Length"),
            }
    except HTTPError as exc:
        return exc.code, {"content_type": None, "content_length": None}


def probe(now: datetime | None = None, fetcher=None) -> dict:
    now = now or datetime.now(timezone.utc)
    fetcher = fetcher or head_status
    rows = []
    for url in targets(now):
        row = {"url": url, "status": "unavailable", "http_status": None,
               "content_length": None, "content_type": None}
        try:
            status, details = fetcher(url)
            row.update(http_status=status, content_length=details.get("content_length"),
                       content_type=details.get("content_type"))
            row["status"] = "head_confirmed" if status == 200 else (
                "head_unsupported" if status in (405, 501) else "unavailable")
        except Exception as exc:
            row["error"] = type(exc).__name__ + ": " + str(exc)[:140]
        rows.append(row)
    return {
        "checked_utc": now.astimezone(timezone.utc).isoformat(),
        "status": "archive_endpoint_potentially_available" if any(x["status"]=="head_confirmed" for x in rows)
                  else "not_confirmed",
        "head_confirmed": sum(x["status"]=="head_confirmed" for x in rows),
        "tested": len(rows),
        "samples": rows,
        "caution": "HEAD-only probe does not prove files contain usable records, full historical coverage, or future availability; no article text downloaded.",
    }


def write_report(report: dict, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out/"gal_archive_probe.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    lines = ["# GDELT GAL historical minute archive availability — HEAD-only", "",
             "Run UTC: " + report["checked_utc"],
             "Confirmed HEAD 200: " + str(report["head_confirmed"]) + "/" + str(report["tested"]),
             "Status: " + report["status"], "",
             "| Endpoint | HTTP status | Content-Length | Probe |",
             "|---|---|---:|---|"]
    for row in report["samples"]:
        lines.append(f"| {row['url']} | {row['http_status'] or 'unknown'} | {row['content_length'] or '-'} | {row['status']} |")
    lines.extend(["", report["caution"]])
    (out/"gal_archive_probe.md").write_text("\n".join(lines)+"\n", encoding="utf-8")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, default=Path("output/source_probe"))
    args = p.parse_args()
    result = probe()
    write_report(result, args.output)
    print(json.dumps({"status": result["status"], "confirmed": result["head_confirmed"],
                      "tested": result["tested"], "samples": result["samples"]}, indent=2))
