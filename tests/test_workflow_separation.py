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

    def test_shared_writer_concurrency_queues_instead_of_replacing_pending_polls(self):
        writers=("frequent-gal.yml","hourly-discovery.yml",
                 "live-collector.yml","precutoff-rss.yml")
        for name in writers:
            with self.subTest(name=name):
                flow=workflow(name)
                self.assertIn("group: energybrew-live-collector",flow)
                self.assertIn("cancel-in-progress: false",flow)
                self.assertIn("queue: max",flow)
                self.assertIn("git push origin HEAD:collector-state",flow)
        # A read-only preparation consumes no write lock. Branch fetches
        # are atomic; stalled morning research must not starve polling.
        readonly=workflow("morning-news-readiness.yml")
        self.assertNotIn("group: energybrew-live-collector",readonly)
        self.assertNotIn("git push origin HEAD:collector-state",readonly)

    def test_precutoff_scan_does_not_waste_narrow_window_on_tests(self):
        flow=workflow("precutoff-rss.yml")
        self.assertNotIn("python -m unittest",flow)
        self.assertIn("python collector.py --state state/articles.json",flow)
        self.assertIn("public_collector_guard.py --sanitize-legacy",flow)
        self.assertIn("queue: max",flow)
        self.assertLess(flow.index("python collector.py --state"),
                        flow.index("public_collector_guard.py --sanitize-legacy"))
        self.assertIn("steps.rss.outcome == 'success'",flow)

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

    def test_full_collector_owns_heavy_gap_diagnostics(self):
        full=workflow("live-collector.yml")
        self.assertIn("python source_gap_audit.py --",full)
        self.assertIn("python ops_metrics.py --",full)
        self.assertIn("state/source_gap_latest.json",full)
        for path in ("live-collector.yml","frequent-gal.yml","hourly-discovery.yml"):
            self.assertNotIn("newsletter_delivery.py",workflow(path))
            self.assertIn("public_collector_guard.py",workflow(path))

    def test_frequent_gal_sampling_has_no_heavy_reporting_before_persistence(self):
        for name in ("frequent-gal.yml","hourly-discovery.yml"):
            with self.subTest(name=name):
                yml=workflow(name)
                self.assertIn("python gal.py --state state/discovery.json",yml)
                self.assertIn("git push origin HEAD:collector-state",yml)
                self.assertNotIn("python research_desk.py",yml)
                self.assertNotIn("python ops_metrics.py",yml)
                self.assertNotIn("python source_gap_audit.py",yml)
                self.assertNotIn("python newsroom_health.py",yml)
                self.assertLess(yml.index("python gal.py --state state/discovery.json"),
                                yml.index("public_collector_guard.py --sanitize-legacy"))
                self.assertLess(yml.index("public_collector_guard.py --sanitize-legacy"),
                                yml.index("git push origin HEAD:collector-state"))
                self.assertIn("steps.metadata_guard.outcome == 'success'",yml)

    def test_final_morning_preparation_never_polls_after_cutoff(self):
        s=workflow("morning-news-readiness.yml")
        self.assertIn("python morning_readiness.py --rss",s)
        self.assertNotIn("python collector.py --",s)
        self.assertNotIn("python gal.py --",s)
        self.assertIn("saved source state only",s)

    def test_rolling_gal_samplers_do_not_block_on_pre_poll_tests(self):
        offline=workflow("news-logic-ci.yml")
        self.assertIn('python -m unittest discover -s tests -v',offline)
        for filename in ("frequent-gal.yml","hourly-discovery.yml"):
            with self.subTest(filename=filename):
                sampler=workflow(filename)
                self.assertNotIn('python -m unittest',sampler)
                self.assertIn('python gal.py --state state/discovery.json',sampler)
                self.assertIn('public_collector_guard.py --sanitize-legacy',sampler)
                # Always restore retained state first; never poll with an
                # empty history when a prior branch exists.
                self.assertLess(sampler.index("git fetch --no-tags origin collector-state"),
                                sampler.index("python gal.py --state state/discovery.json"))
                # The metadata guard must still run before state persistence.
                self.assertLess(sampler.index('public_collector_guard.py --sanitize-legacy'),
                                sampler.index('git push origin HEAD:collector-state'))

    def test_morning_workflows_export_evidence_without_inventing_summary(self):
        research=workflow("morning-news-readiness.yml")
        editorial=workflow("morning-editorial.yml")
        self.assertIn("python morning_evidence.py --rss",research)
        self.assertIn("morning_evidence_brief_template.json",research.replace(
            "morning_evidence.json","morning_evidence_brief_template.json"))
        self.assertIn("steps.evidence.outcome != 'success'",research)
        self.assertIn("python morning_evidence.py --rss",editorial)
        self.assertIn("MORNING_SOURCE_EVIDENCE.json",editorial)
        self.assertNotIn("newsletter_delivery.py",research)
        self.assertNotIn("newsletter_delivery.py",editorial)

    def test_editorial_pipeline_rebuilds_cutoff_desk_from_source_history(self):
        editorial=workflow("morning-editorial.yml")
        self.assertIn("python cutoff_desk.py --rss latest-state/articles.json", editorial)
        self.assertIn("latest-state/cutoff_desk.json", editorial)
        self.assertIn("MORNING_CUTOFF_DESK.json", editorial)
        self.assertNotIn("git show FETCH_HEAD:state/desk_latest.json", editorial)
        self.assertNotIn("--desk latest-state/desk_latest.json", editorial)
        self.assertIn("post_cutoff = now.hour > 6", editorial)
        self.assertLess(editorial.index("python cutoff_desk.py --rss"),
                        editorial.index("python newsletter.py prepare --desk"))
        self.assertNotIn("newsletter_delivery.py", editorial)

    def test_pilot_editorial_action_renders_complete_email_without_sending(self):
        flow=workflow("morning-editorial.yml")
        self.assertIn("python pilot_audit.py --pilot",flow)
        self.assertIn("python brief_compiler.py --desk",flow)
        self.assertIn('newsletter/briefs/**',flow)
        self.assertIn("COMPILED_PILOT.json",flow)
        self.assertIn("PILOT_QUALITY_REPORT.json",flow)
        self.assertIn('cron: "45 11,12 * * 1-5"',flow)
        self.assertIn('40 <= now.minute < 55',flow)
        self.assertIn("newsletter/pilots/**",flow)
        self.assertIn("python newsletter.py pilot-preview --edition",flow)
        self.assertIn("PILOT_email_preview.html",flow)
        self.assertNotIn("python newsletter.py preview --draft",flow)
        self.assertNotIn("newsletter_delivery.py",flow)
        self.assertIn("no fake summaries",flow)

    def test_no_collection_guard_is_removed_to_silence_notifications(self):
        s=workflow("live-collector.yml")
        self.assertIn("public_collector_guard.py --sanitize-legacy",s)
        self.assertIn("git push origin HEAD:collector-state",s)

if __name__=="__main__":
    unittest.main()
