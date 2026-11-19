"""Morning editorial cutoff, DST, freshness, provenance and immutable handoff tests."""
import json
import tempfile
import unittest
from datetime import date,datetime,timedelta,timezone
from pathlib import Path

from morning_readiness import prepare, local_schedule, write_preparation

CT=datetime(2026,11,19,6,30,tzinfo=timezone(timedelta(hours=-6)))
CUTOFF=CT.astimezone(timezone.utc)
NOW=CUTOFF+timedelta(minutes=5)

def time_str(minutes=0):
    return (CUTOFF+timedelta(minutes=minutes)).isoformat()

def fixtures():
    rss={"runs":[{"run_utc":time_str(-20),"feeds_connected":15,"feeds_checked":15,
                  "scan_state":"healthy"}],
         "articles":[{"url":"https://example.org/news/old","title":"Henry Hub natural gas production surges",
                      "published_utc":time_str(-90),"published_precision":"timestamp"},
                     {"url":"https://example.org/news/future","title":"LNG export terminal new deal",
                      "published_utc":time_str(+10),"published_precision":"timestamp"}]}
    discovery={"gal_runs":[{"run_utc":time_str(-i),"status":"ok"} for i in range(0,361,10)],
               "leads":[{"url":"https://example.net/energy/world","title":"Iranian missiles hit oil tanker near Strait of Hormuz",
                         "gdelt_first_seen_utc":time_str(-12)},
                        {"url":"https://example.net/energy/later","title":"Russian oil refinery struck by missile",
                         "gdelt_first_seen_utc":time_str(+2)}]}
    releases={"leads":[]}
    return rss,discovery,releases

