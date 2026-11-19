"""Persistent morning job uses GAL daemon history without modifying it."""
import json
import tempfile
import unittest
import threading
from unittest.mock import patch
from datetime import datetime,timedelta,timezone
from pathlib import Path

from morning_host_runner import refresh_rss_safely, run_morning, concurrent_first_fetches, recover_abandoned_rss_stage

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
    def test_initial_publisher_fetches_are_bounded_concurrent(self):
        from collector import SOURCES
        seen = set()
        gate = threading.Event()
        all_entered = threading.Event()
        lock = threading.Lock()

        def mocked_http(url):
            with lock:
                seen.add(threading.get_ident())
                if len(seen) >= 3:
                    all_entered.set()
            if not gate.wait(timeout=4):
                raise TimeoutError("Parallel fetch did not release")
            return RSS, 200

        with patch("morning_host_runner.fetch_feed", side_effect=mocked_http):
            pool, fetcher=concurrent_first_fetches(workers=5)
            try:
                self.assertTrue(all_entered.wait(timeout=4))
                gate.set()
                first=fetcher(SOURCES[0][1])
                self.assertEqual(first[1],200)
                self.assertGreaterEqual(len(seen),3)
                self.assertLessEqual(len(seen),5)
            finally:
                gate.set()
                pool.shutdown(wait=True)

    def test_failed_prefetch_is_retried_via_fresh_request(self):
        from collector import SOURCES
        first_url=SOURCES[0][1]
        attempts={}
        def mocked_http(url):
            attempts[url]=attempts.get(url,0)+1
            if url==first_url and attempts[url]==1:
                raise TimeoutError("Temporary publisher timeout")
            return RSS,200
        with patch("morning_host_runner.fetch_feed",side_effect=mocked_http), patch(
                "morning_host_runner.time.sleep",return_value=None):
            pool,fetcher=concurrent_first_fetches(workers=5)
            try:
                with self.assertRaises(TimeoutError):
                    fetcher(first_url)
                self.assertEqual(fetcher(first_url)[1],200)
                self.assertEqual(attempts[first_url],2)
            finally:
                pool.shutdown(wait=True)

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
            draft=json.loads((root/"morning/editorial_draft_2026-11-19.json").read_text())
            self.assertEqual(draft["status"],"draft")
            self.assertFalse(draft["approval"]["edition_fact_checked"])
            self.assertEqual(draft["stories"][0]["summary"],"")
            self.assertFalse(draft["stories"][0]["facts_checked"])
            self.assertTrue(result["private_draft_available"])

    def test_missing_gal_history_blocks_snapshot_but_records_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            result=run_morning(root,now=NOW,fetcher=lambda _:(RSS,200))
            self.assertEqual(result["status"],"blocked_collection_readiness")
            self.assertIn("overnight_gdelt_sampling_below_minimum",result["blocking_issues"])
            self.assertFalse((root/"morning/research_2026-11-19.json").exists())
            self.assertFalse((root/"morning/editorial_draft_2026-11-19.json").exists())
            self.assertTrue((root/"morning/readiness_2026-11-19.json").exists())

    def test_render_0638_uses_pre_cutoff_feed_without_network_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            healthy_gal(root)
            refresh_rss_safely(root/"articles.json",root/"out",now=CUTOFF-timedelta(minutes=6),
                               fetcher=lambda _:(RSS,200))
            before=(root/"articles.json").read_bytes()
            requested=[]
            outcome=run_morning(root,now=NOW,
                                fetcher=lambda url:requested.append(url),
                                refresh_rss=False)
            self.assertEqual(outcome["status"],"ready_for_editor_review")
            self.assertTrue(outcome["frozen"])
            self.assertEqual(requested,[])
            self.assertEqual((root/"articles.json").read_bytes(),before)

    def test_render_missing_pre_cutoff_refresh_blocks_freeze(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            healthy_gal(root)
            refresh_rss_safely(root/"articles.json",root/"out",now=CUTOFF-timedelta(minutes=6),
                               fetcher=lambda _:(RSS,200))
            outcome=run_morning(root,now=NOW,refresh_rss=False,
                 prerequisite_issues=("pre_cutoff_publisher_refresh_not_confirmed",))
            self.assertEqual(outcome["status"],"blocked_collection_readiness")
            self.assertFalse(outcome["frozen"])
            self.assertFalse((root/"morning/research_2026-11-19.json").exists())
            self.assertIn("pre_cutoff_publisher_refresh_not_confirmed",
                          outcome["blocking_issues"])

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

    def test_stale_rss_stage_recovered_without_mutating_committed_history(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            state=root/"articles.json"
            refresh_rss_safely(state,root/"out",now=NOW,
                               fetcher=lambda _:(RSS,200))
            previous=json.loads(state.read_text())
            old_urls={row["url"] for row in previous["articles"]}
            old_runs=len(previous["runs"])
            stale=root/"articles.json.morning-stage"
            stale.write_text("partial power loss")
            refresh_rss_safely(state,root/"out",now=NOW,
                               fetcher=lambda _:(RSS,200))
            updated=json.loads(state.read_text())
            self.assertTrue(old_urls.issubset({row["url"] for row in updated["articles"]}))
            self.assertEqual(len(updated["runs"]),old_runs+1)
            self.assertFalse(stale.exists())

    def test_stale_rss_stage_kept_if_committed_history_is_corrupt(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            state=root/"articles.json"
            stage=root/"articles.json.morning-stage"
            state.write_text("corrupted")
            stage.write_text("uncommitted")
            with self.assertRaises(ValueError):
                recover_abandoned_rss_stage(state)
            self.assertEqual(state.read_text(),"corrupted")
            self.assertTrue(stage.exists())

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
