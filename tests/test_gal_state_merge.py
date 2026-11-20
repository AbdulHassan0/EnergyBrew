"""GAL branch race regression: independent HTTP polling then serialized merge."""
import copy
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json

from gal_state_merge import merge, main

NOW = datetime(2026, 11, 20, 18, 0, tzinfo=timezone.utc)


def when(minutes):
    return (NOW + timedelta(minutes=minutes)).isoformat()


def lead(url, first, *, title="Cheniere LNG export expansion approved", topics=None):
    return {
        "url": url, "title": title,
        "gdelt_first_seen_utc": when(-20),
        "first_collector_observed_utc": when(first),
        "discovery_provider": "GDELT GAL RSS",
        "topics": topics or ["gal_rolling_sample"],
        "published_time_verified": False,
    }


def run(minutes, payload):
    return {"run_utc": when(minutes), "completed_utc": when(minutes + 1),
            "status": "ok", "feed_payload_sha256": payload}


class GalStateMergeTests(unittest.TestCase):
    def test_independently_fetched_samples_not_lost_when_writers_queue(self):
        base = {"leads": [lead("https://site.test/existing", -60)],
                "gal_runs": [run(-60, "base")], "runs": [{"status": "ok"}],
                "provider_throttle_streak": 4,
                "provider_cooldown_until_utc": when(90)}
        # The first sampler was taken before another job's source history commit.
        early = {"leads": [lead("https://site.test/a", -8)],
                 "gal_runs": [run(-8, "early")],
                 "provider_throttle_streak": 1}
        late = {"leads": [lead("https://site.test/b", -3)],
                "gal_runs": [run(-3, "late")]}
        merged_early = merge(base, early, now=NOW)
        final = merge(merged_early, late, now=NOW)
        self.assertEqual(len(final["leads"]), 3)
        self.assertEqual(len(final["gal_runs"]), 3)
        self.assertEqual([x["feed_payload_sha256"] for x in final["gal_runs"]],
                         ["base", "early", "late"])
        self.assertEqual(final["provider_throttle_streak"], 4)
        self.assertEqual(final["provider_cooldown_until_utc"], when(90))

    def test_first_local_observation_never_moves_forward(self):
        uri = "https://site.test/important"
        base = {"leads": [lead(uri, -12, topics=["lng_exports"])],
                "gal_runs": [run(-11, "a")]}
        sample = {"leads": [lead(uri, -2, topics=["gal_rolling_sample"])],
                  "gal_runs": [run(-2, "b")]}
        out = merge(base, sample, now=NOW)
        row = out["leads"][0]
        self.assertEqual(row["first_collector_observed_utc"], when(-12))
        self.assertEqual(set(row["topics"]), {"lng_exports", "gal_rolling_sample"})
        self.assertFalse(row["published_time_verified"])

    def test_delayed_old_sample_cannot_delete_more_recent_news_or_run(self):
        base = {"leads": [lead("https://site.test/newer", -2)],
                "gal_runs": [run(-2, "recent")]}
        old_sample = {"leads": [lead("https://site.test/older", -15)],
                      "gal_runs": [run(-15, "older")]}
        result = merge(base, old_sample, now=NOW)
        self.assertEqual(len(result["leads"]), 2)
        self.assertEqual([x["feed_payload_sha256"] for x in result["gal_runs"]],
                         ["older", "recent"])

    def test_repeated_sample_is_idempotent(self):
        base = {"leads": [], "gal_runs": []}
        sampled = {"leads": [lead("https://site.test/a", -10)],
                   "gal_runs": [run(-10, "sample")]}
        once = merge(base, sampled, now=NOW)
        twice = merge(once, sampled, now=NOW)
        self.assertEqual(len(twice["gal_runs"]), 1)
        self.assertEqual(len(twice["leads"]), 1)

    def test_corrupt_or_missing_data_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "list of leads"):
            merge({}, {"leads": []}, now=NOW)
        with self.assertRaisesRegex(ValueError, "missing URL"):
            merge({"leads": []}, {"leads": [{"title": "gas"}]}, now=NOW)
        with self.assertRaisesRegex(ValueError, "timezone"):
            merge({"leads": []}, {"leads": []},
                  now=datetime(2026, 11, 20, 18, 0))

    def test_source_history_not_mutated(self):
        base = {"leads": [lead("https://site.test/a", -20)],
                "gal_runs": [run(-20, "a")]}
        sample = {"leads": [lead("https://site.test/b", -15)],
                  "gal_runs": [run(-15, "b")]}
        original = copy.deepcopy((base, sample))
        merge(base, sample, now=NOW)
        self.assertEqual((base, sample), original)

    def test_cli_rejects_missing_latest_state(self):
        with tempfile.TemporaryDirectory() as d:
            sample = Path(d) / "sample.json"
            sample.write_text(json.dumps({"leads": [], "gal_runs": []}))
            with self.assertRaises(FileNotFoundError):
                main(["--base", str(Path(d)/"missing.json"),
                      "--sample", str(sample),
                      "--output", str(Path(d)/"merged.json")])


if __name__ == "__main__":
    unittest.main()