class MorningTests(unittest.TestCase):
    def test_central_time_cutoff_spring_and_fall(self):
        winter=local_schedule("2026-11-19")
        summer=local_schedule("2026-07-15")
        self.assertEqual(winter["news_cutoff_utc"],"2026-11-19T12:30:00+00:00")
        self.assertEqual(summer["news_cutoff_utc"],"2026-07-15T11:30:00+00:00")
        self.assertEqual(winter["target_delivery_utc"],"2026-11-19T13:00:00+00:00")
        self.assertEqual(summer["target_delivery_utc"],"2026-07-15T12:00:00+00:00")

    def test_ready_edition_freezes_only_pre_cutoff_records(self):
        a,b,c=fixtures()
        result=prepare(a,b,c,now=NOW)
        self.assertEqual(result["status"],"ready_for_editor_review")
        urls=[x["url"] for x in result["research_desk"]["stories"]]
        self.assertEqual(len(urls),2)
        self.assertIn("https://example.org/news/old",urls)
        self.assertNotIn("https://example.org/news/future",urls)
        self.assertNotIn("https://example.net/energy/later",urls)
        self.assertEqual(result["publication_status"],"research_only_not_approved_not_sent")

    def test_missing_gal_overnight_intervals_block_readiness(self):
        a,b,c=fixtures()
        b["gal_runs"]=[{"run_utc":time_str(-5),"status":"ok"}]
        result=prepare(a,b,c,now=NOW)
        self.assertIn("overnight_gdelt_sampling_below_minimum",result["blocking_issues"])
        self.assertEqual(result["status"],"blocked_collection_readiness")
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(write_preparation(result,d))
            self.assertFalse((Path(d)/"research_2026-11-19.json").exists())
            self.assertTrue((Path(d)/"readiness_2026-11-19.json").exists())

    def test_stale_rss_blocks_without_misreporting_no_articles(self):
        a,b,c=fixtures()
        a["runs"][0]["run_utc"]=time_str(-130)
        result=prepare(a,b,c,now=NOW)
        self.assertIn("publisher_rss_not_recent_at_cutoff",result["blocking_issues"])

    def test_pre_cutoff_cannot_freeze(self):
        a,b,c=fixtures()
        result=prepare(a,b,c,now=CUTOFF-timedelta(minutes=1))
        self.assertIn("edition_cutoff_not_reached",result["blocking_issues"])

    def test_day_only_notice_today_is_not_claimed_known_at_cutoff(self):
        a,b,c=fixtures()
        a["articles"].append({"url":"https://agency.gov/notices/today",
                              "title":"FERC pipeline permit notice",
                              "published_utc":"2026-11-19T00:00:00+00:00",
                              "published_precision":"day"})
        result=prepare(a,b,c,now=NOW)
        self.assertNotIn("https://agency.gov/notices/today",
                         [x["url"] for x in result["research_desk"]["stories"]])

    def test_fresh_scan_after_cutoff_does_not_import_late_news(self):
        a,b,c=fixtures()
        a["runs"].append({"run_utc":time_str(+5),"feeds_checked":15,
                          "feeds_connected":15,"scan_state":"healthy"})
        b["gal_runs"].append({"run_utc":time_str(+5),"status":"ok"})
        result=prepare(a,b,c,now=NOW)
        self.assertEqual(result["status"],"ready_for_editor_review")
        self.assertIn("rss_polled_after_cutoff_records_strictly_filtered_to_cutoff",result["warnings"])
        titles=[x["title"] for x in result["research_desk"]["stories"]]
        self.assertNotIn("LNG export terminal new deal",titles)
        self.assertNotIn("Russian oil refinery struck by missile",titles)

    def test_late_morning_preparation_not_marked_ready(self):
        a,b,c=fixtures()
        result=prepare(a,b,c,now=CUTOFF+timedelta(minutes=25))
        self.assertIn("insufficient_editorial_review_time_before_7am",result["blocking_issues"])

    def test_overnight_and_early_evening_use_distinct_time_buckets(self):
        a,b,c=fixtures()
        a["articles"].append({"url":"https://example.org/news/evening",
            "title":"EIA US natural gas inventories report",
            "published_utc":time_str(-11*60),"published_precision":"timestamp"})
        r=prepare(a,b,c,now=NOW)
        by_url={x["url"]:x for x in r["research_desk"]["stories"]}
        self.assertEqual(by_url["https://example.net/energy/world"]["morning_time_bucket"],
                         "overnight_on_source_time_basis")
        self.assertEqual(by_url["https://example.org/news/evening"]["morning_time_bucket"],
                         "since_previous_cutoff_on_source_time_basis")

    def test_prior_day_news_is_background_not_filling_fresh_candidate_slots(self):
        a,b,c=fixtures()
        a["articles"].append({"url":"https://example.org/news/previous",
            "title":"Venture Global LNG terminal investment advances",
            "published_utc":time_str(-30*60),"published_precision":"timestamp"})
        r=prepare(a,b,c,now=NOW)
        self.assertEqual(r["primary_candidate_count_since_previous_cutoff"],2)
        self.assertEqual(r["older_background_context_count"],1)
        self.assertNotIn("https://example.org/news/previous",
                         [x["url"] for x in r["research_desk"]["stories"]])
        self.assertEqual(r["background_context"][0]["morning_time_bucket"],"older_background_context")

    def test_previous_research_is_repeat_flag_not_automatic_exclusion(self):
        a,b,c=fixtures()
        previous={"research_desk":{"stories":[{"url":"https://example.org/news/old",
                 "title":"Henry Hub natural gas production surges",
                 "observed_time_utc":time_str(-2*60),
                 "category":"Natural Gas"}]}}
        r=prepare(a,b,c,now=NOW,previous_research=previous)
        by_url={x["url"]:x for x in r["research_desk"]["stories"]}
        self.assertEqual(by_url["https://example.org/news/old"]["prior_research_repeat_review"],
                         "same_url_previous_research")
        self.assertEqual(r["primary_candidate_count_since_previous_cutoff"],2)

    def test_immutable_research_snapshot_cannot_be_rewritten(self):
        a,b,c=fixtures()
        result=prepare(a,b,c,now=NOW)
        with tempfile.TemporaryDirectory() as d:
            self.assertTrue(write_preparation(result,d))
            self.assertFalse(write_preparation(result,d))
            modified=json.loads(json.dumps(result))
            modified["research_desk"]["stories"][0]["title"]="Rewritten after lock"
            with self.assertRaisesRegex(ValueError,"Immutable"):
                write_preparation(modified,d)
            self.assertNotIn("Rewritten after lock",(Path(d)/"research_2026-11-19.json").read_text())

    def test_no_candidates_is_not_ready(self):
        a,b,c=fixtures()
        a["articles"]=[]
        b["leads"]=[]
        result=prepare(a,b,c,now=NOW)
        self.assertIn("no_qualifying_research_leads",result["blocking_issues"])

if __name__=="__main__":
    unittest.main()
