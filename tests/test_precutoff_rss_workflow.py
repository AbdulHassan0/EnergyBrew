"""Precutoff GitHub RSS collection must be DST-aware and metadata-only."""
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]/".github"/"workflows"

class PrecutoffTests(unittest.TestCase):
    def test_time_gate_and_serialized_state(self):
        s=(ROOT/"precutoff-rss.yml").read_text()
        self.assertIn('cron: "10 11,12 * * *"',s)
        self.assertIn('ZoneInfo("America/Chicago")',s)
        self.assertIn('time(6,5)<=wall<time(6,25)',s)
        self.assertIn('group: energybrew-live-collector',s)
        self.assertIn('git push origin HEAD:collector-state',s)
        self.assertIn('public_collector_guard.py',s)
        self.assertIn("steps.rss.outcome != 'success'",s)

    def test_no_publisher_poll_after_cutoff_or_email(self):
        s=(ROOT/"precutoff-rss.yml").read_text()
        self.assertIn("steps.gate.outputs.active == 'true'",s)
        for prohibited in ('newsletter_delivery.py','smtp','python discovery.py'):
            self.assertNotIn(prohibited,s.lower())

if __name__=="__main__":
    unittest.main()
