"""Stand-alone worker tests: durable state, guard, failure visibility and no burst."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from collector_daemon import sample_once, update_health, run_forever

NOW=datetime(2026,11,18,15,tzinfo=timezone.utc)
FEED=b"""<rss><channel><item><title>Cheniere LNG expansion advances</title>
<link>https://example.com/new-lng-project</link>
<pubDate>Wed, 18 Nov 2026 14:45:00 GMT</pubDate>
</item></channel></rss>"""

class WorkerTests(unittest.TestCase):
    def test_safe_staging_writes_durable_state(self):
        with tempfile.TemporaryDirectory() as d:
            state=Path(d)/"state/discovery.json"
            r=sample_once(state,Path(d)/"out",now=NOW,fetcher=lambda u:(FEED,200))
            self.assertEqual(r["status"],"ok")
            self.assertTrue(state.exists())
            self.assertFalse(state.with_name(state.name+".staging").exists())
            self.assertEqual(len(json.loads(state.read_text())["leads"]),1)

    def test_bad_existing_state_not_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            state=Path(d)/"state.json"
            state.write_text("broken")
            with self.assertRaises(ValueError):
                sample_once(state,Path(d)/"out",now=NOW,fetcher=lambda u:(FEED,200))
            self.assertEqual(state.read_text(),"broken")
            self.assertFalse(state.with_name(state.name+".staging").exists())

    def test_failed_gal_retains_previous_leads_without_fake_success(self):
        with tempfile.TemporaryDirectory() as d:
            state=Path(d)/"state.json"
            sample_once(state,Path(d)/"out",now=NOW,fetcher=lambda u:(FEED,200))
            fail=sample_once(state,Path(d)/"out",now=NOW+timedelta(minutes=5),
                             fetcher=lambda u:(b"<rss",200))
            self.assertEqual(fail["status"],"degraded")
            self.assertEqual(len(json.loads(state.read_text())["leads"]),1)

    def test_health_marks_three_failed_cycles_critical(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"health.json"
            for i in range(3):
                status=update_health(path,{"status":"degraded","error":"upstream offline"},
                                     now=NOW+timedelta(minutes=5*i))
            self.assertEqual(status["status"],"critical")
            self.assertEqual(status["consecutive_failures"],3)
            r=update_health(path,{"status":"ok","new_unique_links":1},now=NOW+timedelta(minutes=20))
            self.assertEqual(r["consecutive_failures"],0)
            self.assertEqual(r["status"],"healthy")

    def test_unsafe_poll_interval_rejected(self):
        with self.assertRaises(ValueError):
            run_forever(Path("/tmp/x"),Path("/tmp/y"),interval_seconds=30)

if __name__=="__main__":
    unittest.main()
