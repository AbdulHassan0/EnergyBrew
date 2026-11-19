"""Availability probe must not download GDELT article files."""
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from gal_archive_probe import probe, targets, write_report

NOW=datetime(2026,11,18,20,0,tzinfo=timezone.utc)

class ArchiveProbeTests(unittest.TestCase):
    def test_targets_are_fixed_gdelt_https_minute_archives(self):
        x=targets(NOW)
        self.assertGreaterEqual(len(x),5)
        self.assertTrue(all(s.startswith("https://data.gdeltproject.org/gdeltv3/gal/") for s in x))
        self.assertIn("20200101000100.gal.json.gz",x[0])
    def test_head_confirmation_does_not_claim_full_backfill(self):
        r=probe(NOW,fetcher=lambda url:(200,{"content_length":"1200","content_type":"application/gzip"}))
        self.assertEqual(r["head_confirmed"],r["tested"])
        self.assertIn("not prove",r["caution"])
    def test_403_and_404_are_unavailable_without_bypass(self):
        r=probe(NOW,fetcher=lambda url:(403,{}))
        self.assertEqual(r["head_confirmed"],0)
        self.assertEqual(r["status"],"not_confirmed")
    def test_probe_file_does_not_contain_article_text(self):
        with tempfile.TemporaryDirectory() as d:
            r=probe(NOW,fetcher=lambda url:(404,{}))
            write_report(r,Path(d))
            self.assertTrue((Path(d)/"gal_archive_probe.json").exists())

if __name__=="__main__":
    unittest.main()
