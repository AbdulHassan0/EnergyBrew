"""No invented publisher dates or false independent corroboration in gap reports."""
import json
import tempfile
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path

from source_gap_audit import reconcile,write_report
from research_desk import CATEGORY_ORDER

NOW=datetime(2026,11,19,14,0,tzinfo=timezone.utc)
def ago(minutes):
    return (NOW-timedelta(minutes=minutes)).isoformat()
def original(url,title,mins=35):
    return {"url":url,"title":title,"source":"EIA Today in Energy",
            "published_utc":ago(mins),"source_class":"official_agency",
            "published_precision":"timestamp","editorial_candidate":True}
def index(url,title,mins=25):
    return {"url":url,"title":title,"gdelt_first_seen_utc":ago(mins),
            "discovery_provider":"GDELT GAL RSS"}


class GapAuditTests(unittest.TestCase):
    def test_same_url_not_declared_as_missing(self):
        article=original("https://source.test/lng","LNG export contract supply expansion approved")
        a=reconcile({"articles":[article]},
                    {"leads":[index(article["url"],article["title"])]},now=NOW)
        self.assertEqual(a["cross_origin_classifications"]["exact_direct_publisher_link"],1)
        self.assertEqual(a["high_priority_discovery_only_leads_for_review"],[])

    def test_index_only_event_flagged_unverified_not_missing(self):
        article=index("https://news.example.com/energy/oil",
                      "OPEC crude oil output reduction hits energy supply")
        a=reconcile({},{"leads":[article]},now=NOW)
        self.assertEqual(len(a["high_priority_discovery_only_leads_for_review"]),1)
        lead=a["high_priority_discovery_only_leads_for_review"][0]
        self.assertTrue(lead["requires_original_publisher_verification"])
        self.assertEqual(lead["timestamp_basis"],"GDELT_index_first_seen_not_publisher_date")
        self.assertNotIn("published_utc",lead)
        self.assertEqual(a["gdelt_publisher_date_verified"],0)

    def test_aged_gdelt_index_link_is_excluded_from_24h(self):
        a=reconcile({},{"leads":[index("https://publisher.test/one",
                            "LNG export contract supply expansion",mins=1600)]},now=NOW)
        self.assertEqual(a["gdelt_observed_unique_urls_24h"],0)

    def test_unique_index_url_not_counted_twice(self):
        entry=index("https://www.example.com/one","Natural gas pipeline expansion project")
        a=reconcile({},{"leads":[entry,entry]},now=NOW)
        self.assertEqual(a["gdelt_observed_unique_urls_24h"],1)

    def test_press_release_url_is_not_independent_journalism(self):
        uri="https://company.test/press/energy"
        announcement={"url":uri,"title":"LNG project terminal expansion",
                      "feed_published_utc":ago(10)}
        gdelt=index(uri,announcement["title"])
        a=reconcile({},{"leads":[gdelt]},{"leads":[announcement]},now=NOW)
        self.assertEqual(a["cross_origin_classifications"].get(
            "exact_unverified_issuer_announcement_link"),1)
        self.assertEqual(a["high_priority_discovery_only_leads_for_review"],[])

    def test_no_false_publisher_activity_on_successful_empty_feed(self):
        record={"last_success_utc":ago(30),"newest_feed_published_utc":None}
        a=reconcile({"source_health":{"EIA Today in Energy":record}}, {}, now=NOW)
        eia=next(x for x in a["feed_liveness"] if x["source"]=="EIA Today in Energy")
        self.assertEqual(eia["activity"],"publisher_item_date_unknown")
        self.assertEqual(eia["timestamped_article_links_24h"],0)

    def test_six_beats_and_disclaimer_in_serialized_report(self):
        a=reconcile({}, {},now=NOW)
        self.assertEqual(set(a["direct_publisher_category_counts_24h"]),set(CATEGORY_ORDER))
        with tempfile.TemporaryDirectory() as temp:
            write_report(a,temp)
            payload=json.loads((Path(temp)/"source_gap.json").read_text())
            self.assertEqual(payload["status"],"source_gap_triage_not_a_verified_recall_score")
            self.assertIn("not proof",(Path(temp)/"source_gap.md").read_text().lower())

    def test_untrusted_publisher_title_cannot_create_markdown_links(self):
        from source_gap_audit import _plain_markdown_label
        result = _plain_markdown_label('LNG [fake](https://fake.test) | <script>')
        self.assertNotIn('[', result)
        self.assertNotIn(']', result)
        self.assertNotIn('<', result)
        self.assertNotIn('|', result)
        self.assertIn('LNG fake', result)

    def test_rejects_naive_now(self):
        with self.assertRaises(ValueError):
            reconcile({}, {},now=datetime(2026,11,19,14,0))


if __name__=="__main__":
    unittest.main()
