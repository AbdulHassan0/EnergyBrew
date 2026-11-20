"""Offline proof that the morning editorial queue cannot leak late news."""
import unittest
from datetime import datetime, timedelta, timezone

from cutoff_desk import cutoff_desk

CUTOFF = datetime(2026, 11, 19, 12, 30, tzinfo=timezone.utc)
NOW = CUTOFF + timedelta(minutes=15)


def rss(title, uri, published, observed=None):
    row = {
        "url": uri, "title": title, "published_utc": published.isoformat(),
        "published_precision": "timestamp", "source": "Energy Source",
        "source_class": "specialist_publisher",
    }
    if observed:
        row["first_collector_observed_utc"] = observed.isoformat()
    return row


class CutoffDeskTests(unittest.TestCase):
    def test_morning_queue_requires_local_pre_cutoff_observation(self):
        original = rss("Henry Hub natural gas storage prices rise",
                       "https://publisher.example/a",
                       CUTOFF - timedelta(minutes=45),
                       CUTOFF - timedelta(minutes=5))
        late_published = rss("WTI crude oil prices rise after OPEC update",
                             "https://publisher.example/b",
                             CUTOFF + timedelta(minutes=1),
                             CUTOFF + timedelta(minutes=3))
        late_collected = rss("Venture Global LNG export agreement signed",
                             "https://publisher.example/c",
                             CUTOFF - timedelta(minutes=20),
                             CUTOFF + timedelta(minutes=1))
        unknown = rss("Cheniere LNG export cargo capacity expansion",
                      "https://publisher.example/d",
                      CUTOFF - timedelta(minutes=20))
        desk = cutoff_desk({"articles": [original,late_published,
                                        late_collected,unknown], "runs": []},
                           {"leads": [], "gal_runs": []},
                           {"leads": []}, now=NOW)
        urls = {x["url"] for x in desk["stories"]}
        self.assertIn(original["url"], urls)
        self.assertNotIn(late_published["url"], urls)
        self.assertNotIn(late_collected["url"], urls)
        self.assertNotIn(unknown["url"], urls)
        excluded = desk["cutoff_provenance"]["excluded_records_by_lane"]["rss"]
        self.assertEqual(excluded["unknown_first_collection_time"], 1)
        self.assertEqual(excluded["first_collected_after_cutoff"], 2)
        self.assertEqual(desk["cutoff_provenance"]["news_cutoff_utc"],
                         CUTOFF.isoformat())
        self.assertEqual(desk["cutoff_provenance"]["readiness_status"],
                         "blocked_collection_readiness")

    def test_prior_cutoff_is_not_same_as_today_cutoff(self):
        yesterday = rss("Henry Hub natural gas storage prices rise",
                        "https://publisher.example/old",
                        CUTOFF - timedelta(hours=26),
                        CUTOFF - timedelta(hours=25))
        desk = cutoff_desk({"articles": [yesterday], "runs": []},
                           {"leads": [], "gal_runs": []},
                           {"leads": []}, now=NOW)
        self.assertEqual(desk["stories"], [])

    def test_early_generation_fails_instead_of_freezing_future_cutoff(self):
        with self.assertRaisesRegex(ValueError, "before 06:30"):
            cutoff_desk({"articles": []}, {"leads": []}, {"leads": []},
                        now=CUTOFF-timedelta(minutes=1))

    def test_missing_source_state_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "Missing or invalid"):
            cutoff_desk({"articles": []}, {}, {"leads": []}, now=NOW)

    def test_does_not_change_input_research_history(self):
        item = rss("Henry Hub natural gas storage prices rise",
                   "https://publisher.example/unchanged",
                   CUTOFF - timedelta(minutes=45),
                   CUTOFF - timedelta(minutes=5))
        state = {"articles": [item], "runs": []}
        cutoff_desk(state, {"leads": [],"gal_runs":[]}, {"leads":[]}, now=NOW)
        self.assertEqual(state["articles"], [item])


if __name__ == "__main__":
    unittest.main()
