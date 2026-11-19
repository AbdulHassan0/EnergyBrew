"""Fail CI if development edits start live collection or suppress actual outages.

This is a source-level workflow guard, avoiding optional YAML dependencies.
"""
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]/".github"/"workflows"


def workflow(name):
    return (ROOT/name).read_text(encoding="utf-8")


class WorkflowSeparationTests(unittest.TestCase):
    def test_live_collector_has_only_schedule_or_dispatch_triggers(self):
        s=workflow("live-collector.yml")
        self.assertIn("  workflow_dispatch:",s)
        self.assertIn("  schedule:",s)
        self.assertNotIn("\n  push:",s)
        self.assertIn("Mark absence of live source connection as a failure",s)

    def test_all_scheduled_collection_paths_do_not_run_on_code_push(self):
        for filename in ("frequent-gal.yml","hourly-discovery.yml",
                         "morning-news-readiness.yml","scheduler-audit.yml"):
            with self.subTest(filename=filename):
                s=workflow(filename)
                self.assertIn("\n  schedule:",s)
                self.assertNotIn("\n  push:",s)

    def test_regression_ci_is_code_push_only_not_source_poller(self):
        s=workflow("news-logic-ci.yml")
        self.assertIn("\n  push:",s)
        self.assertIn("python -m unittest discover -s tests -v",s)
        self.assertNotIn("python collector.py --",s)
        self.assertNotIn("python gal.py --",s)
        self.assertNotIn("collector-state",s)

    def test_failed_preflight_tests_cannot_cause_secondary_missing_state_error(self):
        s=workflow("live-collector.yml")
        self.assertNotIn("id: metadata_guard\n        if: always()",s)
        self.assertIn("id: metadata_guard",s)
        self.assertIn("if: success() && steps.metadata_guard.outcome == 'success'",s)
        self.assertIn("No successful live RSS response",s)

    def test_free_collection_paths_publish_gap_diagnostics_without_email(self):
        for path in ("live-collector.yml","frequent-gal.yml"):
            s=workflow(path)
            self.assertIn("python source_gap_audit.py --",s)
            self.assertIn("state/source_gap_latest.json",s)
            self.assertNotIn("newsletter_delivery.py",s)
            self.assertIn("public_collector_guard.py",s)

    def test_no_collection_guard_is_removed_to_silence_notifications(self):
        s=workflow("live-collector.yml")
        self.assertIn("public_collector_guard.py --sanitize-legacy",s)
        self.assertIn("git push origin HEAD:collector-state",s)

if __name__=="__main__":
    unittest.main()
