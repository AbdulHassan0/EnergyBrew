"""Offline regression checks; no live network or commercial publisher access."""
import json
import hashlib
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from collector import clean_url, collect, parse_feed, published_date, SOURCES, DAY_PRECISION_SOURCES, SPECIALIST_NEWS_SOURCES, SYSTEM_OPERATOR_SOURCES
from editorial import evaluate
from xml.etree import ElementTree as ET

NOW = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)

def sample(title="LNG terminal expansion approved", when="Wed, 18 Nov 2026 10:00:00 GMT", url="https://example.gov/energy?utm_source=test"):
    return (f"<rss version='2.0'><channel><item><title>{title}</title><link>{url}</link>"
            f"<pubDate>{when}</pubDate><guid>unique-guid-1</guid>"
            "<description>Natural gas LNG market project</description></item></channel></rss>").encode()

def fixture_fetch(url):
    unique = hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
    return sample(url=f"https://example.gov/unique-story/{unique}"), 200

class CollectorTests(unittest.TestCase):
    def test_rss_dates_links(self):
        items, rejected, seen = parse_feed(sample(), "Official", NOW, 48)
        self.assertEqual((len(items), seen), (1, 1))
        self.assertEqual(items[0]["url"], "https://example.gov/energy")
        self.assertEqual(items[0]["category"], "Natural Gas & LNG")
        self.assertEqual(rejected["undated"], 0)

    def test_publisher_feed_tier_not_misrepresented_as_agency(self):
        items,_,_ = parse_feed(sample(title="LNG export shipping supply agreement"),"Offshore Energy News",NOW,48)
        self.assertEqual(items[0]["source_class"],"specialist_publisher")
        self.assertIn("Offshore Energy News",SPECIALIST_NEWS_SOURCES)

    def test_pjm_is_original_grid_operator_not_a_government_agency(self):
        items,_,_ = parse_feed(sample(title="PJM power grid reliability updates"),"PJM Inside Lines",NOW,48)
        self.assertIn("PJM Inside Lines", SYSTEM_OPERATOR_SOURCES)
        self.assertEqual(items[0]["source_class"],"system_operator_primary")

    def test_updated_is_not_published(self):
        xml = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Gas LNG</title><link href="https://example.gov/x"/><updated>2026-11-18T10:00:00Z</updated></entry></feed>'
        items, rejected, seen = parse_feed(xml, "Official", NOW, 48)
        self.assertEqual(seen, 1)
        self.assertEqual(len(items), 0)
        self.assertEqual(rejected["undated"], 1)

    def test_rejects_old_future_undated(self):
        for date, label in [("Wed, 01 Jan 2020 10:00:00 GMT", "old"), ("Wed, 25 Nov 2026 10:00:00 GMT", "future"), ("", "undated")]:
            items, rejected, _ = parse_feed(sample(when=date), "Official", NOW, 48)
            self.assertFalse(items)
            self.assertEqual(rejected[label], 1)

    def test_public_history_has_no_publisher_excerpt(self):
        with tempfile.TemporaryDirectory() as d:
            state=Path(d)/"state.json"
            collect(state,Path(d)/"out",now=NOW,fetcher=fixture_fetch)
            saved=json.loads(state.read_text())
            self.assertTrue(saved["articles"])
            self.assertTrue(all("summary_excerpt" not in x for x in saved["articles"]))

    def test_sensitive_link_query_and_credentials(self):
        self.assertFalse(clean_url("https://user:secret@example.com/story"))
        self.assertEqual(clean_url("https://example.com/story?utm_source=site&token=secret&id=5"),"https://example.com/story?id=5")

    def test_state_persists_without_duplication(self):
        with tempfile.TemporaryDirectory() as d:
            state = Path(d) / "state.json"
            out = Path(d) / "out"
            fetch = fixture_fetch
            first = collect(state, out, now=NOW, fetcher=fetch)
            self.assertEqual(first["feeds_connected"], len(SOURCES))
            self.assertEqual(first["relevant_fresh_entries"], len(SOURCES)-len(DAY_PRECISION_SOURCES))
            self.assertEqual(len(json.loads((out/"editorial_candidates.json").read_text())), len(SOURCES)-len(DAY_PRECISION_SOURCES))
            self.assertEqual(first["new_article_links"], len(SOURCES))  # source identities are independent
            second = collect(state, out, now=NOW + timedelta(hours=1), fetcher=fetch)
            self.assertEqual(second["new_article_links"], 0)
            self.assertEqual(len(json.loads(state.read_text())["articles"]), len(SOURCES))
            self.assertEqual(len(json.loads(state.read_text())["runs"]), 2)

    def test_relevance_requires_sector_context(self):
        self.assertTrue(evaluate("LNG export terminal expansion approved")["editorial_candidate"])
        self.assertTrue(evaluate("PJM seeks faster connections for data center power demand")["editorial_candidate"])
        self.assertFalse(evaluate("Company announces a new project and commission approval")["editorial_candidate"])
        self.assertFalse(evaluate("Spoiled ingredients and boiler maintenance project")["editorial_candidate"])

    def test_named_energy_developments_do_not_disappear(self):
        self.assertTrue(evaluate("Venture Global signs LNG supply agreement with buyer")["editorial_candidate"])
        self.assertTrue(evaluate("Chevron nears major Beacon Offshore acquisition")["editorial_candidate"])
        self.assertTrue(evaluate("Cheniere approves new Corpus Christi expansion")["editorial_candidate"])
        self.assertTrue(evaluate("Calpine advances power generation project")["editorial_candidate"])
        self.assertFalse(evaluate("City approves new hotel and restaurant")["editorial_candidate"])

    def test_date_only_regulatory_leads_are_not_fresh_editorial_headlines(self):
        items, rejected, seen = parse_feed(sample(), "Federal Register FERC notices", NOW, 48, date_precision="day")
        self.assertEqual(seen, 1)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["published_precision"], "day")
        self.assertEqual(items[0]["status"], "research_date_only")
        self.assertFalse(items[0]["editorial_candidate"])

    def test_daily_volume_separates_regulatory_notices(self):
        with tempfile.TemporaryDirectory() as d:
            state, out = Path(d)/"state.json", Path(d)/"out"
            report = collect(state, out, now=NOW, fetcher=fixture_fetch)
            volumes = json.loads((out/"volume_7d.json").read_text())
            self.assertEqual(report["relevant_fresh_entries"], len(SOURCES)-len(DAY_PRECISION_SOURCES))
            self.assertEqual(report["date_only_entries"], 1)
            self.assertEqual(report["editorial_candidates_24h"], len(SOURCES)-len(DAY_PRECISION_SOURCES))
            self.assertEqual(len(json.loads((out/"editorial_candidates_24h.json").read_text())), len(SOURCES)-len(DAY_PRECISION_SOURCES))
            self.assertEqual(volumes["days"][0]["editorial_candidates"], len(SOURCES)-len(DAY_PRECISION_SOURCES))
            self.assertEqual(volumes["days"][0]["regulatory_date_only_leads"], 1)
            self.assertEqual(len(json.loads((out/"editorial_candidates.json").read_text())), len(SOURCES)-len(DAY_PRECISION_SOURCES))

    def test_old_federal_register_duplication_is_folded_by_url(self):
        with tempfile.TemporaryDirectory() as d:
            state, out = Path(d)/"state.json", Path(d)/"out"
            old_a = parse_feed(sample(url="https://example.gov/fed-notice"), "Federal Register FERC notices", NOW, 48, date_precision="day")[0][0]
            old_b = parse_feed(sample(url="https://example.gov/fed-notice"), "Federal Register DOE notices", NOW, 48, date_precision="day")[0][0]
            state.write_text(json.dumps({"articles":[old_a,old_b],"runs":[]}))
            report=collect(state,out,now=NOW,fetcher=fixture_fetch)
            data=json.loads(state.read_text())["articles"]
            duplicated=[x for x in data if x["url"]=="https://example.gov/fed-notice"]
            self.assertEqual(len(duplicated),1)
            self.assertEqual(duplicated[0]["source"],"Federal Register notices")
            self.assertFalse(duplicated[0]["editorial_candidate"])
            self.assertEqual(report["distinct_article_links_7d"],len(SOURCES)+1)

    def test_failure_is_visible(self):
        with tempfile.TemporaryDirectory() as d:
            def fail(url):
                raise OSError("offline")
            report = collect(Path(d)/"db.json", Path(d)/"out", now=NOW, fetcher=fail)
            self.assertEqual(report["feeds_connected"], 0)
            self.assertEqual(len(report["sources"]), len(SOURCES))
            self.assertIn("offline", (Path(d)/"out/latest.md").read_text())

    def test_invalid_schema_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            state=Path(d)/"db.json"
            state.write_text(json.dumps(["bad-state"]))
            with self.assertRaises(ValueError):
                collect(state,Path(d)/"out",now=NOW,fetcher=fixture_fetch)

    def test_http_503_rss_body_is_not_a_successful_connection(self):
        with tempfile.TemporaryDirectory() as d:
            r=collect(Path(d)/"db.json",Path(d)/"out",now=NOW,
                      fetcher=lambda url:(sample(),503))
            self.assertEqual(r["scan_state"],"critical")
            self.assertEqual(r["feeds_connected"],0)

    def test_single_connected_feed_fails_minimum_quorum(self):
        with tempfile.TemporaryDirectory() as d:
            state=Path(d)/"db.json"
            def one(url):
                if url==SOURCES[0][1]:
                    return sample(),200
                raise OSError("offline")
            r=collect(state,Path(d)/"out",now=NOW,fetcher=one)
            self.assertEqual(r["feeds_connected"],1)
            self.assertEqual(r["scan_state"],"critical")
            second=collect(state,Path(d)/"out",now=NOW+timedelta(hours=1),fetcher=one)
            self.assertEqual(second["scan_state"],"critical")
            history=json.loads(state.read_text())
            self.assertEqual(history["source_health"][SOURCES[1][0]]["consecutive_failures"],2)
            self.assertEqual(history["source_health"][SOURCES[0][0]]["consecutive_successes"],2)

    def test_zero_new_headlines_is_success_if_feeds_parse(self):
        with tempfile.TemporaryDirectory() as d:
            state=Path(d)/"db.json"
            r=collect(state,Path(d)/"out",now=NOW,fetcher=fixture_fetch)
            self.assertEqual(r["scan_state"],"healthy")
            second=collect(state,Path(d)/"out",now=NOW+timedelta(hours=1),fetcher=fixture_fetch)
            self.assertEqual(second["new_article_links"],0)
            self.assertEqual(second["scan_state"],"healthy")

    def test_invalid_existing_state_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            state = Path(d)/"db.json"
            state.write_text("{broken")
            with self.assertRaises(ValueError):
                collect(state, Path(d)/"out", now=NOW, fetcher=lambda _: (sample(),200))
            self.assertEqual(state.read_text(), "{broken")

if __name__ == "__main__":
    unittest.main()
