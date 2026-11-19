"""Morning source packet never substitutes index dates for publisher evidence."""
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from morning_evidence import build, write_packet, _md_label

NOW=datetime(2026,11,19,12,42,tzinfo=timezone.utc)
OBSERVED="2026-11-19T12:24:00+00:00"
PUB="2026-11-19T12:05:00+00:00"


def primary(title="US natural gas storage inventories rise",
            observed=OBSERVED, published=PUB):
    return {"url":"https://www.eia.gov/todayinenergy/detail.php?id=123",
            "title":title,"source":"EIA Today in Energy",
            "source_class":"official_agency","published_precision":"timestamp",
            "published_utc":published,"first_collector_observed_utc":observed}


def discovery(observed=OBSERVED):
    return {"url":"https://publisher.com/lng-contract",
            "title":"LNG export terminal expansion project approved",
            "gdelt_first_seen_utc":PUB,"discovery_provider":"GDELT GAL RSS",
            "first_collector_observed_utc":observed}


def release(observed=OBSERVED):
    return {"url":"https://presswire.com/power-project",
            "title":"PJM power grid reliability project",
            "feed_published_utc":PUB,"provider":"Press Release Feed",
            "first_collector_observed_utc":observed}


class MorningEvidenceTests(unittest.TestCase):
    def test_direct_publisher_data_means_observed_not_fact_checked(self):
        packet=build({"articles":[primary()]},{},{"leads":[]},now=NOW)
        row=packet["section_statuses"]["Natural Gas"]
        self.assertEqual(row["status"],"publisher_evidence_present")
        self.assertEqual(row["publisher_links_confirmed_collected"],1)
        self.assertTrue(row["links"][0]["can_prove_collected_before_cutoff"])
        self.assertFalse(row["links"][0]["original_publication_date_verified"])
        self.assertEqual(row["links"][0]["original_publisher_date"],"2026-11-19")
        self.assertIn("Oil & Energy",packet["missing_beats"])
        self.assertEqual(packet["researcher_brief_template"]["briefs"][0]["summary"],"")
        self.assertEqual(packet["researcher_brief_template"]["briefs"][0]["why_it_matters"],"")

    def test_gdelt_discovery_does_not_claim_original_pub_date(self):
        packet=build({},{"leads":[discovery()]},{},now=NOW)
        row=packet["section_statuses"]["LNG"]
        self.assertEqual(row["status"],"discovery_only_verify_original_source")
        self.assertEqual(row["publisher_links_confirmed_collected"],0)
        self.assertEqual(row["discovery_links_confirmed_collected"],1)
        self.assertIsNone(row["links"][0]["original_publisher_date"])
        self.assertIn("GDELT",row["links"][0]["notes"])
        self.assertEqual(packet["researcher_brief_template"]["briefs"][0]["source_date"],"")

    def test_source_first_discovered_after_cutoff_not_counted(self):
        late="2026-11-19T12:31:00+00:00"
        packet=build({"articles":[primary(observed=late)]},
                     {"leads":[discovery(observed=late)]},{},now=NOW)
        self.assertEqual(packet["section_statuses"]["Natural Gas"]["total_candidate_links"],0)
        self.assertEqual(packet["section_statuses"]["LNG"]["total_candidate_links"],0)
        self.assertEqual(packet["late_first_collection_exclusions"]["publisher_rss"],1)
        self.assertEqual(packet["late_first_collection_exclusions"]["global_discovery"],1)

    def test_legacy_timestamp_unknown_does_not_count_as_proven(self):
        row=primary()
        row.pop("first_collector_observed_utc")
        packet=build({"articles":[row]},{},{},now=NOW)
        section=packet["section_statuses"]["Natural Gas"]
        self.assertEqual(section["status"],"source_first_collection_time_unknown")
        self.assertEqual(section["publisher_links_confirmed_collected"],0)
        self.assertEqual(packet["unknown_first_collection_counts"]["publisher_rss"],1)

    def test_issuer_publisher_claim_kept_separate(self):
        packet=build({}, {}, {"leads":[release()]},now=NOW)
        result=packet["section_statuses"]["Power & Electricity"]
        self.assertEqual(result["status"],"date_only_or_issuer_evidence_only")
        self.assertEqual(result["publisher_links_confirmed_collected"],0)
        self.assertEqual(result["links"][0]["origin"],"issuer_claim")
        self.assertIn("claim",result["links"][0]["notes"])

    def test_date_only_notice_keeps_official_calendar_day(self):
        row=primary(title="Natural gas pipeline expansion approval by FERC",
                    published="2026-11-18T00:00:00+00:00")
        row["published_precision"]="day"
        packet=build({"articles":[row]},{},{},now=NOW)
        all_links=[item for beat in packet["section_statuses"].values()
                   for item in beat["links"]]
        self.assertTrue(any(item["origin"]=="regulatory_date_only"
                            for item in all_links))
        self.assertFalse(any(item["origin"]=="publisher_rss"
                             for item in all_links))
        self.assertEqual(all_links[0]["original_publisher_date"],None)

    def test_daylight_saving_prior_local_cutoff_is_not_24h_utc(self):
        packet=build({}, {}, {},edition_date="2026-03-08",
                     now=datetime(2026,3,8,13,0,tzinfo=timezone.utc))
        self.assertEqual(packet["news_cutoff_utc"],"2026-03-08T11:30:00+00:00")
        self.assertEqual(packet["previous_cutoff_utc"],"2026-03-07T12:30:00+00:00")

    def test_morning_preflight_cannot_see_future_rss(self):
        early=datetime(2026,11,19,11,45,tzinfo=timezone.utc)
        packet=build({"articles":[primary()]},{},{},now=early)
        self.assertEqual(packet["section_statuses"]["Natural Gas"]["total_candidate_links"],0)
        self.assertEqual(packet["observation_limit_utc"],early.isoformat())

    def test_fails_closed_for_malformed_source_state(self):
        with self.assertRaisesRegex(ValueError,"JSON array"):
            build({"articles":{}},{},{},now=NOW)
        with self.assertRaisesRegex(ValueError,"timezone"):
            build({}, {}, {},now=datetime(2026,11,19,12,42))

    def test_markdown_headline_is_escaped_for_packet(self):
        text=_md_label("Oil #Crash [Click here](https://fake.example) <script>!")
        for illegal in ("[","]","<",">","#","!"):
            self.assertNotIn(illegal,text)

    def test_packet_writes_json_markdown_and_unfilled_brief_handoff(self):
        p=build({"articles":[primary()]},{},{},now=NOW)
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"morning_evidence.json"
            write_packet(p,path)
            self.assertTrue(path.exists())
            data=json.loads(path.read_text())
            self.assertEqual(data["status"],"research_evidence_only_never_email_approved")
            m=path.with_suffix(".md").read_text()
            self.assertIn("Natural Gas",m)
            self.assertIn("No factual summaries",m)
            draft=json.loads(path.with_name(
                "morning_evidence_brief_template.json").read_text())
            self.assertEqual(draft["briefs"][0]["summary"],"")
            self.assertEqual(draft["briefs"][0]["why_it_matters"],"")


if __name__=="__main__":
    unittest.main()
