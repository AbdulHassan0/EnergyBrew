"""Editorial QA: collector links cannot become a newsletter without human approval."""
import copy
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from newsletter import (
    EditorialError, archive, date_only, render_html, render_text, research_queue,
    validate_approved, valid_url, TOPICS,
)
from newsletter_delivery import deliver_test, prepare_message

BODY = ("The briefing summarizes confirmed facts drawn from the cited original publisher "
        "material. Every number, date, organization, and market implication should be checked "
        "by the editor against the original article before approving this issue.")
WHY = ("This development could affect future energy supply and demand decisions, "
       "which is why the editor selected it for the morning brief.")


def example_approved(day="2026-11-17"):
    return {
        "schema_version": 1,
        "edition_date": day,
        "status": "approved",
        "headline": "Your daily shot of energy.",
        "intro": "Four energy developments to follow with your morning coffee.",
        "approval": {
            "editor": "Example human editor",
            "approved_at_utc": "2026-11-17T12:00:00+00:00",
            "edition_fact_checked": True,
            "distribution_rights_checked": True,
        },
        "stories": [{
            "title": f"Story number {i} about energy infrastructure",
            "source_url": f"https://example.org/energy/{i}",
            "publisher": "Example Publisher",
            "section": ("Natural Gas" if i % 2 else "Power & Electricity"),
            "source_date": "2026-11-17",
            "summary": BODY,
            "why_it_matters": WHY,
            "fact_check_evidence_urls": [f"https://example.org/energy/{i}"],
            "original_source_checked": True,
            "publisher_date_checked": True,
            "facts_checked": True,
            "summary_rights_checked": True,
            "verification_notes": "Editor reviewed original source and checked claims; sample for unit test.",
        } for i in range(1, 5)]
    }


