"""Require real Windows-runner CI for the free local news collector."""
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


class WindowsLocalCI(unittest.TestCase):
    def test_task_installer_is_explicit_opt_in_and_one_instance(self):
        src=(ROOT/"deploy/windows/install-news-task.ps1").read_text()
        self.assertIn("PREVIEW ONLY",src)
        self.assertIn("[switch]$Install",src)
        self.assertIn("[switch]$Replace",src)
        self.assertIn("[switch]$Remove",src)
        self.assertIn("New-ScheduledTaskTrigger -AtLogOn",src)
        self.assertIn("New-ScheduledTaskPrincipal -UserId $User -LogonType Interactive",src)
        self.assertIn("-MultipleInstances IgnoreNew",src)
        self.assertIn("-RestartCount 99",src)
        self.assertIn("-ExecutionTimeLimit (New-TimeSpan -Seconds 0)",src)
        self.assertIn("if (-not $Install)",src)
        self.assertNotIn("NEWSLETTER_ALLOW_TEST_SEND",src)

    def test_windows_job_and_nonpaid_host_assumption(self):
        src=(ROOT/".github/workflows/collector-daemon-ci.yml").read_text()
        self.assertIn("windows-local-smoke:",src)
        self.assertIn("runs-on: windows-latest",src)
        self.assertIn('python -m pip install tzdata',src)
        self.assertIn('test_portable_lock.py',src)
        self.assertIn('test_render_worker.py',src)
        self.assertNotIn("NEWSLETTER_ALLOW_TEST_SEND",src)


if __name__ == "__main__":
    unittest.main()
