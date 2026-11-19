"""File locking on local news metadata state."""
import tempfile
import unittest
from pathlib import Path
from portable_lock import lock_exclusive_nonblocking


class PortableLockTests(unittest.TestCase):
    def test_second_writer_denied_until_first_closes(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"worker.lock"
            with path.open("a+") as first:
                lock_exclusive_nonblocking(first)
                with path.open("a+") as second:
                    with self.assertRaises(BlockingIOError):
                        lock_exclusive_nonblocking(second)
            with path.open("a+") as third:
                lock_exclusive_nonblocking(third)

    def test_windows_and_posix_paths_exist(self):
        src=(Path(__file__).resolve().parents[1]/"portable_lock.py").read_text()
        self.assertIn('os.name == "nt"',src)
        self.assertIn("msvcrt.locking(",src)
        self.assertIn("fcntl.flock(",src)


if __name__ == "__main__":
    unittest.main()
