"""Collection health regression tests, including thin-news days and stale runs."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from newsroom_health import audit, report, REQUIRED_BEATS

NOW=datetime(2026,11,18,15,0,tzinfo=timezone.utc)


def rss_record(index, category, *, date=None, precision="timestamp", eligible=True):
    return {"url":f"https://example.gov/story/{index}",
            "published_utc":(date or NOW-timedelta(hours=2)).isoformat(),
            "published_precision":precision,
            "category":category,
            "editorial_candidate":eligible}


def discovery_lead(index, *, date=None, score=50):
    return {"url":f"https://news.example.org/{index}",
            "gdelt_first_seen_utc":(date or NOW-timedelta(hours=1)).isoformat(),
            "publisher_published_utc":None, "published_time_verified":False,
            "relevance_score":score}


def rss_report(*, date=None, connected=10):
    return {"run_utc":(date or NOW).isoformat(),
            "feeds_connected":connected,"feeds_checked":11}


def broad_discovery():
    return {"run_utc":NOW.isoformat(),"status":"ok"}


class NewsroomHealthTests(unittest.TestCase):
    def test_no_articles_critical_even_if_feeds_connect(self):
        h=audit({"articles":[]},rss_report(),{"leads":[discovery_lead(1)]},broad_discovery(),now=NOW)
        self.assertEqual(h["status"],"critical")
        self.assertIn("No high-signal", " ".join(h["critical"]))
        self.assertEqual(h["research_first_seen_links_24h"],1)
        self.assertEqual(h["research_publisher_dates_verified"],0)

    def test_old_and_date_only_do_not_count(self):
        state={"articles":[rss_record(1,"Natural Gas & LNG",date=NOW-timedelta(days=2)),
                           rss_record(2,"Oil & Energy",precision="day")]}
        h=audit(state,rss_report(),now=NOW)
        self.assertEqual(h["timestamped_editorial_leads_24h"],0)

    def test_good_coverage_requires_multiple_beats(self):
        state={"articles":[rss_record(i,REQUIRED_BEATS[i%4]) for i in range(12)]}
        h=audit(state,rss_report(),{"leads":[discovery_lead(1)]},broad_discovery(),now=NOW)
        self.assertEqual(h["status"],"operational_coverage_target_met")
        self.assertEqual(h["timestamped_editorial_leads_24h"],12)
        self.assertEqual(h["unobserved_beats"],[])

    def test_thin_category_coverage_flagged(self):
        state={"articles":[rss_record(i,"Power & Electricity") for i in range(12)]}
        h=audit(state,rss_report(),{"leads":[discovery_lead(1)]},broad_discovery(),now=NOW)
        self.assertEqual(h["status"],"degraded")
        self.assertIn("Natural Gas & LNG",h["unobserved_beats"])

    def test_stale_rss_run_is_critical(self):
        h=audit({"articles":[rss_record(1,"Power & Electricity")]},
                rss_report(date=NOW-timedelta(hours=15)),
                {"leads":[discovery_lead(1)]},broad_discovery(),now=NOW)
        self.assertEqual(h["status"],"critical")
        self.assertTrue(any("no recent" in x.lower() for x in h["critical"]))

    def test_no_connected_rss_critical_despite_discovery(self):
        h=audit({"articles":[]},rss_report(connected=0),
                {"leads":[discovery_lead(i) for i in range(40)]},broad_discovery(),now=NOW)
        self.assertEqual(h["status"],"critical")
        self.assertEqual(h["research_first_seen_links_24h"],40)

    def test_discovery_degraded_not_misreported_healthy(self):
        state={"articles":[rss_record(i,REQUIRED_BEATS[i%4]) for i in range(12)]}
        h=audit(state,rss_report(),{"leads":[discovery_lead(1)]},
                {"run_utc":NOW.isoformat(),"status":"degraded"},now=NOW)
        self.assertEqual(h["status"],"degraded")
        self.assertTrue(any("rate limited" in w for w in h["warnings"]))

    def test_old_indexed_lead_not_counted(self):
        h=audit({"articles":[]},rss_report(),
                {"leads":[discovery_lead(1,date=NOW-timedelta(days=3))]},
                broad_discovery(),now=NOW)
        self.assertEqual(h["research_first_seen_links_24h"],0)

    def test_persists_report_even_when_critical(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/"out"
            h=report(Path(d)/"rss.json",Path(d)/"status.json",
                     Path(d)/"discovery.json",Path(d)/"discovery_status.json",
                     out,now=NOW)
            self.assertEqual(h["status"],"critical")
            self.assertTrue((out/"health.json").exists())
            self.assertTrue((out/"health.md").exists())
            self.assertIn("Critical",(out/"health.md").read_text())


if __name__=="__main__":
    unittest.main()
