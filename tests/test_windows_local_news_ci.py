"""Require real Windows-runner CI for the free local news collector."""
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


class WindowsLocalCI(unittest.TestCase):
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
