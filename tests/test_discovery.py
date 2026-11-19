"""Regression tests for independent GDELT news-discovery worker."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError

from discovery import (
    TOPICS, api_url, normalize_results, parse_first_seen,
    retry_after_seconds, escalation_cooldown_seconds, run_discovery,
)

NOW = datetime(2026, 11, 18, 14, 0, tzinfo=timezone.utc)


def sample(url="https://news.example.com/lng?utm_source=feed",
           title="LNG export terminal announces pipeline expansion",
           seen="20261118T130000Z"):
    return {"articles": [{
        "url": url, "title": title, "seendate": seen,
        "domain": "news.example.com", "language": "English",
    }]}


class DiscoveryTests(unittest.TestCase):
    def test_first_seen_formats_and_no_naive_timezone(self):
        self.assertEqual(parse_first_seen("20261118T130000Z"), NOW - timedelta(hours=1))
        self.assertEqual(parse_first_seen("20261118130000"), NOW - timedelta(hours=1))
        self.assertIsNone(parse_first_seen("2026-11-18 13:00:00"))
        self.assertIsNone(parse_first_seen("not-a-date"))

    def test_source_time_not_fabricated(self):
        results, errors, seen = normalize_results(sample(), "lng_exports", NOW)
        self.assertEqual((seen, len(results)), (1, 1))
        lead = results[0]
        self.assertFalse(lead["published_time_verified"])
        self.assertIsNone(lead["publisher_published_utc"])
        self.assertEqual(lead["gdelt_first_seen_utc"], "2026-11-18T13:00:00+00:00")
        self.assertEqual(lead["status"], "discovery_only_requires_publisher_verification")
        self.assertEqual(lead["url"], "https://news.example.com/lng")

    def test_reject_future_stale_and_missing_timestamps(self):
        for seen, field in [
            ("20261120T130000Z", "outside_window"),
            ("20261010T130000Z", "outside_window"),
            ("", "invalid_first_seen"),
        ]:
            items, errors, count = normalize_results(sample(seen=seen), "gas", NOW)
            self.assertEqual(count, 1)
            self.assertEqual(len(items), 0)
            self.assertEqual(errors[field], 1)

    def test_non_json_not_mistaken_for_empty_results(self):
        with self.assertRaises(ValueError):
            normalize_results(b"<html>Blocked</html>", "lng", NOW)
        with self.assertRaises(ValueError):
            normalize_results({"articles": "bad"}, "lng", NOW)

    def test_normalization_does_not_follow_article_links(self):
        items, _, _ = normalize_results(sample(), "lng", NOW)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["domain"], "news.example.com")
        self.assertNotIn("content", items[0])

    def test_topic_rotation_survives_restarts(self):
        with tempfile.TemporaryDirectory() as d:
            state, out = Path(d)/"state.json", Path(d)/"out"
            calls = []
            def fake(url):
                calls.append(url)
                return json.dumps(sample()).encode(), 200
            first = run_discovery(state, out, now=NOW, fetcher=fake, max_queries=4)
            self.assertEqual(first["topics_attempted"], 4)
            self.assertEqual(first["topics_succeeded"], 4)
            self.assertEqual(first["new_discovered_urls"], 1)
            self.assertEqual(len(json.loads(state.read_text())["leads"]), 1)
            self.assertEqual(len(json.loads((out/"leads_24h.json").read_text())), 1)
            again = run_discovery(state, out, now=NOW+timedelta(hours=1),
                                  fetcher=fake, max_queries=4)
            self.assertEqual(again["topics_attempted"], 4)
            self.assertEqual(again["new_discovered_urls"], 0)
            self.assertEqual(len(json.loads(state.read_text())["topics"]), 8)
            self.assertEqual(len(json.loads(state.read_text())["runs"]), 2)
            self.assertNotEqual(calls[:4], calls[4:8])
            for item in json.loads(state.read_text())["leads"]:
                self.assertFalse(item["published_time_verified"])

    def test_429_stops_subsequent_queries_and_persists_cooldown(self):
        with tempfile.TemporaryDirectory() as d:
            state, out = Path(d)/"state.json", Path(d)/"out"
            calls = []
            def limit(url):
                calls.append(url)
                raise HTTPError(url, 429, "Rate limit", {"Retry-After": "3600"}, None)
            first = run_discovery(state,out,now=NOW,fetcher=limit,max_queries=4)
            self.assertEqual((first["topics_attempted"],first["topics_succeeded"]),(1,0))
            self.assertEqual(first["topic_attempts"][0]["status"],"rate_limited")
            self.assertEqual(len(calls),1)
            second = run_discovery(state,out,now=NOW+timedelta(minutes=10),fetcher=limit,max_queries=4)
            self.assertEqual(second["status"], "provider_cooldown")
            self.assertEqual(second["topics_attempted"], 0)
            self.assertEqual(len(calls),1)
            third = run_discovery(state,out,now=NOW+timedelta(hours=2),fetcher=limit,max_queries=4)
            self.assertEqual(third["topics_attempted"],1)
            self.assertEqual(len(calls),2)

    def test_backoff_increases_after_repeated_provider_rate_limits(self):
        with tempfile.TemporaryDirectory() as d:
            state,out=Path(d)/"state.json",Path(d)/"out"
            attempts=[]
            def limit(url):
                attempts.append(url)
                raise HTTPError(url,429,"Rate limit",{},None)
            first=run_discovery(state,out,now=NOW,fetcher=limit,max_queries=4)
            self.assertEqual(first["provider_throttle_streak"],1)
            self.assertEqual(first["topic_attempts"][0]["backoff_seconds"],5400)
            self.assertEqual(len(attempts),1)
            second=run_discovery(state,out,now=NOW+timedelta(hours=2),
                                 fetcher=limit,max_queries=4)
            self.assertEqual(second["provider_throttle_streak"],2)
            self.assertEqual(second["topic_attempts"][0]["backoff_seconds"],10800)
            blocked=run_discovery(state,out,now=NOW+timedelta(hours=4),
                                  fetcher=limit,max_queries=4)
            self.assertEqual(blocked["status"],"provider_cooldown")
            self.assertEqual(len(attempts),2)
            third=run_discovery(state,out,now=NOW+timedelta(hours=6),
                                fetcher=limit,max_queries=4)
            self.assertEqual(third["provider_throttle_streak"],3)
            self.assertEqual(third["topic_attempts"][0]["backoff_seconds"],21600)
            self.assertEqual(len(attempts),3)

    def test_gdelt_success_resets_throttle_streak(self):
        with tempfile.TemporaryDirectory() as d:
            state,out=Path(d)/"state.json",Path(d)/"out"
            def limit(url):
                raise HTTPError(url,429,"Rate limit",{},None)
            run_discovery(state,out,now=NOW,fetcher=limit,max_queries=1)
            def good(url):
                return json.dumps(sample(seen="20261118T130000Z")).encode(),200
            success=run_discovery(state,out,now=NOW+timedelta(hours=2),
                                  fetcher=good,max_queries=1)
            self.assertEqual(success["topics_succeeded"],1)
            self.assertEqual(success["provider_throttle_streak"],0)
            self.assertIsNone(success["provider_cooldown_until_utc"])
            limited=run_discovery(state,out,now=NOW+timedelta(hours=3),
                                  fetcher=limit,max_queries=1)
            self.assertEqual(limited["topic_attempts"][0]["backoff_seconds"],5400)

    def test_explicit_retry_after_can_override_exponential(self):
        self.assertEqual(escalation_cooldown_seconds({"Retry-After":"14400"},NOW,1),14400)
        self.assertEqual(escalation_cooldown_seconds({},NOW,2),10800)
        self.assertEqual(escalation_cooldown_seconds({},NOW,10),43200)

    def test_retry_after_clamps_extremes(self):
        self.assertEqual(retry_after_seconds({"Retry-After":"1"},NOW),1800)
        self.assertEqual(retry_after_seconds({"Retry-After":"999999999999999999"},NOW),86400)
        self.assertEqual(retry_after_seconds({"Retry-After":"bad"},NOW),5400)

    def test_failed_queries_are_not_misreported_as_completed(self):
        with tempfile.TemporaryDirectory() as d:
            state, out = Path(d)/"state.json", Path(d)/"out"
            def fail(url):
                raise OSError("Network unavailable")
            r=run_discovery(state,out,now=NOW,fetcher=fail,max_queries=3)
            self.assertEqual(r["status"], "degraded")
            self.assertEqual(r["topics_succeeded"], 0)
            self.assertEqual(r["new_discovered_urls"], 0)
            self.assertEqual(len(json.loads(state.read_text())["topics"]),3)
            self.assertIn("Network unavailable",(out/"latest.md").read_text())

    def test_corrupt_state_refuses_to_discard_history(self):
        with tempfile.TemporaryDirectory() as d:
            state = Path(d)/"state.json"
            state.write_text("bad data")
            with self.assertRaises(ValueError):
                run_discovery(state,Path(d)/"out",now=NOW,fetcher=lambda url:(b'{}',200))
            self.assertEqual(state.read_text(),"bad data")

    def test_worldwide_geopolitical_energy_discovery_has_three_topics(self):
        geo=[(n,q) for n,q in TOPICS if n.startswith("geo_energy_")]
        self.assertEqual(len(geo),3)
        self.assertTrue(all(any(v in q.lower() for v in
            ("oil","lng","energy","tanker","pipeline","hormuz","refinery"))
            for _,q in geo))

    def test_query_budget_enforced(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                run_discovery(Path(d)/"s",Path(d)/"o",now=NOW,
                              max_queries=len(TOPICS)+1)

    def test_query_encoded_with_public_api_parameters(self):
        url=api_url('("LNG cargo" OR "LNG export")')
        self.assertIn("gdeltproject.org/api/v2/doc/doc",url)
        self.assertIn("maxrecords=75",url)
        self.assertIn("timespan=36h",url)
        self.assertIn("format=json",url)


if __name__=="__main__":
    unittest.main()
