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
    def test_future_completion_not_counted_as_healthy_even_if_started_early(self):
        rss={"runs":[{"run_utc":stamp(6),
                      "completed_utc":(NOW+timedelta(minutes=2)).isoformat(),
                      "scan_state":"healthy","feeds_checked":15,"feeds_connected":15}]}
        gal={"gal_runs":[{"run_utc":stamp(5),
                          "completed_utc":(NOW+timedelta(minutes=1)).isoformat(),
                          "status":"ok"}]}
        metric=create(rss,gal,now=NOW)
        self.assertIsNone(metric["latest_official_scan_utc"])
        self.assertIsNone(metric["latest_gal_sample_utc"])
        self.assertEqual(metric["official_successful_scans"],0)
        self.assertEqual(metric["gal_successful_samples"],0)
        self.assertEqual(metric["gal_sampled_window_24h"]["potential_coverage_upper_bound_pct"],0)

    def test_actual_completion_replaces_start_as_freshness_reference(self):
        rss={"runs":[{"run_utc":stamp(15),"completed_utc":stamp(3),
                      "scan_state":"healthy","feeds_checked":15,"feeds_connected":15}]}
        gal={"gal_runs":[{"run_utc":stamp(20),"completed_utc":stamp(5),
                          "status":"ok"}]}
        metric=create(rss,gal,now=NOW)
        self.assertEqual(metric["latest_official_scan_utc"],stamp(3))
        self.assertEqual(metric["latest_gal_sample_utc"],stamp(5))
        self.assertEqual(metric["latest_gal_age_minutes"],5)

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

    def test_single_connected_feed_does_not_count_as_successful_scan(self):
        rss={"runs":[{"run_utc":stamp(2),"feeds_checked":15,
                      "feeds_connected":1,"scan_state":"critical"}],
             "source_health":{"Failed feed":{"consecutive_failures":3,
                               "last_success_utc":None,"last_error_type":"OSError"}}}
        discovery={"gal_runs":[{"run_utc":stamp(2),"status":"ok"}]}
        result=create(rss,discovery,now=NOW)
        self.assertEqual(result["official_successful_scans"],0)
        self.assertIsNone(result["latest_official_scan_utc"])
        self.assertEqual(result["failing_sources"][0]["consecutive_failures"],3)
        self.assertEqual(result["status"],"degraded")

    def test_complete_seven_day_pilot_is_reachable(self):
        rss={"runs":[{"run_utc":(NOW-timedelta(hours=12*i)).isoformat(),
                      "feeds_checked":15,"feeds_connected":15,"scan_state":"healthy"}
                     for i in range(15)]}
        gal={"gal_runs":[{"run_utc":(NOW-timedelta(minutes=10*i)).isoformat(),"status":"ok"}
                         for i in range(1010)]}
        r=create(rss,gal,now=NOW)
        self.assertGreaterEqual(r["history_span_days"],7)
        self.assertEqual(r["observed_sampling_gaps"],[])
        self.assertEqual(r["seven_day_start_gap_minutes"],0)
        self.assertEqual(r["latest_gal_age_minutes"],0)
        self.assertTrue(r["seven_day_pilot_complete"])

    def test_start_of_seven_day_sampling_window_cannot_be_unobserved(self):
        rss={"runs":[{"run_utc":(NOW-timedelta(hours=12*i)).isoformat(),
                      "feeds_checked":15,"feeds_connected":15,"scan_state":"healthy"}
                     for i in range(15)]}
        gal={"gal_runs":[{"run_utc":(NOW-timedelta(minutes=10*i)).isoformat(),"status":"ok"}
                         for i in range(900)]}
        r=create(rss,gal,now=NOW)
        self.assertGreater(r["seven_day_start_gap_minutes"],15)
        self.assertFalse(r["seven_day_pilot_complete"])

    def test_transient_retry_successes_are_measured_separately_from_outages(self):
        rss={"runs":[
            {"run_utc":stamp(55),"feeds_connected":14,"feeds_checked":15,
             "scan_state":"degraded","transient_retries":2,
             "feeds_recovered_after_retry":0},
            {"run_utc":stamp(5),"feeds_connected":15,"feeds_checked":15,
             "scan_state":"healthy","transient_retries":2,
             "feeds_recovered_after_retry":1},
        ],"source_health":{"PJM Inside Lines":{
            "last_recovered_after_retry":True,
            "last_request_attempts":3,
            "last_transient_retry_count":2,
            "total_recoveries":1,"consecutive_failures":0,
            "last_success_utc":stamp(5)}}}
        report=create(rss,{"gal_runs":[{"run_utc":stamp(4),"status":"ok"}]},now=NOW)
        self.assertEqual(report["rss_transient_retries_8d"],4)
        self.assertEqual(report["rss_recovered_sources_8d"],1)
        self.assertEqual(report["latest_rss_recovered_sources"][0]["source"],"PJM Inside Lines")
        self.assertEqual(report["official_fully_connected_scans"],1)
        self.assertEqual(report["failing_sources"],[])

    def test_connected_feed_can_be_dormant_not_broken(self):
        rss={"runs":[{"run_utc":stamp(3),"feeds_connected":2,"feeds_checked":2,
                      "scan_state":"healthy"}],
             "source_health":{
                 "Old testimony":{"newest_feed_published_utc":(NOW-timedelta(days=365)).isoformat(),
                                  "last_success_utc":stamp(3),"consecutive_failures":0},
                 "Active LNG RSS":{"newest_feed_published_utc":stamp(60),
                                   "last_success_utc":stamp(3),"consecutive_failures":0},
             }}
        r=create(rss,{"gal_runs":[{"run_utc":stamp(2),"status":"ok"}]},now=NOW)
        self.assertEqual(r["official_fully_connected_scans"],1)
        self.assertEqual(r["feed_publication_activity_counts"]["publication_within_7d"],1)
        self.assertEqual(r["feed_publication_activity_counts"]["no_publication_in_7d"],1)
        self.assertEqual(r["failing_sources"],[])

    def test_repeated_gal_payload_is_visible_without_being_falsely_called_outage(self):
        r=create({},{"gal_runs":[
            {"run_utc":stamp(20),"status":"ok","feed_payload_sha256":"same-a"},
            {"run_utc":stamp(10),"status":"ok","feed_payload_sha256":"same-a"},
            {"run_utc":stamp(2),"status":"ok","feed_payload_sha256":"new-b"}]},now=NOW)
        self.assertEqual(r["gal_repeated_feed_payloads"],1)
        self.assertEqual(len(r["observed_sampling_gaps"]),0)

    def test_metrics_do_not_credit_duplicate_snapshots_as_extra_windows(self):
        discovery={"gal_runs":[
            {"run_utc":stamp(30),"status":"ok","feed_payload_sha256":"a"},
            {"run_utc":stamp(20),"status":"ok","feed_payload_sha256":"a"},
            {"run_utc":stamp(10),"status":"ok","feed_payload_sha256":"b"}]}
        r=create({},discovery,now=NOW)
        self.assertEqual(r["gal_sampled_window_24h"]
                         ["repeated_identical_payload_samples_not_credited"],1)
        self.assertEqual(r["gal_sampled_window_24h"]
                         ["potentially_sampled_minutes_upper_bound"],30)
        self.assertTrue(any("received no additional" in w for w in r["warnings"]))

    def test_metrics_identify_historical_large_gap_magnitude(self):
        rss={"runs":[{"run_utc":stamp(2),"feeds_checked":15,
                      "feeds_connected":15,"scan_state":"healthy"}]}
        gal={"gal_runs":[{"run_utc":stamp(24*60-15),"status":"ok"},
                         {"run_utc":stamp(2),"status":"ok"}]}
        r=create(rss,gal,now=NOW)
        self.assertLess(r["gal_sampled_window_24h"]["potential_coverage_upper_bound_pct"],5)
        self.assertGreater(r["gal_sampled_window_24h"]["unobserved_minutes_at_least"],1300)
        self.assertFalse(r["seven_day_pilot_complete"])
        self.assertTrue(any("sampled-window" in warning for warning in r["warnings"]))

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
