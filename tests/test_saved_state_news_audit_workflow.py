"""Read-only free pilot audit must not pretend to be a live collector."""
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]/".github"/"workflows"


class SavedStateAuditWorkflowTests(unittest.TestCase):
    def test_has_read_only_permissions_and_no_live_calls(self):
        text=(ROOT/"saved-state-news-audit.yml").read_text(encoding="utf-8")
        self.assertIn("contents: read",text)
        self.assertNotIn("contents: write",text)
        self.assertIn("state/discovery.json",text)
        self.assertIn("source_gap_audit.py --rss",text)
        self.assertIn("ops_metrics.py --rss",text)
        self.assertIn("NOT live collection",text)
        for prohibited in ("git push", "newsletter_delivery.py",
                           "python collector.py", "python gal.py",
                           "python discovery.py", "python press_releases.py"):
            self.assertNotIn(prohibited,text)
        self.assertIn("schedule:",text)
        self.assertIn("workflow_dispatch:",text)


if __name__=="__main__":
    unittest.main()
