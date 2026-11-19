"""Persistent morning job uses GAL daemon history without modifying it."""
import json
import tempfile
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path

from morning_host_runner import refresh_rss_safely, run_morning

CUTOFF=datetime(2026,11,19,12,30,tzinfo=timezone.utc)
NOW=CUTOFF+timedelta(minutes=8)
RSS=b"""<rss><channel><item><title>Henry Hub natural gas supply prices rise</title>
<link>https://example.com/news/henry-hub</link>
<pubDate>Thu, 19 Nov 2026 12:15:00 GMT</pubDate>
</item></channel></rss>"""

def healthy_gal(root):
    records=[{"run_utc":(CUTOFF-timedelta(minutes=i)).isoformat(),"status":"ok"}
             for i in range(0,361,10)]
    (root/"discovery.json").write_text(json.dumps({"leads":[],"gal_runs":records}))

class MorningHostTests(unittest.TestCase):
    def test_once_at_0638_prepares_without_email_or_mutating_gal_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            healthy_gal(root)
            before=(root/"discovery.json").read_bytes()
            result=run_morning(root,now=NOW,fetcher=lambda _: (RSS,200))
            self.assertEqual(result["status"],"ready_for_editor_review")
            self.assertTrue(result["frozen"])
            self.assertEqual((root/"discovery.json").read_bytes(),before)
            payload=json.loads((root/"morning/research_2026-11-19.json").read_text())
            self.assertEqual(payload["publication_status"],"research_only_not_approved_not_sent")
            self.assertEqual(len(payload["research_desk"]["stories"]),1)

    def test_missing_gal_history_blocks_snapshot_but_records_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            result=run_morning(root,now=NOW,fetcher=lambda _:(RSS,200))
            self.assertEqual(result["status"],"blocked_collection_readiness")
            self.assertIn("overnight_gdelt_sampling_below_minimum",result["blocking_issues"])
            self.assertFalse((root/"morning/research_2026-11-19.json").exists())
            self.assertTrue((root/"morning/readiness_2026-11-19.json").exists())

    def test_unhealthy_last_rss_attempt_forces_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            healthy_gal(root)
            result=run_morning(root,now=NOW,fetcher=lambda _:(b"<rss",200))
            self.assertEqual(result["status"],"blocked_collection_readiness")
            self.assertIn("final_publisher_refresh_critical",result["blocking_issues"])

    def test_slow_0638_refresh_finishing_after_0650_cannot_freeze(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            healthy_gal(root)
            outcome=run_morning(
                root, now=NOW, fetcher=lambda _:(RSS,200),
                completion_clock=lambda: CUTOFF+timedelta(minutes=22))
            self.assertEqual(outcome["status"], "blocked_collection_readiness")
            self.assertIn("host_research_completed_after_0650",
                          outcome["blocking_issues"])
            self.assertFalse((root/"morning/research_2026-11-19.json").exists())
            audit=json.loads((root/"morning/readiness_2026-11-19.json").read_text())
            self.assertEqual(audit["status"],"blocked_collection_readiness")

    def test_tz_naive_completion_clock_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            healthy_gal(root)
            with self.assertRaises(ValueError):
                run_morning(root,now=NOW,fetcher=lambda _:(RSS,200),
                            completion_clock=lambda:datetime(2026,11,19,12,40))

    def test_existing_rss_metadata_not_overwritten_if_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            state=root/"articles.json"
            state.write_text("broken")
            with self.assertRaises(ValueError):
                refresh_rss_safely(state,root/"out",now=NOW,fetcher=lambda _:(RSS,200))
            self.assertEqual(state.read_text(),"broken")

    def test_outside_preparation_window_does_not_poll(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls=[]
            with self.assertRaises(RuntimeError):
                run_morning(Path(tmp),now=CUTOFF+timedelta(minutes=30),
                            fetcher=lambda u:(calls.append(u),200))
            self.assertEqual(calls,[])

    def test_second_run_cannot_rewrite_frozen_daily_candidate_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            healthy_gal(root)
            run_morning(root,now=NOW,fetcher=lambda _:(RSS,200))
            before=(root/"morning/research_2026-11-19.json").read_text()
            with self.assertRaisesRegex(ValueError,"Immutable"):
                run_morning(root,now=NOW+timedelta(minutes=2),
                            fetcher=lambda _:(RSS.replace(b"prices rise",b"prices fall"),200))
            self.assertEqual((root/"morning/research_2026-11-19.json").read_text(),before)

if __name__=="__main__":
    unittest.main()
