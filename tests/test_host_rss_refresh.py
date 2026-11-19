"""Offline host deployment regression tests; no network or email."""
import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from collector import SOURCES
from host_rss_refresh import run_refresh

NOW = datetime(2026, 11, 19, 11, 35, tzinfo=timezone.utc)
ROOT = Path(__file__).resolve().parents[1]
UNITS = ROOT / "deploy" / "systemd"


def rss_response(url):
    slug = hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
    return (f"<rss><channel><item><title>LNG export project expansion approved</title>"
            f"<link>https://example.org/energy/{slug}</link>"
            f"<pubDate>Thu, 19 Nov 2026 11:25:00 GMT</pubDate>"
            f"</item></channel></rss>").encode(), 200


class HostCollectorTests(unittest.TestCase):
    def test_preflight_refresh_writes_safe_public_metadata_without_email(self):
        with tempfile.TemporaryDirectory() as directory:
            result = run_refresh(directory, now=NOW, fetcher=rss_response)
            self.assertEqual(result["status"], "healthy")
            self.assertEqual(result["feeds_connected"], len(SOURCES))
            state = json.loads((Path(directory) / "articles.json").read_text())
            self.assertEqual(len(state["articles"]), len(SOURCES))
            self.assertFalse((Path(directory) / "articles.json.morning-stage").exists())
            self.assertTrue(all("summary_excerpt" not in row for row in state["articles"]))
            self.assertIn("no_email", result["publication"])

    def test_critical_source_failure_is_visible_and_state_keeps_history(self):
        with tempfile.TemporaryDirectory() as directory:
            first = run_refresh(directory, now=NOW, fetcher=rss_response)
            self.assertEqual(first["status"], "healthy")
            before = json.loads((Path(directory) / "articles.json").read_text())
            second = run_refresh(directory, now=NOW, fetcher=lambda _: (_ for _ in ()).throw(OSError("offline")))
            self.assertEqual(second["status"], "critical")
            after = json.loads((Path(directory) / "articles.json").read_text())
            self.assertEqual(len(after["articles"]), len(before["articles"]))
            self.assertFalse((Path(directory) / "articles.json.morning-stage").exists())

    def test_naive_clock_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                run_refresh(directory, now=datetime(2026, 11, 19, 5, 35))

    def test_host_timers_use_central_dst_without_delayed_catchup(self):
        cases = {
            "energybrew-rss-refresh.timer": ("05:35:00", "06:24:00"),
            "energybrew-preflight.timer": ("05:45:00",),
            "energybrew-morning.timer": ("06:38:00",),
        }
        for name, clock_times in cases.items():
            with self.subTest(name=name):
                body = (UNITS / name).read_text()
                self.assertIn("Persistent=false", body)
                self.assertIn("RandomizedDelaySec=0", body)
                for t in clock_times:
                    self.assertIn(t + " America/Chicago", body)
                self.assertEqual(body.count("OnCalendar="), len(clock_times))
                self.assertNotIn("ExecStart=", body)

    def test_host_units_share_one_volume_and_do_not_send_email(self):
        units = [
            "energybrew-gal.service", "energybrew-rss-refresh.service",
            "energybrew-preflight.service", "energybrew-morning.service",
        ]
        for name in units:
            with self.subTest(name=name):
                body = (UNITS / name).read_text()
                self.assertIn("source=/opt/energybrew/energybrew-state,target=/data", body)
                self.assertIn("AssertPathIsDirectory=/opt/energybrew/energybrew-state", body)
                self.assertIn("NO EMAIL", body)
                self.assertNotIn("newsletter_delivery.py", body)
                self.assertNotIn("newsletter.py", body)
        self.assertIn("Restart=on-failure", (UNITS / "energybrew-gal.service").read_text())


if __name__ == "__main__":
    unittest.main()
