"""Research desk tests: no external requests, no publisher contents or emails."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from research_desk import assemble, generate

NOW = datetime(2026, 11, 18, 19, 0, tzinfo=timezone.utc)
def dt(hours=0):
    return (NOW - timedelta(hours=hours)).isoformat()
def official(url="https://eia.gov/news/1", title="US natural gas LNG feedgas supply rises"):
    return {"url":url, "title":title, "published_utc":dt(1),
            "source":"EIA", "published_precision":"timestamp"}
def global_lead(url="https://publisher.com/story/1", title="LNG export terminal expansion project approved"):
    return {"url":url, "title":title, "gdelt_first_seen_utc":dt(0.5),
            "discovery_provider":"GDELT GAL RSS"}
def release(url="https://wire.com/story/2", title="PJM power grid reliability project"):
    return {"url":url, "title":title, "feed_published_utc":dt(2),
            "provider":"Press Release Feed"}

class DeskTests(unittest.TestCase):
    def test_separated_provenance_and_status(self):
        r=assemble([official()], [global_lead()], [release()], now=NOW)
        self.assertEqual(r["unique_relevant_urls_7d"],3)
        self.assertEqual(r["publisher_timestamped_official_24h"],1)
        self.assertEqual(r["discovery_publisher_dates_verified"],0)
        by_kind={x["origin"]:x for x in r["stories"]}
        self.assertTrue(by_kind["official_rss"]["publisher_time_verified"])
        self.assertFalse(by_kind["global_discovery"]["publisher_time_verified"])
        self.assertEqual(by_kind["company_announcement"]["time_basis"],"third_party_release_feed_date_unverified")
        self.assertTrue(all(x["editorial_status"]=="research_only_not_approved" for x in r["stories"]))

    def test_url_deduplicated_with_official_priority(self):
        o=official()
        d=global_lead(url=o["url"])
        r=assemble([o],[d],[],now=NOW)
        self.assertEqual(r["unique_relevant_urls_7d"],1)
        self.assertEqual(r["stories"][0]["origin"],"official_rss")
        self.assertIn("global_discovery",r["stories"][0]["other_origins"])

    def test_regulatory_day_only_cannot_be_timestamped(self):
        r=assemble([dict(official(),published_precision="day")],[],[],now=NOW)
        self.assertEqual(r["publisher_timestamped_official_24h"],0)
        self.assertEqual(r["stories"][0]["queue"],"regulatory_date_only")

    def test_missing_old_and_malformed_rejected(self):
        x=global_lead()
        x["gdelt_first_seen_utc"]=dt(24*10)
        r=assemble([], [x,dict(x,gdelt_first_seen_utc="bad")],[],now=NOW)
        self.assertEqual(r["unique_relevant_urls_7d"],0)

    def test_foreign_script_and_promotional_flags(self):
        x=global_lead(title="Ελλάδα LNG export terminal expansion")
        y=release(title="Vendor launches SEO services for power grid operators")
        r=assemble([], [x],[y],now=NOW)
        self.assertTrue(any("translation_and_source_review" in row["needs_editor_review"] for row in r["stories"]))
        self.assertTrue(any("promotional_or_generic_marketing" in row["needs_editor_review"] for row in r["stories"]))

    def test_domain_cap(self):
        leads=[global_lead(url=f"https://same.org/news/{n}",title=f"LNG export terminal expansion project {n}") for n in range(10)]
        r=assemble([],leads,[],now=NOW)
        self.assertEqual(r["selected_research_links"],4)

    def test_report_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"rss.json").write_text(json.dumps({"articles":[official()]}))
            (root/"discovery.json").write_text(json.dumps({"leads":[global_lead()]}))
            result=generate(root/"rss.json",root/"discovery.json",root/"missing.json",root/"out",now=NOW)
            self.assertEqual(result["selected_research_links"],2)
            self.assertTrue((root/"out/desk.json").exists())
            self.assertIn("Not fact-checked", (root/"out/desk.md").read_text())

if __name__=="__main__":
    unittest.main()
