"""Per-source poll health must not be confused with publisher posting frequency."""
import unittest
from datetime import datetime, timedelta, timezone
from ops_metrics import create

NOW = datetime(2026, 11, 20, 14, 0, tzinfo=timezone.utc)

class IndividualSourcePollHealthTests(unittest.TestCase):
    def test_stale_and_missing_poll_are_visible_even_with_recent_publications(self):
        recent_article = (NOW - timedelta(hours=1)).isoformat()
        rss = {"articles": [], "runs": [], "source_health": {
            "active": {"newest_feed_published_utc": recent_article,
                       "last_success_utc": (NOW-timedelta(hours=2)).isoformat()},
            "stale": {"newest_feed_published_utc": recent_article,
                      "last_success_utc": (NOW-timedelta(hours=25)).isoformat()},
            "never": {"newest_feed_published_utc": recent_article},
            "future": {"newest_feed_published_utc": recent_article,
                       "last_success_utc": (NOW+timedelta(hours=2)).isoformat()},
        }}
        result = create(rss, {}, now=NOW)
        rows = {r["source"]: r for r in result["feed_publication_activity"]}
        self.assertEqual(rows["active"]["poll_status"], "recent_successful_poll")
        self.assertEqual(rows["stale"]["poll_status"], "stale_successful_poll")
        self.assertEqual(rows["never"]["poll_status"], "never_successfully_polled")
        self.assertEqual(rows["future"]["poll_status"], "future_scan_timestamp")
        self.assertEqual(set(result["stale_source_polls"]), {"stale", "never", "future"})
        self.assertTrue(any("individual RSS sources" in w for w in result["warnings"]))
        self.assertTrue(all(r["activity"] == "publication_within_7d" for r in rows.values()))

    def test_old_publisher_content_does_not_mean_poll_failure(self):
        rss = {"articles": [], "runs": [], "source_health": {
            "infrequent agency": {
                "newest_feed_published_utc": (NOW-timedelta(days=40)).isoformat(),
                "last_success_utc": (NOW-timedelta(minutes=30)).isoformat()
            }
        }}
        result = create(rss, {}, now=NOW)
        row = result["feed_publication_activity"][0]
        self.assertEqual(row["activity"], "no_publication_in_7d")
        self.assertEqual(row["poll_status"], "recent_successful_poll")
        self.assertEqual(result["stale_source_polls"], [])

if __name__ == "__main__":
    unittest.main()
