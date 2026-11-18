"""Offline regression checks; no live network or commercial publisher access."""
import json
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from collector import collect, parse_feed, published_date
from xml.etree import ElementTree as ET

NOW = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)

def sample(title="LNG terminal expansion approved", when="Wed, 18 Nov 2026 10:00:00 GMT", url="https://example.gov/energy?utm_source=test"):
    return (f"<rss version='2.0'><channel><item><title>{title}</title><link>{url}</link>"
            f"<pubDate>{when}</pubDate><guid>unique-guid-1</guid>"
            "<description>Natural gas LNG market project</description></item></channel></rss>").encode()

class CollectorTests(unittest.TestCase):
    def test_rss_dates_links(self):
        items, rejected, seen = parse_feed(sample(), "Official", NOW, 48)
        self.assertEqual((len(items), seen), (1, 1))
        self.assertEqual(items[0]["url"], "https://example.gov/energy")
        self.assertEqual(items[0]["category"], "Natural Gas & LNG")
        self.assertEqual(rejected["undated"], 0)

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

    def test_state_persists_without_duplication(self):
        with tempfile.TemporaryDirectory() as d:
            state = Path(d) / "state.json"
            out = Path(d) / "out"
            fetch = lambda url: (sample(), 200)
            first = collect(state, out, now=NOW, fetcher=fetch)
            self.assertEqual(first["feeds_connected"], 8)
            self.assertEqual(first["relevant_fresh_entries"], 8)
            self.assertEqual(len(json.loads((out/"editorial_candidates.json").read_text())), 8)
            self.assertEqual(first["new_article_links"], 8)  # source identities are independent
            second = collect(state, out, now=NOW + timedelta(hours=1), fetcher=fetch)
            self.assertEqual(second["new_article_links"], 0)
            self.assertEqual(len(json.loads(state.read_text())["articles"]), 8)
            self.assertEqual(len(json.loads(state.read_text())["runs"]), 2)

    def test_failure_is_visible(self):
        with tempfile.TemporaryDirectory() as d:
            def fail(url):
                raise OSError("offline")
            report = collect(Path(d)/"db.json", Path(d)/"out", now=NOW, fetcher=fail)
            self.assertEqual(report["feeds_connected"], 0)
            self.assertEqual(len(report["sources"]), 8)
            self.assertIn("offline", (Path(d)/"out/latest.md").read_text())

    def test_invalid_existing_state_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            state = Path(d)/"db.json"
            state.write_text("{broken")
            with self.assertRaises(ValueError):
                collect(state, Path(d)/"out", now=NOW, fetcher=lambda _: (sample(),200))
            self.assertEqual(state.read_text(), "{broken")

if __name__ == "__main__":
    unittest.main()
