"""Offline checks for Render's single-disk morning scheduling and blueprint."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from render_worker import JOBS, read_state, scheduler_tick, worker_loop

ROOT = Path(__file__).resolve().parents[1]
ZONE = ZoneInfo("America/Chicago")


def local_time(hour, minute, *, day=19):
    return datetime(2026, 11, day, hour, minute, tzinfo=ZONE).astimezone(timezone.utc)


class RenderWorkerTests(unittest.TestCase):
    def test_blueprint_contains_one_disk_backed_worker_not_cron(self):
        blueprint = (ROOT / "render.yaml").read_text()
        self.assertIn("type: worker", blueprint)
        self.assertNotIn("type: cron", blueprint)
        self.assertEqual(blueprint.count("  - type: worker"), 1)
        self.assertIn("mountPath: /data", blueprint)
        self.assertIn("dockerfilePath: ./Dockerfile.render", blueprint)
        self.assertIn("numInstances: 1", blueprint)
        self.assertIn("autoDeployTrigger: checksPass", blueprint)
        self.assertNotIn("email", blueprint.split("services:")[1].lower())
        self.assertIn('ENTRYPOINT ["python", "render_worker.py"]',
                      (ROOT / "Dockerfile.render").read_text())

    def test_jobs_are_ordered_and_before_seven_am(self):
        self.assertEqual([x.name for x in JOBS], [
            "rss_early", "research_preview", "rss_pre_cutoff", "research_final"])
        self.assertLess(JOBS[-1].deadline().hour, 7)

    def test_due_job_run_once_even_after_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            execute = lambda n: (calls.append(n) or ("ok", "tested"))
            first = scheduler_tick(directory, now=local_time(5, 35), execute=execute)
            second = scheduler_tick(directory, now=local_time(5, 36), execute=execute)
            self.assertEqual(calls, ["rss_early"])
            self.assertEqual(first["jobs"]["rss_early"]["status"], "ok")
            self.assertEqual(second["dispatched"], [])

    def test_missed_window_never_executed_or_faked_as_success(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            report = scheduler_tick(directory, now=local_time(7, 5),
                                    execute=lambda n: (calls.append(n) or ("ok", "no")))
            self.assertEqual(calls, [])
            self.assertEqual(set(v["status"] for v in report["jobs"].values()),
                             {"missed"})

    def test_blocked_final_is_terminal_not_silent_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            def run(name):
                calls.append(name)
                return "blocked", "overnight_gdelt_sampling_below_minimum"
            first = scheduler_tick(directory, now=local_time(6, 38), execute=run)
            second = scheduler_tick(directory, now=local_time(6, 40), execute=run)
            self.assertEqual(first["jobs"]["research_final"]["status"], "blocked")
            self.assertEqual(second["jobs"]["research_final"]["status"], "blocked")
            self.assertEqual(calls.count("research_final"), 1)

    def test_one_transient_retry_then_durable_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            def fail(name):
                calls.append(name)
                return "failed", "publisher_unavailable"
            a = scheduler_tick(directory, now=local_time(5, 35), execute=fail)
            self.assertEqual(a["jobs"]["rss_early"]["status"], "retry_pending")
            b = scheduler_tick(directory, now=local_time(5, 35), execute=fail)
            self.assertEqual(len(calls), 1)
            c = scheduler_tick(directory, now=local_time(5, 37), execute=fail)
            self.assertEqual(c["jobs"]["rss_early"]["status"], "failed")
            self.assertEqual(len(calls), 2)

    def test_retry_pending_on_restart_uses_persistent_ledger(self):
        with tempfile.TemporaryDirectory() as directory:
            scheduler_tick(directory, now=local_time(5, 35),
                           execute=lambda _: ("failed", "offline"))
            ledger = read_state(Path(directory) / "render_schedule.json")
            self.assertEqual(ledger["dates"]["2026-11-19"]["rss_early"]["attempts"], 1)
            report = scheduler_tick(directory, now=local_time(5, 38),
                                    execute=lambda _: ("ok", "recovered"))
            self.assertEqual(report["jobs"]["rss_early"]["status"], "ok")
            self.assertEqual(report["jobs"]["rss_early"]["attempts"], 2)

    def test_naive_clock_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                scheduler_tick(directory, now=datetime(2026, 11, 19, 5, 35))

    def test_dst_schedule_follows_local_time_not_fixed_utc(self):
        with tempfile.TemporaryDirectory() as directory:
            winter = datetime(2026, 11, 19, 5, 35, tzinfo=ZONE)
            summer = datetime(2026, 7, 19, 5, 35, tzinfo=ZONE)
            self.assertNotEqual(winter.utcoffset(), summer.utcoffset())
            self.assertEqual(winter.astimezone(timezone.utc).hour, 11)
            self.assertEqual(summer.astimezone(timezone.utc).hour, 10)

    def test_worker_fails_if_gal_thread_exits(self):
        with tempfile.TemporaryDirectory() as directory:
            def return_immediately(*args, **kwargs):
                return
            with self.assertRaisesRegex(RuntimeError, "GAL collector"):
                # Force the first tick to permit gal thread to end.
                worker_loop(directory, gal_runner=return_immediately,
                            now_fn=lambda: local_time(7, 10),
                            sleep=lambda seconds: None, max_iterations=100)

    def test_no_pdf_or_newsletter_delivery_dependencies_in_image(self):
        docker = (ROOT / "Dockerfile.render").read_text()
        self.assertIn("python:3.12-slim", docker)
        self.assertIn("USER energybrew", docker)
        self.assertNotIn("npm ", docker)
        self.assertNotIn("newsletter_delivery", (ROOT / "render_worker.py").read_text())


if __name__ == "__main__":
    unittest.main()
