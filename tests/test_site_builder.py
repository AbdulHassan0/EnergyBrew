"""Regression checks for the EnergyBrew static research export."""
import json
import tempfile
import unittest
from pathlib import Path
from site_builder import build_data, create_site, export_story, read_json, safe_url

SAMPLE = {"generated_utc":"2026-11-18T19:13:00+00:00",
          "unique_relevant_urls_7d":2,
          "selected_topic_coverage_counts":{"Natural Gas & LNG":1},
          "stories":[
              {"title":"  Test gas headline  ","url":"https://www.eia.gov/article","source":"EIA",
               "domain":"eia.gov","category":"Natural Gas & LNG","coverage_themes":["Natural Gas & LNG"],
               "origin":"official_rss","observed_time_utc":"2026-11-18T14:00:00+00:00",
               "publisher_time_verified":True},
              {"title":"Duplicate story","url":"https://www.eia.gov/article",
               "category":"Natural Gas & LNG","origin":"official_rss"},
              {"title":"Unsafe","url":"javascript:alert(1)","origin":"global_discovery"}
          ]}

class SiteBuilderTests(unittest.TestCase):
    def test_safe_urls_only(self):
        self.assertIsNone(safe_url("javascript:alert(1)"))
        self.assertIsNone(safe_url("https://u:p@example.com/article"))
        self.assertEqual(safe_url("https://eia.gov/"),"https://eia.gov/")

    def test_source_not_pretended_approved(self):
        article = export_story(SAMPLE["stories"][0])
        self.assertEqual(article["editorial_status"],"research_only_not_approved")
        self.assertTrue(article["publisher_time_verified"])
        discovery = dict(SAMPLE["stories"][0], origin="global_discovery")
        self.assertFalse(export_story(discovery)["publisher_time_verified"])

    def test_dedup_and_no_synthetic_stories(self):
        result = build_data(SAMPLE)
        self.assertEqual(len(result["stories"]),1)
        self.assertEqual(result["stories"][0]["title"],"Test gas headline")

    def test_missing_data_fails_closed(self):
        with self.assertRaises(ValueError):
            build_data({})
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ValueError):
                read_json(Path(root)/"missing.json",required=True)

    def test_export_writes_site(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            assets = folder/"assets"
            assets.mkdir()
            for name in ("index.html","styles.css","app.js"):
                (assets/name).write_text("test",encoding="utf-8")
            data=create_site(SAMPLE,{}, {},assets,folder/"dist")
            self.assertEqual(len(data["stories"]),1)
            output=json.loads((folder/"dist/data/feed.json").read_text(encoding="utf-8"))
            self.assertEqual(output["stories"][0]["title"],"Test gas headline")
            self.assertTrue((folder/"dist/index.html").exists())
            self.assertIn("Disallow: /",(folder/"dist/robots.txt").read_text())

class FrontendContractTests(unittest.TestCase):
    """Keep the newsletter promise, live controls and editorial caveats visible."""

    def test_newsletter_brand_and_reading_views(self):
        root = Path(__file__).resolve().parent.parent / "frontend"
        html = (root / "index.html").read_text(encoding="utf-8")
        js = (root / "app.js").read_text(encoding="utf-8")
        css = (root / "styles.css").read_text(encoding="utf-8")
        for phrase in ("EnergyBrew", "Your daily shot", "morning brew",
                       "data-view=\"morning\"", "data-view=\"desk\"",
                       "research preview", "id=\"progress-track\"",
                       "id=\"search\"", "id=\"saved-filter\""):
            self.assertIn(phrase, html)
        self.assertIn("editorial review", html)
        self.assertIn("morningCut", js)
        self.assertIn("timeText", js)
        self.assertIn("readKey", js)
        self.assertIn("@media(max-width:600px)", css)
        self.assertIn("prefers-reduced-motion:reduce", css)

    def test_site_never_misrepresents_email_signup(self):
        root = Path(__file__).resolve().parent.parent / "frontend"
        html = (root / "index.html").read_text(encoding="utf-8")
        self.assertIn("email newsletter is in development", html)
        self.assertNotIn('type="email"', html)

if __name__=="__main__":
    unittest.main()
