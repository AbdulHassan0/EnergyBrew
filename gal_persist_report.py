"""Finalize independently sampled GAL results without downgrading newer state.

Called only under shared collector-state writer lock, after GAL merge.
Does not fetch news, alter publisher timestamps, or approve source links.
"""
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from research_desk import as_time


def finish(merged: dict, sample_report: dict, previous_report: dict | None,
           *, outdir: Path, sample_dir: Path, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Completion clock must be timezone-aware")
    old = previous_report if isinstance(previous_report, dict) else {}
    fresh_time = as_time(sample_report.get("completed_utc") or sample_report.get("run_utc"))
    old_time = as_time(old.get("completed_utc") or old.get("run_utc"))
    if fresh_time is None:
        raise ValueError("Sample lacks completion timestamp")
    if not isinstance(merged.get("leads"), list) or not isinstance(merged.get("gal_runs"), list):
        raise ValueError("Invalid merged research state")

    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    latest_kept = old_time is None or fresh_time >= old_time
    if latest_kept:
        for src,dest in (("latest.json","gal_latest.json"),
                         ("latest.md","gal_latest.md")):
            source = Path(sample_dir) / src
            if not source.is_file():
                raise FileNotFoundError(f"GAL sample report missing: {source}")
            shutil.copyfile(source,outdir/dest)

    # A delayed sampler must not rewind the 24-hour lead window.
    anchor=max(now.astimezone(timezone.utc),fresh_time,
               old_time if old_time else fresh_time)
    records=[]
    for item in merged["leads"]:
        if not isinstance(item,dict):
            raise ValueError("Merged lead is not an object")
        observed=as_time(item.get("gdelt_first_seen_utc"))
        if observed is not None and observed <= anchor + timedelta(minutes=10):
            records.append(item)
    records.sort(key=lambda item:item.get("gdelt_first_seen_utc",""),reverse=True)
    (outdir/"research_leads_7d.json").write_text(
        json.dumps(records,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    current=[item for item in records
             if as_time(item["gdelt_first_seen_utc"]) >= anchor-timedelta(hours=24)]
    (outdir/"research_leads_24h.json").write_text(
        json.dumps(current,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    return {"retained_leads":len(records),"recent_leads":len(current),
            "new_sample_is_latest":latest_kept,
            "observed_coverage_not_inferred":True}


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--merged",type=Path,required=True)
    p.add_argument("--sample-report",type=Path,required=True)
    p.add_argument("--sample-dir",type=Path,required=True)
    p.add_argument("--previous-report",type=Path)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args(argv)
    def get(path):
        if path is None or not path.is_file():
            return None
        data=json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data,dict):
            raise ValueError(f"Invalid GAL report JSON: {path}")
        return data
    merged=get(args.merged)
    sample=get(args.sample_report)
    if not merged or not sample:
        raise ValueError("Missing GAL merged state or sampled report")
    result=finish(merged,sample,get(args.previous_report),
                  outdir=args.output,sample_dir=args.sample_dir)
    print(json.dumps(result,indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
