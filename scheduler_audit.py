"""Measure actual GitHub scheduled collector events, separately from GDELT RSS health."""
from __future__ import annotations
import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

CRONS = {"frequent-gal.yml": (6,16,26,36,46,56),
         "hourly-discovery.yml": (1,11,21,31,41,51)}
GRACE = timedelta(minutes=20)

def parse_time(value):
    if isinstance(value, str):
        try:
            value=datetime.fromisoformat(value.replace("Z","+00:00"))
        except ValueError:
            return None
    return value.astimezone(timezone.utc) if isinstance(value,datetime) and value.tzinfo else None

def count_slots(start, end, minutes):
    if not start.tzinfo or not end.tzinfo:
        raise ValueError("Timezone-aware times required")
    start,end=start.astimezone(timezone.utc),end.astimezone(timezone.utc)
    hour=start.replace(minute=0,second=0,microsecond=0)
    total=0
    while hour<=end:
        total+=sum(start<=hour+timedelta(minutes=m)<=end for m in minutes)
        hour+=timedelta(hours=1)
    return total

def analyze(workflows, runs, now):
    now=parse_time(now)
    if now is None:
        raise ValueError("Timezone-aware clock required")
    rows=[]
    for name,minutes in CRONS.items():
        wf=workflows.get(name)
        if not isinstance(wf,dict):
            raise ValueError("Workflow metadata missing: "+name)
        deployed=parse_time(wf.get("updated_at")) or parse_time(wf.get("created_at"))
        if deployed is None:
            raise ValueError("Workflow deployment timestamp missing: "+name)
        start=max(now-timedelta(hours=24),deployed)
        end=now-GRACE
        nominal=count_slots(start,end,minutes)
        entries=[r for r in runs.get(name,[]) if isinstance(r,dict)
                 and r.get("event")=="schedule"
                 and (t:=parse_time(r.get("created_at"))) is not None
                 and start<=t<=now]
        actual=len(entries)
        bad=sum(r.get("conclusion") in ("failure","cancelled","timed_out") for r in entries)
        good=sum(r.get("conclusion")=="success" for r in entries)
        ratio=min(1,actual/nominal) if nominal else None
        hours=max(0,(end-start).total_seconds()/3600)
        state=("warming_up" if hours<3 or not nominal else
               "critical" if ratio<.4 else
               "degraded" if ratio<.8 or bad else "observed")
        rows.append({"workflow":name,"status":state,
                     "nominal_eligible_slots":nominal,
                     "schedule_runs_seen":actual,"succeeded":good,"failed":bad,
                     "minimum_missing_events":max(0,nominal-actual),
                     "run_count_ratio_upper_bound":round(ratio,3) if ratio is not None else None,
                     "evaluated_hours":round(hours,2)})
    mature=[r for r in rows if r["status"]!="warming_up"]
    overall=("warming_up" if not mature else
             "critical" if all(r["status"]=="critical" for r in mature) else
             "degraded" if any(r["status"] in ("degraded","critical") for r in mature) else "observed")
    return {"checked_utc":now.isoformat(),"status":overall,"workflows":rows,
            "caution":"Optimistic counts of GitHub schedule events versus nominal cron slots; delayed events cannot be attributed to exact slots. Does not prove GAL article capture or complete news coverage."}

def request_json(url,token):
    headers={"Accept":"application/vnd.github+json","User-Agent":"EnergyBrewNewsSchedulerAudit/1"}
    if token:
        headers["Authorization"]="Bearer "+token
    with urlopen(Request(url,headers=headers),timeout=15) as r:
        return json.load(r)

def live(repo,token,now):
    base="https://api.github.com/repos/"+repo+"/actions/workflows/"
    since=(now-timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
    meta={}
    runs={}
    for name in CRONS:
        meta[name]=request_json(base+name,token)
        items=[]
        complete=False
        for page in range(1,6):
            query=urlencode({"event":"schedule","created":">="+since,
                             "per_page":100,"page":page})
            part=request_json(base+name+"/runs?"+query,token).get("workflow_runs")
            if not isinstance(part,list):
                raise ValueError("Malformed GitHub workflow response: "+name)
            items.extend(part)
            if len(part)<100:
                complete=True
                break
        if not complete:
            raise ValueError("Incomplete scheduler audit pagination: "+name)
        runs[name]=items
    return analyze(meta,runs,now)

def save(result,directory):
    p=Path(directory)
    p.mkdir(parents=True,exist_ok=True)
    (p/"scheduler_audit.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    lines=["# EnergyBrew collector scheduler audit","","Status: "+result["status"],"",
           "| Workflow | Status | Nominal slots | Scheduled run events | Successful | Failed | At least missing |",
           "|---|---|---:|---:|---:|---:|---:|"]
    for x in result["workflows"]:
        lines.append("| {workflow} | {status} | {nominal_eligible_slots} | {schedule_runs_seen} | {succeeded} | {failed} | {minimum_missing_events} |".format(**x))
    lines+=["",result["caution"]]
    (p/"scheduler_audit.md").write_text("\n".join(lines)+"\n",encoding="utf-8")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--repo",default=os.environ.get("GITHUB_REPOSITORY","AbdulHassan0/EnergyBrew"))
    p.add_argument("--output",default="output/scheduler")
    args=p.parse_args()
    result=live(args.repo,os.getenv("GITHUB_TOKEN"),datetime.now(timezone.utc))
    save(result,args.output)
    print(json.dumps(result,indent=2))
    return 2 if result["status"]=="critical" else 0
if __name__=="__main__":
    raise SystemExit(main())
