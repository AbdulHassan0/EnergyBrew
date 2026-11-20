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


def rss_report(*, date=None, connected=11):
    return {"run_utc":(date or NOW).isoformat(),
            "feeds_connected":connected,"feeds_checked":11}


def broad_discovery():
    return {"run_utc":NOW.isoformat(),"status":"ok"}


class NewsroomHealthTests(unittest.TestCase):
    def test_no_articles_is_not_by_itself_a_source_outage(self):
        h=audit({"articles":[]},rss_report(),{"leads":[discovery_lead(1)]},broad_discovery(),now=NOW)
        self.assertEqual(h["status"],"degraded")
        self.assertIn("No high-signal", " ".join(h["warnings"]))
        self.assertEqual(h["research_first_seen_links_24h"],1)
        self.assertEqual(h["research_publisher_dates_verified"],0)

    def test_old_and_date_only_do_not_count(self):
        state={"articles":[rss_record(1,"Natural Gas",date=NOW-timedelta(days=2)),
                           rss_record(2,"Oil & Energy",precision="day")]}
        h=audit(state,rss_report(),now=NOW)
        self.assertEqual(h["timestamped_editorial_leads_24h"],0)

    def test_good_coverage_requires_multiple_beats(self):
        state={"articles":[rss_record(i,REQUIRED_BEATS[i%len(REQUIRED_BEATS)]) for i in range(12)]}
        h=audit(state,rss_report(),{"leads":[discovery_lead(1)]},broad_discovery(),now=NOW)
        self.assertEqual(h["status"],"operational_coverage_target_met")
        self.assertEqual(h["timestamped_editorial_leads_24h"],12)
        self.assertEqual(h["unobserved_beats"],[])
        self.assertEqual(len(REQUIRED_BEATS),6)
        self.assertEqual(h["geopolitical_energy_leads_24h"],2)

    def test_no_geopolitical_event_is_not_in_itself_a_feed_failure(self):
        categories=[b for b in REQUIRED_BEATS if b!="Geopolitics"]
        rss={"articles":[rss_record(i,categories[i%len(categories)]) for i in range(15)]}
        h=audit(rss,rss_report(),{"leads":[discovery_lead(1)]},broad_discovery(),now=NOW)
        self.assertEqual(h["status"],"operational_coverage_target_met")
        self.assertIn("Geopolitics",h["unobserved_beats"])
        self.assertEqual(h["event_driven_beats_with_no_observed_stories"],["Geopolitics"])
        self.assertEqual(h["geopolitical_energy_leads_24h"],0)

    def test_thin_category_coverage_flagged(self):
        state={"articles":[rss_record(i,"Power & Electricity") for i in range(12)]}
        h=audit(state,rss_report(),{"leads":[discovery_lead(1)]},broad_discovery(),now=NOW)
        self.assertEqual(h["status"],"degraded")
        self.assertIn("Natural Gas",h["unobserved_beats"])
        self.assertIn("Geopolitics",h["unobserved_beats"])

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
        state={"articles":[rss_record(i,REQUIRED_BEATS[i%len(REQUIRED_BEATS)]) for i in range(12)]}
        h=audit(state,rss_report(),{"leads":[discovery_lead(1)]},
                {"run_utc":NOW.isoformat(),"status":"degraded"},now=NOW)
        self.assertEqual(h["status"],"degraded")
        self.assertTrue(any("rate limited" in w for w in h["warnings"]))

    def test_doc_cooldown_with_healthy_gal_backup_is_distinguished(self):
        state={"articles":[rss_record(i,REQUIRED_BEATS[i%len(REQUIRED_BEATS)]) for i in range(12)]}
        x=audit(state,rss_report(),{"leads":[discovery_lead(1)]},
                {"status":"provider_cooldown","run_utc":NOW.isoformat()},
                gal_report={"status":"ok","run_utc":NOW.isoformat(),
                            "potential_sampling_gap":False},now=NOW)
        self.assertTrue(x["rolling_gal_recent_healthy"])
        self.assertEqual(x["rolling_gal_status"],"ok")
        self.assertTrue(any("recent GAL poll does not establish continuous coverage" in w
                            for w in x["warnings"]))
        self.assertFalse(x["rolling_gal_24h_continuity_adequate"])
        self.assertEqual(x["status"],"degraded")

    def test_one_recent_gal_sample_does_not_claim_24h_continuity(self):
        state={"articles":[rss_record(i,REQUIRED_BEATS[i%len(REQUIRED_BEATS)])
                           for i in range(12)]}
        gal={"status":"ok","run_utc":NOW.isoformat(),"potential_sampling_gap":False}
        discovery={"leads":[discovery_lead(1)],
                   "gal_runs":[{"run_utc":NOW.isoformat(),"completed_utc":NOW.isoformat(),
                                "status":"ok","feed_payload_sha256":"one-sample"}]}
        h=audit(state,rss_report(),discovery,broad_discovery(),
                gal_report=gal,now=NOW)
        self.assertTrue(h["rolling_gal_recent_healthy"])
        self.assertFalse(h["rolling_gal_24h_continuity_adequate"])
        self.assertLess(h["rolling_gal_24h_coverage_upper_bound_pct"],2)
        self.assertGreater(h["rolling_gal_24h_unobserved_minutes_at_least"],1400)
        self.assertEqual(h["status"],"degraded")
        self.assertTrue(any("sampling continuity weak" in w for w in h["warnings"]))

    def test_repeated_identical_gal_payload_does_not_inflate_health(self):
        state={"articles":[rss_record(i,REQUIRED_BEATS[i%len(REQUIRED_BEATS)])
                           for i in range(12)]}
        runs=[{"run_utc":(NOW-timedelta(minutes=10*i)).isoformat(),
               "status":"ok","feed_payload_sha256":"same-bytes"} for i in range(6)]
        h=audit(state,rss_report(),{"leads":[discovery_lead(1)],"gal_runs":runs},
                broad_discovery(),gal_report={"status":"ok","run_utc":NOW.isoformat()},
                now=NOW)
        self.assertLess(h["rolling_gal_24h_coverage_upper_bound_pct"],2)
        self.assertEqual(h["status"],"degraded")

    def test_missing_gal_sample_is_reported_when_run_data_present(self):
        x=audit({"articles":[]},rss_report(),{"leads":[]},broad_discovery(),
                gal_report={"status":"ok","run_utc":(NOW-timedelta(hours=2)).isoformat(),
                            "potential_sampling_gap":True},now=NOW)
        self.assertFalse(x["rolling_gal_recent_healthy"])
        self.assertTrue(any("Rolling GDELT GAL sample failed" in w for w in x["warnings"]))
        self.assertTrue(any("missed rolling GAL" in w for w in x["warnings"]))

    def test_old_indexed_lead_not_counted(self):
        h=audit({"articles":[]},rss_report(),
                {"leads":[discovery_lead(1,date=NOW-timedelta(days=3))]},
                broad_discovery(),now=NOW)
        self.assertEqual(h["research_first_seen_links_24h"],0)

    def test_one_connected_feed_is_critical_even_with_editorial_stories(self):
        rss_state={"articles":[rss_record(i,REQUIRED_BEATS[i%len(REQUIRED_BEATS)]) for i in range(12)]}
        h=audit(rss_state,rss_report(connected=1),
                {"leads":[discovery_lead(1)]},broad_discovery(),now=NOW)
        self.assertEqual(h["status"],"critical")
        self.assertTrue(any("below quorum" in msg for msg in h["critical"]))

    def test_press_release_claims_count_separately_from_verified_stories(self):
        state={"articles":[rss_record(i,REQUIRED_BEATS[i%len(REQUIRED_BEATS)]) for i in range(12)]}
        releases={"leads":[{"url":"https://example.com/company-announcement",
                            "feed_published_utc":NOW.isoformat(),
                            "published_time_verified":False,
                            "named_issuer_verified":False}]}
        x=audit(state,rss_report(),{"leads":[discovery_lead(1)]},broad_discovery(),
                release_state=releases,
                release_report={"status":"ok","run_utc":NOW.isoformat()},now=NOW)
        self.assertEqual(x["company_announcement_links_24h"],1)
        self.assertEqual(x["company_announcement_publisher_dates_verified"],0)
        self.assertEqual(x["timestamped_editorial_leads_24h"],12)
        self.assertEqual(x["status"],"operational_coverage_target_met")

    def test_press_release_provider_failure_is_reported(self):
        state={"articles":[rss_record(i,REQUIRED_BEATS[i%len(REQUIRED_BEATS)]) for i in range(12)]}
        x=audit(state,rss_report(),{"leads":[discovery_lead(1)]},broad_discovery(),
                release_state={"leads":[]},release_report={"status":"degraded"},now=NOW)
        self.assertEqual(x["status"],"degraded")
        self.assertTrue(any("announcement feed" in w for w in x["warnings"]))

    def test_ferc_date_only_source_is_visible_but_not_in_timed_rss_counts(self):
        state={"articles":[{
            "url":"https://www.ferc.gov/news-events/news/ferc-gas-infrastructure",
            "title":"FERC approves major gas infrastructure facilities",
            "source":"FERC News Releases","published_precision":"day",
            "published_utc":"2026-11-18T00:00:00+00:00",
            "first_collector_observed_utc":NOW.isoformat(),
            "editorial_candidate":False}]}
        h=audit(state,rss_report(),{"leads":[]},broad_discovery(),
                ferc_report={"status":"ok","run_utc":NOW.isoformat()},now=NOW)
        self.assertEqual(h["ferc_news_status"],"ok")
        self.assertEqual(h["ferc_news_day_only_links_retained"],1)
        self.assertEqual(h["ferc_news_day_only_links_first_collected_24h"],1)
        self.assertEqual(h["timestamped_editorial_leads_24h"],0)

    def test_ferc_outage_degrades_health_without_erasing_other_leads(self):
        state={"articles":[rss_record(i,REQUIRED_BEATS[i%len(REQUIRED_BEATS)])
                           for i in range(12)]}
        h=audit(state,rss_report(),{"leads":[discovery_lead(1)]},
                broad_discovery(),ferc_report={"status":"degraded"},
                now=NOW)
        self.assertEqual(h["status"],"degraded")
        self.assertEqual(h["timestamped_editorial_leads_24h"],12)
        self.assertTrue(any("FERC primary newsroom" in w for w in h["warnings"]))

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
