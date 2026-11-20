import tempfile
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from scheduler_audit import analyze,count_slots,save

NOW=datetime(2026,11,19,12,tzinfo=timezone.utc)
def config(hours=24):
    return {name:{"updated_at":(NOW-timedelta(hours=hours)).isoformat()}
            for name in ("frequent-gal.yml","hourly-discovery.yml")}
def run(i,result="success"):
    return {"created_at":(NOW-timedelta(minutes=10*i)).isoformat(),
            "event":"schedule","conclusion":result}

class AuditTests(unittest.TestCase):
    def test_nominal_slots(self):
        self.assertEqual(count_slots(NOW-timedelta(hours=24),NOW-timedelta(minutes=20),(6,16,26,36,46,56)),142)
    def test_missing_schedules_are_critical(self):
        r=analyze(config(),{},NOW)
        self.assertEqual(r["status"],"critical")
        self.assertGreater(r["workflows"][0]["minimum_missing_events"],100)
    def test_deployment_warmup(self):
        self.assertEqual(analyze(config(1),{},NOW)["status"],"warming_up")
    def test_backup_does_not_hide_primary_failure(self):
        r=analyze(config(),{"hourly-discovery.yml":[run(i) for i in range(1,142)]},NOW)
        self.assertEqual(r["status"],"degraded")
    def test_ignore_push_runs(self):
        r=analyze(config(),{"frequent-gal.yml":[{"event":"push","created_at":NOW.isoformat()}]*200},NOW)
        self.assertEqual(r["workflows"][0]["schedule_runs_seen"],0)
    def test_failures_are_not_successful_runs(self):
        r=analyze(config(),{"frequent-gal.yml":[run(i,"failure") for i in range(1,142)]},NOW)
        self.assertEqual(r["workflows"][0]["failed"],141)
    def test_routine_workflow_edit_does_not_reset_schedule_window(self):
        workflows={name:{
            "created_at":(NOW-timedelta(days=10)).isoformat(),
            "updated_at":(NOW-timedelta(minutes=30)).isoformat()}
            for name in ("frequent-gal.yml","hourly-discovery.yml")}
        result=analyze(workflows,{},NOW)
        self.assertEqual(result["status"],"critical")
        self.assertGreater(result["workflows"][0]["nominal_eligible_slots"],100)

    def test_pending_queue_and_run_start_delay_are_exposed(self):
        workflows=config()
        entries=[{
            "created_at":(NOW-timedelta(minutes=20)).isoformat(),
            "run_started_at":(NOW-timedelta(minutes=7)).isoformat(),
            "event":"schedule","status":"completed","conclusion":"success",
        },{
            "created_at":(NOW-timedelta(minutes=15)).isoformat(),
            "event":"schedule","status":"queued","conclusion":None,
        },{
            "created_at":(NOW-timedelta(minutes=8)).isoformat(),
            "event":"schedule","status":"completed","conclusion":"cancelled",
        }]
        result=analyze(workflows,{"frequent-gal.yml":entries},NOW)
        first=result["workflows"][0]
        self.assertEqual(first["cancelled"],1)
        self.assertEqual(first["queued_or_in_progress"],1)
        self.assertEqual(first["max_observed_run_start_delay_minutes"],13)
        self.assertEqual(first["oldest_pending_run_minutes"],15)

    def test_stalled_pending_runs_degrade_even_when_slots_filled(self):
        full=[run(i) for i in range(142)]
        full[3]["status"]="queued"
        full[3]["conclusion"]=None
        result=analyze(config(),{
            "frequent-gal.yml":full,
            "hourly-discovery.yml":[run(i) for i in range(142)]
        },NOW)
        primary=result["workflows"][0]
        self.assertEqual(primary["run_count_ratio_upper_bound"],1)
        self.assertEqual(primary["stalled_pending_runs"],1)
        self.assertEqual(primary["status"],"degraded")
        self.assertEqual(result["status"],"degraded")

    def test_write_public_diagnostics(self):
        with tempfile.TemporaryDirectory() as d:
            save(analyze(config(),{},NOW),d)
            self.assertIn("At least missing",(Path(d)/"scheduler_audit.md").read_text())
    def test_naive_clock_rejected(self):
        with self.assertRaises(ValueError):
            analyze(config(),{},datetime(2026,11,19,12))
if __name__=="__main__":
    unittest.main()
