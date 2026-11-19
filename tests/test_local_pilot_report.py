"""Observe real on-disk timestamps, never substitute a green code build."""
import json
import tempfile
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from local_pilot_report import inspect

NOW=datetime(2026,11,19,11,0,tzinfo=timezone.utc)
def stamp(n=0):
    return (NOW-timedelta(minutes=n)).isoformat()
def write(root,name,data):
    p=Path(root)/name
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(data),encoding="utf-8")


class PilotTests(unittest.TestCase):
    def test_empty_state_is_not_healthy(self):
        with tempfile.TemporaryDirectory() as d:
            r=inspect(d,now=NOW)
            self.assertEqual(r["status"],"needs_attention")
            self.assertIn("no_recent_local_worker_heartbeat",r["problems"])
            self.assertFalse(r["seven_day_pilot_complete"])

    def test_fresh_collection_is_not_seven_day_pilot(self):
        with tempfile.TemporaryDirectory() as d:
            write(d,"render_worker_heartbeat.json",
                  {"checked_utc":stamp(),"gal_thread_alive":True})
            write(d,"output/gal-worker/worker_health.json",
                  {"status":"healthy","last_success_utc":stamp()})
            write(d,"articles.json",{"runs":[{"run_utc":stamp(5),"feeds_checked":15,
                                          "feeds_connected":15,"scan_state":"healthy"}]})
            write(d,"discovery.json",{"gal_runs":[{"run_utc":stamp(1),"status":"ok"}]})
            r=inspect(d,now=NOW)
            self.assertEqual(r["problems"],["seven_day_sampling_reliability_not_yet_proven"])
            self.assertNotEqual(r["status"],"production_ready")

    def test_missing_morning_job_detected_after_0700_local(self):
        with tempfile.TemporaryDirectory() as d:
            morning=datetime(2026,11,19,14,10,tzinfo=timezone.utc)
            r=inspect(d,now=morning)
            self.assertIn("morning_final_job_not_recorded_after_0700",r["problems"])
            self.assertEqual(r["morning_date_local"],"2026-11-19")

    def test_explicitly_blocked_morning_job_is_not_healthy(self):
        with tempfile.TemporaryDirectory() as d:
            write(d,"render_schedule.json",{"dates":{"2026-11-19":{
                  "research_final":{"status":"blocked"}}}})
            r=inspect(d,now=datetime(2026,11,19,14,10,tzinfo=timezone.utc))
            self.assertIn("morning_final_job_blocked",r["problems"])

    def test_malformed_state_fails_instead_of_returning_green(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d)/"render_worker_heartbeat.json").write_text("[]")
            with self.assertRaises(ValueError):
                inspect(d,now=NOW)

    def test_naive_clock_rejected(self):
        with self.assertRaises(ValueError):
            inspect("/tmp",now=datetime(2026,11,19,11,0))


if __name__=="__main__":
    unittest.main()
