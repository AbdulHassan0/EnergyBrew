"""Research desk tests: no external requests, no publisher contents or emails."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from research_desk import assemble, generate, entry

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
    def test_specialist_event_collapsed_in_short_research_desk(self):
        a=dict(official(url="https://source-a.com/one",title="China Gas Upsizes Long-Term LNG Supply with U.S. Venture Global"),source_class="specialist_publisher")
        b=dict(official(url="https://source-b.com/two",title="Venture Global’s bigger LNG deal with China Gas adds 500,000 tons annually"),source_class="specialist_publisher")
        result=assemble([a,b],[],[],now=NOW)
        self.assertEqual(result["unique_relevant_urls_7d"],2)
        self.assertEqual(result["selected_research_links"],1)
        self.assertEqual(result["publisher_timestamped_specialist_24h"],2)
        self.assertEqual(result["publisher_timestamped_official_24h"],0)
        self.assertEqual(result["likely_same_event_links_suppressed"],1)
        self.assertEqual(len(result["stories"][0]["related_reports"]),1)

    def test_grid_operator_provenance(self):
        a = dict(official(url="https://insidelines.pjm.com/a",title="PJM grid reliability transmission expansion"),source_class="system_operator_primary")
        r = assemble([a],[],[],now=NOW)
        self.assertEqual(r["stories"][0]["queue"],"system_operator_primary_24h")
        self.assertEqual(r["stories"][0]["time_basis"],"system_operator_rss_timestamp")
        self.assertEqual(r["system_operator_primary_24h"],1)
        self.assertEqual(r["publisher_timestamped_official_24h"],0)

    def test_gal_provider_timestamp_does_not_imply_original_publication_date(self):
        lead=global_lead()
        lead["discovery_provider"]="GDELT GAL RSS"
        result=assemble([], [lead], [], now=NOW)
        self.assertEqual(result["stories"][0]["time_basis"],
                         "gdelt_gal_rss_provider_time_unverified")
        self.assertFalse(result["stories"][0]["publisher_time_verified"])

    def test_specialist_publisher_provenance(self):
        article=official()
        article["source_class"]="specialist_publisher"
        result=assemble([article],[],[],now=NOW)
        self.assertEqual(result["stories"][0]["source_class"],"specialist_publisher")
        self.assertEqual(result["stories"][0]["time_basis"],"specialist_publisher_rss_timestamp")
        self.assertEqual(result["stories"][0]["queue"],"specialist_publisher_24h")

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
        self.assertIn("promotional_or_generic_marketing", entry(y, "company_announcement", NOW)["needs_editor_review"])
        self.assertFalse(any("promotional_or_generic_marketing" in row["needs_editor_review"] for row in r["stories"]))

    def test_domain_cap(self):
        leads=[global_lead(url=f"https://same.org/news/{n}",title=f"LNG export terminal expansion project {n}") for n in range(10)]
        r=assemble([],leads,[],now=NOW)
        self.assertEqual(r["selected_research_links"],4)

    def test_official_news_ranks_above_release_even_with_lower_raw_score(self):
        o=official(title="Natural gas production pipeline expansion")
        p=release(title="Natural gas LNG feedgas pipeline expansion investment project")
        r=assemble([o],[],[p],now=NOW)
        self.assertEqual(r["stories"][0]["origin"],"official_rss")

    def test_release_cap_and_low_impact_flag(self):
        releases=[release(url=f"https://wire.com/{i}",title=f"LNG terminal expansion infrastructure project {i}") for i in range(5)]
        d=global_lead(title="Students empowered to conserve electricity")
        r=assemble([], [d], releases, now=NOW)
        self.assertLessEqual(sum(x["origin"]=="company_announcement" for x in r["stories"]),2)
        self.assertFalse(any(x["title"] == d["title"] for x in r["stories"]))  # filtered before selection

    def test_geopolitics_is_a_sixth_market_news_beat(self):
        a=official(url="https://news.example.com/hormuz",
            title="Iranian drone attacks disrupt oil tanker shipping through Strait of Hormuz")
        result=assemble([a],[],[],now=NOW)
        self.assertEqual(result["selected_research_links"],1)
        story=result["stories"][0]
        self.assertEqual(story["category"],"Geopolitics")
        self.assertIn("Oil & Energy",story["coverage_themes"])
        self.assertNotIn("Geopolitics",result["missing_categories"])

    def test_political_news_without_energy_exposure_is_not_a_market_lead(self):
        x=global_lead(title="European Union announces parliamentary election date")
        result=assemble([], [x], [], now=NOW)
        self.assertEqual(result["selected_research_links"],0)

    def test_every_available_beat_can_be_selected_in_short_six_story_desk(self):
        candidates=[
            ("Henry Hub natural gas storage prices rise", "Natural Gas"),
            ("Venture Global LNG supply agreement expands", "LNG"),
            ("PJM power grid electricity reliability update", "Power & Electricity"),
            ("WTI crude oil inventories weekly report", "Oil & Energy"),
            ("FERC infrastructure pipeline expansion investment project", "Infrastructure & Investment"),
            ("Iranian drone attacks threaten oil tankers near Strait of Hormuz", "Geopolitics"),
        ]
        rows=[official(url=f"https://sources.example.com/news/{i}",
                       title=title) for i,(title,_) in enumerate(candidates)]
        result=assemble(rows,[],[],now=NOW,max_stories=6)
        self.assertEqual(len(result["stories"]),6)
        for _,category in candidates:
            self.assertEqual(result["selected_category_counts"][category],1)

    def test_inferred_speculative_geopolitics_gets_review_flag_and_lower_rank(self):
        x=official(url="https://news.example.com/is-war-looming",
                   title="Is another US Iran war looming?")
        y=official(url="https://news2.example.com/oil-strikes",
                   title="Iranian missile attacks hit oil tankers in Strait of Hormuz")
        result=assemble([x,y],[],[],now=NOW)
        a=next(row for row in result["stories"] if "looming" in row["title"])
        b=next(row for row in result["stories"] if "oil tankers" in row["title"])
        self.assertIn("energy_market_exposure_inferred",a["needs_editor_review"])
        self.assertIn("speculative_geopolitical_headline",a["needs_editor_review"])
        self.assertLess(a["rank"],b["rank"])

    def test_infrastructure_as_secondary_topic(self):
        r=assemble([official(title="Gas pipeline expansion for LNG exports")], [], [], now=NOW)
        self.assertEqual(r["selected_topic_coverage_counts"]["Infrastructure & Investment"],1)
        self.assertNotIn("Infrastructure & Investment",r["missing_categories"])

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
