"""Public energy-specialist feed probe uses only publisher RSS metadata."""
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from source_probe import measure, write_report

NOW=datetime(2026,11,18,20,0,tzinfo=timezone.utc)
FEED=b"""<rss version="2.0"><channel><item>
<title>New LNG supply agreement increases exports</title>
<link>https://energy.example.com/lng-supply</link>
<pubDate>Wed, 18 Nov 2026 19:00:00 GMT</pubDate>
<description>Publisher text stays in memory</description>
</item></channel></rss>"""


class SourceProbeTests(unittest.TestCase):
    def test_good_feed_measures_real_article_dates(self):
        report=measure([("Publisher","https://energy.example.com/feed")],now=NOW,fetcher=lambda url:(FEED,200))
        self.assertEqual(report["feeds_connected"],1)
        self.assertEqual(report["fresh_links_24h"],1)
        self.assertEqual(report["high_signal_48h"],1)
        self.assertNotIn("summary_excerpt",str(report))

    def test_restricted_feed_is_not_requested_even_with_valid_endpoint(self):
        requested=[]
        def forbidden(url):
            requested.append(url)
            raise AssertionError("Restricted feed must never be fetched")
        report=measure([("LNG Prime","https://lngprime.com/feed/"),
                        ("Energy Storage News","https://www.energy-storage.news/feed/"),
                        ("POWER Magazine","https://www.powermag.com/feed/")],
                       now=NOW,fetcher=forbidden)
        self.assertEqual(report["feeds_connected"],0)
        self.assertEqual(requested,[])
        self.assertTrue(all(x["status"]=="skipped_rights_review" for x in report["sources"]))

    def test_error_is_reported_not_silenced(self):
        def failure(_): raise OSError("connection refused")
        report=measure([("Offline","https://news.example.org/feed")],now=NOW,fetcher=failure)
        self.assertEqual(report["status"],"degraded")
        self.assertIn("connection refused",report["sources"][0]["error"])

    def test_repeated_filing_homepage_urls_are_not_distinct_articles(self):
        feed=b"""<rss><channel>""" + b"".join(
            (f"<item><title>FERC transmission filing number {i}</title>"
             f"<link>https://ferc.gov/</link>"
             f"<pubDate>Wed, 18 Nov 2026 19:00:00 GMT</pubDate></item>").encode()
            for i in range(40)) + b"</channel></rss>"
        report=measure([("FERC eForms RSS","https://ecollection.ferc.gov/api/rssfeed")],
                       now=NOW, fetcher=lambda _: (feed,200))
        self.assertEqual(report["feeds_connected"],1)
        row=report["sources"][0]
        self.assertEqual(row["rss_item_count"],40)
        self.assertEqual(row["fresh_links_48h"],0)
        self.assertEqual(row["link_quality"],"homepage_only")
        self.assertEqual(report["generic_homepage_only_feeds"],1)

    def test_duplicate_deep_links_count_once(self):
        feed=b"""<rss><channel>""" + b"".join(
            (f"<item><title>Natural gas LNG export terminal news {i}</title>"
             f"<link>https://example.org/news/one</link>"
             f"<pubDate>Wed, 18 Nov 2026 19:00:00 GMT</pubDate></item>").encode()
            for i in range(5)) + b"</channel></rss>"
        report=measure([("Demo","https://example.org/feed")],now=NOW,fetcher=lambda _:(feed,200))
        row=report["sources"][0]
        self.assertEqual(row["fresh_links_48h"],1)
        self.assertEqual(row["duplicate_article_urls"],4)

    def test_writes_public_metadata_only(self):
        with tempfile.TemporaryDirectory() as d:
            report=measure([("Publisher","https://energy.example.com/feed")],now=NOW,fetcher=lambda url:(FEED,200))
            write_report(report,Path(d))
            self.assertTrue((Path(d)/"source_probe.md").exists())
            data=json.loads((Path(d)/"source_probe.json").read_text())
            self.assertEqual(data["sources"][0]["fresh_links_48h"],1)


if __name__=="__main__":
    unittest.main()
