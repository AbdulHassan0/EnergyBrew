"""Offline tests for GAL RSS sample fallback and its provenance guarantees."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from gal import parse_gal, collect_gal

NOW=datetime(2026,11,18,15,0,tzinfo=timezone.utc)

def feed(title="Cheniere LNG expansion advances",
         date="Wed, 18 Nov 2026 14:00:00 GMT",
         url="https://example.com/new-lng-project?utm_source=gal"):
    return (f'<rss version="2.0"><channel><title>GAL</title><item>'
            f'<title>{title}</title><link>{url}</link>'
            f'<pubDate>{date}</pubDate><guid>example-1</guid>'
            f'</item></channel></rss>').encode()

class GalTests(unittest.TestCase):
    def test_public_rss_is_research_only(self):
        items,rejected,seen=parse_gal(feed(),NOW)
        self.assertEqual((len(items),seen),(1,1))
        lead=items[0]
        self.assertEqual(lead["url"],"https://example.com/new-lng-project")
        self.assertFalse(lead["published_time_verified"])
        self.assertIsNone(lead["publisher_published_utc"])
        self.assertEqual(lead["index_timestamp_source"],"GAL RSS pubDate (not publisher publication date)")

    def test_off_topic_and_old_items_excluded(self):
        for kwargs,key in [
            ({"title":"How to decorate a birthday cake"},"off_topic"),
            ({"date":"Wed, 01 Jan 2020 12:00:00 GMT"},"stale_index_time"),
            ({"date":""},"missing_index_time"),
        ]:
            items,rejected,seen=parse_gal(feed(**kwargs),NOW)
            self.assertFalse(items)
            self.assertEqual(rejected[key],1)

    def test_malformed_document_fails_not_silent(self):
        with self.assertRaises(Exception):
            parse_gal(b"<rss",NOW)

    def test_repeat_does_not_double_count(self):
        with tempfile.TemporaryDirectory() as d:
            state, out=Path(d)/"discovery.json",Path(d)/"out"
            fake=lambda url:(feed(),200)
            first=collect_gal(state,out,now=NOW,fetcher=fake)
            self.assertEqual(first["status"],"ok")
            self.assertEqual(first["new_unique_links"],1)
            second=collect_gal(state,out,now=NOW+timedelta(minutes=5),fetcher=fake)
            self.assertEqual(second["new_unique_links"],0)
            saved=json.loads(state.read_text())
            self.assertEqual(len(saved["leads"]),1)
            self.assertEqual(len(saved["gal_runs"]),2)

    def test_cross_provider_merge_preserves_other_topic(self):
        with tempfile.TemporaryDirectory() as d:
            state, out=Path(d)/"discovery.json",Path(d)/"out"
            state.write_text(json.dumps({"leads":[{
                "url":"https://example.com/new-lng-project",
                "title":"Cheniere LNG expansion advances",
                "gdelt_first_seen_utc":NOW.isoformat(),
                "discovery_provider":"GDELT DOC 2.0",
                "topics":["lng_exports"],
                "relevance_score":20,
                "published_time_verified":False
            }], "topics":{},"runs":[]}))
            r=collect_gal(state,out,now=NOW,fetcher=lambda url:(feed(),200))
            self.assertEqual(r["new_unique_links"],0)
            item=json.loads(state.read_text())["leads"][0]
            self.assertIn("GDELT GAL RSS",item["discovery_providers"])
            self.assertIn("GDELT DOC 2.0",item["discovery_providers"])
            self.assertIn("lng_exports",item["topics"])
            self.assertIn("gal_rolling_sample",item["topics"])
            self.assertFalse(item["published_time_verified"])

    def test_network_failure_recorded_without_state_loss(self):
        with tempfile.TemporaryDirectory() as d:
            state,out=Path(d)/"discovery.json",Path(d)/"out"
            first=collect_gal(state,out,now=NOW,fetcher=lambda url:(feed(),200))
            def fail(url):
                raise OSError("GAL offline")
            later=collect_gal(state,out,now=NOW+timedelta(hours=1),fetcher=fail)
            self.assertEqual(later["status"],"degraded")
            self.assertIn("GAL offline",later["error"])
            self.assertEqual(len(json.loads(state.read_text())["leads"]),1)
            self.assertTrue((out/"latest.md").exists())

    def test_rejects_bad_state_instead_of_wiping(self):
        with tempfile.TemporaryDirectory() as d:
            state=Path(d)/"discovery.json"
            state.write_text("broken")
            with self.assertRaises(ValueError):
                collect_gal(state,Path(d)/"out",now=NOW,fetcher=lambda u:(feed(),200))
            self.assertEqual(state.read_text(),"broken")

if __name__=="__main__":
    unittest.main()
