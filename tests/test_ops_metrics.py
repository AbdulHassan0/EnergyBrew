import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ops_metrics import create, report

NOW=datetime(2026,11,18,20,0,tzinfo=timezone.utc)
def stamp(minutes_ago):
    return (NOW-timedelta(minutes=minutes_ago)).isoformat()

class MetricsTests(unittest.TestCase):
    def test_empty_system_is_not_healthy(self):
        r=create({}, {}, now=NOW)
        self.assertFalse(r["seven_day_pilot_complete"])
        self.assertEqual(r["status"],"degraded")
        self.assertTrue(any("missing" in x.lower() for x in r["warnings"]))

    def test_gal_sampling_gap_and_source_date_distinction(self):
        rss={"runs":[{"run_utc":stamp(10),"feeds_connected":2}],
             "articles":[{"url":"https://gov.test/1","published_utc":stamp(30),
                          "published_precision":"timestamp","editorial_candidate":True}]}
        discovery={"gal_runs":[
            {"run_utc":stamp(55),"status":"ok"},
            {"run_utc":stamp(10),"status":"ok"}],
            "leads":[{"url":"https://media.test/a","gdelt_first_seen_utc":stamp(20)}]}
        releases={"leads":[{"url":"https://wire.test/b","feed_published_utc":stamp(25)}]}
        r=create(rss,discovery,releases,now=NOW)
        self.assertEqual(r["gal_sample_runs"],2)
        self.assertEqual(len(r["observed_sampling_gaps"]),1)
        self.assertEqual(r["daily"][-1]["high_signal_official_links"],1)
        self.assertEqual(r["daily"][-1]["gdelt_index_first_seen_urls"],1)
        self.assertEqual(r["daily"][-1]["press_release_feed_date_urls"],1)
        self.assertFalse(r["seven_day_pilot_complete"])

    def test_recent_regular_samples_do_not_report_gap(self):
        discovery={"gal_runs":[{"run_utc":stamp(20),"status":"ok"},
                              {"run_utc":stamp(5),"status":"ok"}]}
        rss={"runs":[{"run_utc":stamp(5),"feeds_connected":1}]}
        r=create(rss,discovery,now=NOW)
        self.assertFalse(r["observed_sampling_gaps"])
        self.assertEqual(r["gal_successful_samples"],2)
        self.assertEqual(r["gal_failed_samples"],0)

    def test_grid_operator_is_neither_agency_nor_independent_publisher(self):
        rss={"runs":[{"run_utc":stamp(5),"feeds_connected":1}],
             "articles":[{"url":"https://pjm.test/1","published_utc":stamp(10),
                         "published_precision":"timestamp","source_class":"system_operator_primary",
                         "editorial_candidate":True}]}
        d=create(rss,{},now=NOW)["daily"][-1]
        self.assertEqual(d["publisher_timestamped_official_links"],0)
        self.assertEqual(d["specialist_publisher_timestamped_links"],0)
        self.assertEqual(d["grid_operator_primary_timestamped_links"],1)

    def test_source_class_counts_do_not_mislabel_specialist_as_official(self):
        rss={"runs":[{"run_utc":stamp(5),"feeds_connected":2}],
             "articles":[{"url":"https://publisher.test/1","published_utc":stamp(10),
                         "published_precision":"timestamp","source_class":"specialist_publisher",
                         "editorial_candidate":True}]}
        report=create(rss,{},now=NOW)
        today=report["daily"][-1]
        self.assertEqual(today["publisher_timestamped_official_links"],0)
        self.assertEqual(today["specialist_publisher_timestamped_links"],1)
        self.assertEqual(today["high_signal_official_links"],0)

    def test_all_failed_scans_do_not_mark_health_ok(self):
        rss={"runs":[{"run_utc":stamp(3),"feeds_connected":0}]}
        discovery={"gal_runs":[{"run_utc":stamp(2),"status":"degraded"}]}
        r=create(rss,discovery,now=NOW)
        self.assertEqual(r["official_scan_runs"],1)
        self.assertEqual(r["official_successful_scans"],0)
        self.assertIsNone(r["latest_official_scan_utc"])
        self.assertIsNone(r["latest_gal_sample_utc"])
        self.assertEqual(r["status"],"degraded")
        self.assertFalse(r["daily"][-1]["successful_scanning_observed"])

    def test_report_outputs_readable_files(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            p=root/"rss.json"
            p.write_text(json.dumps({"runs":[{"run_utc":stamp(2)}]}))
            r=report(p,root/"missing.json",root/"missing2.json",root/"out",now=NOW)
            self.assertTrue((root/"out/metrics.json").exists())
            self.assertIn("Unknown", (root/"out/metrics.md").read_text().replace("unknown","Unknown"))
            self.assertFalse(r["seven_day_pilot_complete"])

if __name__=="__main__":
    unittest.main()
