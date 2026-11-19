"""Pilot editorial quality without fake approvals, backfilled clocks or email."""
import copy
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from pilot_audit import audit_pilot, write_report
from newsletter import EditorialError, TOPICS

DAY="2026-11-19"


def fixture():
    stories=[]
    for i,beat in enumerate(TOPICS):
        stories.append({
            "section":beat,"publisher":"Publisher "+str(i),
            "source_date":"2026-11-18",
            "source_url":"https://publisher"+str(i)+".com/news/"+str(i),
            "title":"Energy development changes investment outlook for "+beat,
            "summary":("An energy company announced a new infrastructure development this week. "
                       "The original publisher describes the scope of work and the affected "
                       "markets, with the next regulatory milestone still ahead."),
            "why_it_matters":("New energy capacity could affect fuel flows, power reliability "
                              "and future commercial opportunities."),
        })
    return {"status":"pilot","edition_date":DAY,
            "intro":"Good morning. Here are the key energy updates.",
            "stories":stories}


class AuditTests(unittest.TestCase):
    def test_complete_six_beat_pilot_passes_copy_gate(self):
        r=audit_pilot(fixture())
        self.assertEqual(r["status"],"pilot_copy_ready")
        self.assertTrue(r["six_beats_present"])
        self.assertEqual(r["cutoff_collection_evidence"],"not_established")
        self.assertEqual(r["newsletter_delivery"],"disabled")

    def test_four_category_issue_is_blocked(self):
        f=fixture()
        for i in (2,3):
            f["stories"][i]["section"]="Power & Electricity"
        r=audit_pilot(f)
        self.assertEqual(r["status"],"pilot_copy_blocked")
        self.assertFalse(r["six_beats_present"])
        self.assertTrue(any("Six-category" in x for x in r["errors"]))

    def test_publisher_concentration_detected(self):
        f=fixture()
        for i in range(4):
            f["stories"][i]["source_url"]="https://one.example.org/story/"+str(i)
        r=audit_pilot(f)
        self.assertIn("A single publisher supplies more than three of eight stories",
                      r["errors"])

    def test_old_and_future_publication_dates_rejected(self):
        f=fixture()
        f["stories"][0]["source_date"]="2026-11-13"
        f["stories"][1]["source_date"]="2026-11-20"
        r=audit_pilot(f)
        self.assertEqual(len([x for x in r["errors"] if "Source" in x]),2)

    def test_near_duplicate_urls_not_silent(self):
        f=fixture()
        f["stories"][1]["source_url"]=f["stories"][0]["source_url"]+"/"
        r=audit_pilot(f)
        self.assertTrue(any("canonical source" in x for x in r["errors"]))

    def test_pending_placeholder_detected_even_if_wordy(self):
        f=fixture()
        f["stories"][1]["summary"]="Summary pending fact-check. "+f["stories"][1]["summary"]
        r=audit_pilot(f)
        self.assertTrue(any("placeholder" in x for x in r["errors"]))

    def test_unshortlisted_story_is_traced_to_full_gdelt_source_history(self):
        f=fixture()
        # Its actual source was discovered, but the top 32 list omitted it.
        chosen=f["stories"][0]
        lead={"url":chosen["source_url"],
              "gdelt_first_seen_utc":"2026-11-19T10:00:00+00:00",
              "first_collector_observed_utc":"2026-11-19T12:25:00+00:00"}
        result=audit_pilot(f,{"stories":[]},
                           raw_sources={"discovery":[lead]})
        self.assertEqual(result["matched_research_links"],0)
        self.assertEqual(result["matched_saved_source_links"],1)
        self.assertEqual(result["stories"][0]["as_of_cutoff"],"observed_before_cutoff")
        self.assertNotIn(chosen["source_url"],result["links_missing_in_saved_sources"])

    def test_raw_gdelt_provider_timestamp_is_not_local_observation(self):
        f=fixture()
        lead={"url":f["stories"][0]["source_url"],
              "gdelt_first_seen_utc":"2026-11-19T09:00:00+00:00"}
        result=audit_pilot(f,{"stories":[]},raw_sources={"discovery":[lead]})
        self.assertEqual(result["stories"][0]["as_of_cutoff"],"unproven")

    def test_pre_cutoff_observation_is_distinct_from_later_snapshot(self):
        f=fixture()
        earlier="2026-11-19T12:20:00+00:00"
        desk={"generated_utc":"2026-11-19T17:00:00+00:00",
              "stories":[{"url":x["source_url"],
                          "first_collector_observed_utc":earlier}
                         for x in f["stories"]]}
        r=audit_pilot(f,desk)
        self.assertEqual(r["matched_research_links"],6)
        self.assertEqual(r["cutoff_collection_evidence"],"supported")
        self.assertTrue(any("generated after" in w for w in r["warnings"]))
        desk["stories"][0]["first_collector_observed_utc"]="2026-11-19T13:00:00+00:00"
        r=audit_pilot(f,desk)
        self.assertEqual(r["cutoff_collection_evidence"],"not_established")
        self.assertEqual(len(r["source_links_observed_after_cutoff"]),1)

    def test_legacy_collection_timestamp_does_not_become_verified(self):
        f=fixture()
        desk={"stories":[{"url":x["source_url"],"observed_time_utc":
              "2026-11-19T11:00:00+00:00"} for x in f["stories"]]}
        r=audit_pilot(f,desk)
        self.assertEqual(r["matched_research_links"],6)
        self.assertEqual(len(r["source_links_with_unknown_collection_time"]),6)
        self.assertEqual(r["cutoff_collection_evidence"],"not_established")

    def test_report_distinguishes_copy_and_delivery(self):
        r=audit_pilot(fixture())
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"quality.json"
            write_report(r,path)
            self.assertTrue(path.exists())
            text=path.with_suffix(".md").read_text()
            self.assertIn("No automated email",text)
            self.assertIn("cutoff",text.lower())

    def test_draft_cannot_masquerade_as_pilot(self):
        f=fixture()
        f["status"]="approved"
        with self.assertRaises(EditorialError):
            audit_pilot(f)


if __name__=="__main__":
    unittest.main()