class NewsletterTests(unittest.TestCase):
    def test_draft_only_from_real_desk_links(self):
        desk = {"generated_utc": "2026-11-18T13:00:00Z", "stories": [
            {"title": "Actual sample original headline", "url": "https://eia.gov/news/1",
             "category": "Natural Gas", "source": "EIA", "origin": "official_rss"},
            {"title": "Duplicate version", "url": "https://eia.gov/news/1", "origin": "official_rss"},
            {"title": "Malformed link", "url": "javascript:alert(1)", "origin": "global_discovery"},
        ]}
        queue = research_queue(desk, edition_date="2026-11-18", now=datetime(2026,11,18,20,0,tzinfo=timezone.utc))
        self.assertEqual(len(queue["stories"]), 1)
        self.assertEqual(queue["status"], "draft")
        self.assertEqual(queue["stories"][0]["summary"], "")
        self.assertFalse(queue["stories"][0]["facts_checked"])
        self.assertFalse(queue["stories"][0]["original_source_checked"])
        with self.assertRaises(EditorialError):
            validate_approved(queue)

    def test_newsletter_preserves_all_six_research_beats(self):
        from research_desk import CATEGORY_ORDER
        self.assertEqual(TOPICS, CATEGORY_ORDER)
        desk = {"generated_utc": "2026-11-19T12:40:00Z", "stories": [
            {"title": f"Relevant {beat} market development today",
             "url": f"https://example.org/energy/{i}", "category": beat,
             "source": "Research publisher", "origin": "official_rss"}
            for i, beat in enumerate(CATEGORY_ORDER)
        ]}
        queue = research_queue(desk, now=datetime(2026,11,19,13,0,tzinfo=timezone.utc))
        self.assertEqual([row["section"] for row in queue["stories"]],
                         list(CATEGORY_ORDER))

    def test_unrecognized_topic_does_not_masquerade_as_oil(self):
        desk = {"generated_utc": "2026-11-19T12:40:00Z", "stories": [
            {"title": "Unknown source message with energy words",
             "url": "https://example.org/energy/1", "category": "Unexpected"}
        ]}
        queue = research_queue(desk, now=datetime(2026,11,19,13,0,tzinfo=timezone.utc))
        self.assertEqual(queue["stories"], [])

    def test_default_draft_respects_maximum_eight_story_approval_rule(self):
        desk={"generated_utc":"2026-11-19T12:40:00Z","stories":[
            {"title":f"Natural gas pipeline contract expansion announcement {i}",
             "url":f"https://example.org/natural-gas/{i}",
             "category":"Natural Gas","source":"Energy publisher"} for i in range(15)]}
        queue=research_queue(desk,now=datetime(2026,11,19,13,0,tzinfo=timezone.utc))
        self.assertEqual(len(queue["stories"]),8)
        queue2=research_queue(desk,limit=99,
                              now=datetime(2026,11,19,13,0,tzinfo=timezone.utc))
        self.assertEqual(len(queue2["stories"]),8)

    def test_invalid_draft_story_limit_is_refused(self):
        desk={"generated_utc":"2026-11-19T12:40:00Z","stories":[]}
        for limit in (0,-1,True,"8"):
            with self.subTest(limit=limit),self.assertRaises(EditorialError):
                research_queue(desk,limit=limit,
                               now=datetime(2026,11,19,13,0,tzinfo=timezone.utc))

    def test_reject_stale_snapshot(self):
        with self.assertRaises(EditorialError):
            research_queue({"generated_utc": "2026-11-10T00:00:00Z", "stories": []},
                           now=datetime(2026,11,18,20,0,tzinfo=timezone.utc))

    def test_exclude_non_latin_titles(self):
        desk = {"generated_utc":"2026-11-18T19:00:00Z", "stories":[
            {"title":"Thai oil ราคาน้ำมันโลกดิ่งหนัก", "url":"https://example.com/thai", "category":"Oil & Energy"},
            {"title":"English energy industry briefing", "url":"https://example.com/english", "category":"Oil & Energy"}]}
        queue = research_queue(desk, now=datetime(2026,11,18,20,0,tzinfo=timezone.utc))
        self.assertEqual(len(queue["stories"]), 1)
        self.assertIn("English energy", queue["stories"][0]["title"])

    def test_only_https_and_no_credentials(self):
        self.assertFalse(valid_url("http://example.com/story"))
        self.assertFalse(valid_url("https://x:y@example.com/story"))
        self.assertFalse(valid_url("javascript:alert(1)"))
        self.assertTrue(valid_url("https://example.com/story"))

    def test_dates_are_strict(self):
        self.assertFalse(date_only("2026-02-30"))
        self.assertFalse(date_only("2026-11-18T07:00:00"))
        self.assertTrue(date_only("2026-11-18"))

    def test_approved_fixture_passes_strict_gate(self):
        issue = example_approved()
        self.assertEqual(validate_approved(issue), issue)
        self.assertIn("Why it matters", render_html(issue))
        self.assertIn("ENERGYBREW", render_text(issue))

    def test_missing_story_approval_or_evidence_fails(self):
        for name, value in [
            ("facts_checked", False),
            ("publisher_date_checked", False),
            ("summary_rights_checked", False),
            ("source_date", ""),
            ("fact_check_evidence_urls", []),
            ("verification_notes", ""),
        ]:
            issue = example_approved()
            issue["stories"][0][name] = value
            with self.subTest(name=name), self.assertRaises(EditorialError):
                validate_approved(issue)

    def test_missing_final_approval_fails(self):
        issue = example_approved()
        issue["approval"]["edition_fact_checked"] = False
        with self.assertRaises(EditorialError):
            validate_approved(issue)
        issue = example_approved()
        issue["status"] = "draft"
        with self.assertRaises(EditorialError):
            validate_approved(issue)

    def test_duplicate_sources_fail(self):
        issue = example_approved()
        issue["stories"][1]["source_url"] = issue["stories"][0]["source_url"]
        with self.assertRaises(EditorialError):
            validate_approved(issue)

    def test_no_publisher_content_html_injection(self):
        issue = example_approved()
        issue["stories"][0]["title"] = "Energy sector update <script>alert(1)</script> unsafe markup"
        email = render_html(issue)
        self.assertNotIn("<script>", email)
        self.assertIn("&lt;script&gt;", email)

    def test_approved_editions_only_archived(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            editions = root / "editions"
            editions.mkdir()
            pending = example_approved()
            pending["status"] = "draft"
            (editions / "2026-11-16.json").write_text(json.dumps(pending))
            result = archive(editions, root / "site", root / "email")
            self.assertEqual(result, 0)
            self.assertFalse((root / "email/newsletter_email.html").exists())
            self.assertIn("No approved issues yet", (root / "site/index.html").read_text())
            approved = example_approved()
            (editions / "2026-11-17.json").write_text(json.dumps(approved))
            result = archive(editions, root / "site", root / "email")
            self.assertEqual(result, 1)
            self.assertTrue((root / "site/2026-11-17.html").exists())
            self.assertTrue((root / "email/newsletter_email.html").exists())

    def test_invalid_approved_file_blocks_archive(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            editions = root / "editions"
            editions.mkdir()
            approved = example_approved()
            approved["stories"][0]["summary"] = "Unverified"
            (editions / "2026-11-17.json").write_text(json.dumps(approved))
            with self.assertRaises(EditorialError):
                archive(editions, root / "site", root / "email")

    def test_test_email_requires_explicit_opt_in(self):
        with self.assertRaises(EditorialError):
            deliver_test(example_approved(), env={})
        message = prepare_message(example_approved(), "sender@example.com", "recipient@example.com")
        self.assertEqual(message["To"], "recipient@example.com")
        self.assertIn("EnergyBrew", message["Subject"])
        with self.assertRaises(EditorialError):
            prepare_message(example_approved(), "sender@example.com", "a@example.com,b@example.com")


if __name__ == "__main__":
    unittest.main()
