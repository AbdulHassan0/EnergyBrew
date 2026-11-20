"""Monotonic GAL report persistence after independently timed source fetches."""
import json
import tempfile
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from gal_persist_report import finish

NOW=datetime(2026,11,20,18,0,tzinfo=timezone.utc)


def dt(minutes):
    return (NOW+timedelta(minutes=minutes)).isoformat()


def record(uri,minute):
    return {"url":uri,"title":"Cheniere LNG expansion moves forward",
            "gdelt_first_seen_utc":dt(minute),
            "publisher_published_utc":None,"published_time_verified":False}


class GalPersistReportTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.samples=self.root/"sample"
        self.samples.mkdir()
        (self.samples/"latest.json").write_text(json.dumps({"run_utc":dt(-10),"completed_utc":dt(-9),"status":"ok"}))
        (self.samples/"latest.md").write_text("# Sampled GAL evidence\n")

    def test_older_delayed_sample_cannot_downgrade_newer_gal_latest(self):
        state={"leads":[record("https://a.example/old", -8),
                        record("https://b.example/new", -2)],
               "gal_runs":[{"run_utc":dt(-10),"status":"ok"}]}
        prev={"run_utc":dt(-4),"completed_utc":dt(-3),"status":"ok"}
        (self.root/"out").mkdir()
        (self.root/"out"/"gal_latest.json").write_text(json.dumps(prev))
        (self.root/"out"/"gal_latest.md").write_text("# Newer GAL\n")
        result=finish(state,{"run_utc":dt(-10),"completed_utc":dt(-9)},
                      prev,outdir=self.root/"out",sample_dir=self.samples,now=NOW)
        self.assertFalse(result["new_sample_is_latest"])
        self.assertEqual(json.loads((self.root/"out"/"gal_latest.json").read_text()),prev)
        self.assertEqual(result["recent_leads"],2)

    def test_last_24h_uses_exact_rolling_window_not_midnight(self):
        state={"leads":[record("https://a.example/recent",-23*60),
                        record("https://b.example/older",-26*60)],
               "gal_runs":[]}
        result=finish(state,{"run_utc":dt(-10),"completed_utc":dt(-9)},
                      {},outdir=self.root/"out",sample_dir=self.samples,now=NOW)
        self.assertEqual(result["recent_leads"],1)
        rows=json.loads((self.root/"out"/"research_leads_24h.json").read_text())
        self.assertEqual(rows[0]["url"],"https://a.example/recent")
        self.assertEqual(json.loads((self.root/"out"/"gal_latest.json").read_text())["status"],"ok")

    def test_missing_report_does_not_masquerade_as_success(self):
        (self.samples/"latest.md").unlink()
        with self.assertRaises(FileNotFoundError):
            finish({"leads":[],"gal_runs":[]},
                   {"run_utc":dt(-10),"completed_utc":dt(-9)},
                   None,outdir=self.root/"out",sample_dir=self.samples,now=NOW)

    def test_naive_completion_clock_is_rejected(self):
        with self.assertRaisesRegex(ValueError,"timezone"):
            finish({"leads":[],"gal_runs":[]},{"run_utc":dt(-1)},
                   None,outdir=self.root/"out",sample_dir=self.samples,
                   now=datetime(2026,11,20,18,0))


if __name__ == "__main__":
    unittest.main()
