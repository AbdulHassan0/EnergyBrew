"""Regression coverage for independent RSS polling continuity diagnostics."""
import unittest
from datetime import datetime, timezone, timedelta
from ops_metrics import create


class SourcePollContinuityTests(unittest.TestCase):
    def test_distinguishes_quiet_publisher_from_stale_poll(self):
        now=datetime(2026,11,21,12,0,tzinfo=timezone.utc)
        rss={"source_health":{
            "quiet_but_polled":{"last_success_utc":(now-timedelta(hours=1)).isoformat(),
                                "newest_feed_published_utc":(now-timedelta(days=30)).isoformat()},
            "stale":{"last_success_utc":(now-timedelta(hours=13)).isoformat()},
            "never":{},
            "future":{"last_success_utc":(now+timedelta(days=2)).isoformat()}}}
        result=create(rss,{},now=now)
        statuses={x["source"]:x["status"] for x in result["source_poll_health"]}
        self.assertEqual(statuses,{"quiet_but_polled":"recent_success",
                                   "stale":"stale_success","never":"never_successful",
                                   "future":"invalid_future_success"})
        self.assertEqual(result["feed_publication_activity_counts"]["no_publication_in_7d"],1)
        self.assertTrue(any("Individual RSS feed polling" in x for x in result["warnings"]))

    def test_empty_source_health_does_not_invent_failures(self):
        result=create({}, {}, now=datetime(2026,11,21,12,tzinfo=timezone.utc))
        self.assertEqual(result["source_poll_health"],[])
        self.assertEqual(result["source_poll_health_counts"],{})
        self.assertFalse(any("Individual RSS feed polling" in x for x in result["warnings"]))


if __name__=="__main__":
    unittest.main()
