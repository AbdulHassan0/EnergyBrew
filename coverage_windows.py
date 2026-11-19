"""Bounded estimates of GDELT rolling-window sampling availability.

Each successful GAL request is assumed to expose at most the preceding
15 minutes. This computes the UNION of those potential coverage windows
intersected with a requested evaluation horizon.

The result is an OPTIMISTIC UPPER BOUND of possible GDELT index coverage:
it does not prove all events were indexed, that the feed returned every
article, or that its start and end precisely match these wall-clock times.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

ROLLING_MINUTES = 15


def _aware(value):
    if isinstance(value, datetime):
        result=value
    elif isinstance(value,str):
        try:
            result=datetime.fromisoformat(value.replace("Z","+00:00"))
        except ValueError:
            return None
    else:
        return None
    return result.astimezone(timezone.utc) if result.tzinfo else None


def estimate_sampling_coverage(gal_runs, *, now, hours, window_minutes=ROLLING_MINUTES):
    """Return upper-bound coverage and uncovered spans; no fake backfill."""
    if not isinstance(now,datetime) or not now.tzinfo:
        raise ValueError("now must be an aware datetime")
    if hours<=0 or window_minutes<=0:
        raise ValueError("hours and window_minutes must be positive")
    horizon_end=now.astimezone(timezone.utc)
    horizon_start=horizon_end-timedelta(hours=hours)
    rolling=timedelta(minutes=window_minutes)
    intervals=[]
    for item in gal_runs:
        if not isinstance(item,dict) or item.get("status")!="ok":
            continue
        completed=_aware(item.get("run_utc"))
        if completed is None or completed>horizon_end+timedelta(minutes=5):
            continue
        # Use the run timestamp, not GDELT's ambiguous pubDate, as the
        # observational window anchor.
        left=max(horizon_start,completed-rolling)
        right=min(horizon_end,completed)
        if right>left:
            intervals.append((left,right))
    intervals.sort()
    merged=[]
    for left,right in intervals:
        if merged and left<=merged[-1][1]:
            merged[-1]=(merged[-1][0],max(merged[-1][1],right))
        else:
            merged.append((left,right))
    gaps=[]
    cursor=horizon_start
    for left,right in merged:
        if left>cursor:
            gaps.append((cursor,left))
        cursor=max(cursor,right)
    if cursor<horizon_end:
        gaps.append((cursor,horizon_end))
    total_minutes=hours*60
    observed=sum((right-left).total_seconds()/60 for left,right in merged)
    missing=max(0,total_minutes-observed)
    return {
        "horizon_hours":hours,
        "rolling_window_assumed_minutes":window_minutes,
        "potentially_sampled_minutes_upper_bound":round(observed,1),
        "unobserved_minutes_at_least":round(missing,1),
        "potential_coverage_upper_bound_pct":round(100*observed/total_minutes,2),
        "unobserved_time_spans":[
            {"from_utc":a.isoformat(),"to_utc":b.isoformat(),
             "minutes":round((b-a).total_seconds()/60,1)}
            for a,b in gaps
        ],
        "longest_unobserved_minutes":round(max(((b-a).total_seconds()/60 for a,b in gaps),default=0),1),
        "successfully_timestamped_run_count":len(intervals),
        "warning":"Upper bound on potential indexed time sampled, not verified publisher coverage or recovered missed stories.",
    }
