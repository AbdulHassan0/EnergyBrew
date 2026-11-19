"""Time-window union tests: measure long gaps without double-counting overlap."""
import unittest
from datetime import datetime, timedelta, timezone
from coverage_windows import estimate_sampling_coverage

NOW=datetime(2026,11,19,12,0,tzinfo=timezone.utc)


def run(minutes_ago,status="ok"):
    return {"run_utc":(NOW-timedelta(minutes=minutes_ago)).isoformat(),"status":status}


class SamplingWindowTests(unittest.TestCase):
    def test_full_coverage_with_overlapping_ten_minute_samples(self):
        samples=[run(i) for i in range(0,24*60+1,10)]
        r=estimate_sampling_coverage(samples,now=NOW,hours=24)
        self.assertEqual(r["potential_coverage_upper_bound_pct"],100.0)
        self.assertEqual(r["unobserved_minutes_at_least"],0)
        self.assertEqual(r["longest_unobserved_minutes"],0)

    def test_seven_hour_outage_is_reported_in_minutes_not_one_small_gap(self):
        # Each 15-min sample covers at most fifteen minutes. Samples at
        # 23:45h ago and now leave a 23h30m gap.
        r=estimate_sampling_coverage([run(24*60-15),run(0)],now=NOW,hours=24)
        self.assertEqual(r["potentially_sampled_minutes_upper_bound"],30.0)
        self.assertEqual(r["unobserved_minutes_at_least"],1410.0)
        self.assertEqual(r["longest_unobserved_minutes"],1410.0)

    def test_degraded_failed_samples_cannot_cover_gap(self):
        r=estimate_sampling_coverage([run(20),run(10,"degraded"),run(0)],
                                     now=NOW,hours=1)
        self.assertEqual(r["potentially_sampled_minutes_upper_bound"],30.0)
        self.assertEqual(r["unobserved_minutes_at_least"],30.0)

    def test_duplicate_timestamps_do_not_inflate_coverage(self):
        r=estimate_sampling_coverage([run(5),run(5),run(0)],now=NOW,hours=1)
        self.assertEqual(r["potentially_sampled_minutes_upper_bound"],20)
        self.assertEqual(r["unobserved_minutes_at_least"],40)

    def test_identical_cached_feed_does_not_claim_new_time_coverage(self):
        samples=[
            {**run(30), "feed_payload_sha256":"a1"},
            {**run(20), "feed_payload_sha256":"a1"},
            {**run(10), "feed_payload_sha256":"b2"},
            {**run(0), "feed_payload_sha256":"b2"}]
        result=estimate_sampling_coverage(samples,now=NOW,hours=1)
        self.assertEqual(result["potentially_sampled_minutes_upper_bound"],30.0)
        self.assertEqual(result["repeated_identical_payload_samples_not_credited"],2)
        self.assertEqual(result["successfully_timestamped_run_count"],2)

    def test_duplicate_detection_is_order_independent(self):
        samples=[
            {**run(0), "feed_payload_sha256":"x"},
            {**run(20), "feed_payload_sha256":"x"},
            {**run(10), "feed_payload_sha256":"y"}]
        result=estimate_sampling_coverage(samples,now=NOW,hours=1)
        self.assertEqual(result["potentially_sampled_minutes_upper_bound"],30)
        self.assertEqual(result["repeated_identical_payload_samples_not_credited"],1)

    def test_legacy_hashless_history_is_labelled_unknown(self):
        result=estimate_sampling_coverage([run(20),run(10)],now=NOW,hours=1)
        self.assertEqual(result["samples_without_payload_fingerprint"],2)
        self.assertEqual(result["repeated_identical_payload_samples_not_credited"],0)

    def test_only_horizon_intersection_counts(self):
        r=estimate_sampling_coverage([run(100),run(5)],now=NOW,hours=1)
        self.assertEqual(r["potential_coverage_upper_bound_pct"],25.0)

    def test_missing_everything_is_unknown_coverage_not_zero_news(self):
        r=estimate_sampling_coverage([],now=NOW,hours=24)
        self.assertEqual(r["potential_coverage_upper_bound_pct"],0)
        self.assertEqual(r["longest_unobserved_minutes"],1440)
        self.assertIn("not verified publisher coverage",r["warning"])

    def test_rejects_naive_reference_clock(self):
        with self.assertRaises(ValueError):
            estimate_sampling_coverage([],now=datetime(2026,11,19,12),hours=24)

    def test_sorts_unsorted_input_and_ignores_bad_timestamps(self):
        r=estimate_sampling_coverage([run(10),{"status":"ok","run_utc":"bad"},run(0),run(20)],
                                     now=NOW,hours=1)
        self.assertEqual(r["potentially_sampled_minutes_upper_bound"],35.0)


if __name__=="__main__":
    unittest.main()
