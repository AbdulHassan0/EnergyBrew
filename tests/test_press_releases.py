"""Contract tests for commercial-energy issuer announcements; all research-only."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from press_releases import collect, parse_releases

NOW=datetime(2026,11,18,16,0,tzinfo=timezone.utc)


def feed(title="Cheniere Energy announces LNG expansion financing",
         src="https://www.example.com/company/lng-expansion",
         when="Wed, 18 Nov 2026 15:00:00 GMT"):
    return (f'<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/"><channel>'
            f'<title>Energy press release</title><item>'
            f'<title>{title}</title><link>https://pressreleasefeed.org/releases/example</link>'
            f'<source url="{src}">Company news</source>'
            f'<dc:creator>Cheniere Energy</dc:creator>'
            f'<pubDate>{when}</pubDate><guid>example-guid</guid>'
            f'</item></channel></rss>').encode()


class PressReleaseTests(unittest.TestCase):
    def test_original_source_url_only(self):
        records,skips,count=parse_releases(feed(),NOW)
        self.assertEqual(count,1)
        self.assertEqual(len(records),1)
        row=records[0]
        self.assertEqual(row["url"],"https://www.example.com/company/lng-expansion")
        self.assertEqual(row["issuer"],"Cheniere Energy")
        self.assertIsNone(row["publisher_published_utc"])
        self.assertFalse(row["published_time_verified"])
        self.assertEqual(row["content_kind"],"company_or_newswire_press_release")

    def test_missing_original_source_link_excluded(self):
        records,skips,count=parse_releases(feed(src="not-a-url"),NOW)
        self.assertEqual(records,[])
        self.assertEqual(skips["missing_original_source_url"],1)

    def test_reject_expired_and_nonenergy_releases(self):
        for kwargs,kind in [
            ({"when":"Wed, 01 Jan 2020 15:00:00 GMT"},"outside_window"),
            ({"title":"Restaurant announces new breakfast menu"},"off_topic")
        ]:
            records,skips,count=parse_releases(feed(**kwargs),NOW)
            self.assertFalse(records)
            self.assertEqual(skips[kind],1)

    def test_no_tag_pages_even_when_energy_related(self):
        records,skips,count=parse_releases(feed(
            title="Tag: LNG",src="https://www.example.com/tag/lng"),NOW)
        self.assertFalse(records)
        self.assertEqual(skips["non_article"],1)

    def test_history_preserved_and_duplicate_removed(self):
        with tempfile.TemporaryDirectory() as d:
            state,out=Path(d)/"releases.json",Path(d)/"out"
            first=collect(state,out,now=NOW,fetcher=lambda u:(feed(),200))
            second=collect(state,out,now=NOW+timedelta(hours=1),fetcher=lambda u:(feed(),200))
            self.assertEqual(first["status"],"ok")
            self.assertEqual(first["new_unique_links"],1)
            self.assertEqual(second["new_unique_links"],0)
            self.assertEqual(len(json.loads(state.read_text())["leads"]),1)
            self.assertEqual(len(json.loads(state.read_text())["runs"]),2)

    def test_failure_does_not_erase_saved_links(self):
        with tempfile.TemporaryDirectory() as d:
            state,out=Path(d)/"releases.json",Path(d)/"out"
            collect(state,out,now=NOW,fetcher=lambda u:(feed(),200))
            def fail(url):
                raise OSError("Provider offline")
            r=collect(state,out,now=NOW+timedelta(hours=1),fetcher=fail)
            self.assertEqual(r["status"],"degraded")
            self.assertEqual(len(json.loads(state.read_text())["leads"]),1)
            self.assertIn("Provider offline",r["error"])

    def test_invalid_prior_state_not_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            state=Path(d)/"releases.json"
            state.write_text("not-json")
            with self.assertRaises(ValueError):
                collect(state,Path(d)/"out",now=NOW,fetcher=lambda u:(feed(),200))
            self.assertEqual(state.read_text(),"not-json")


if __name__=="__main__":
    unittest.main()
