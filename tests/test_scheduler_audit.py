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
    def test_write_public_diagnostics(self):
        with tempfile.TemporaryDirectory() as d:
            save(analyze(config(),{},NOW),d)
            self.assertIn("At least missing",(Path(d)/"scheduler_audit.md").read_text())
    def test_naive_clock_rejected(self):
        with self.assertRaises(ValueError):
            analyze(config(),{},datetime(2026,11,19,12))
if __name__=="__main__":
    unittest.main()
