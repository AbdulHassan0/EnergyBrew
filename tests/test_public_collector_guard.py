"""Public collector may persist only safe, canonical source metadata."""
import json
import tempfile
import unittest
from pathlib import Path

from public_collector_guard import SafetyError, ensure_sources_public, validate_all, validate_records


class PublicGuardTests(unittest.TestCase):
    def test_allowlisted_sources_are_public_https(self):
        ensure_sources_public()

    def test_reject_publisher_excerpts(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"articles.json"
            path.write_text(json.dumps({"articles":[{
                "title":"Natural gas supply story","url":"https://example.org/story",
                "summary_excerpt":"Publisher article snippet",}],"runs":[]}))
            with self.assertRaises(SafetyError):
                validate_records(path,"articles")

    def test_reject_credentials_and_unsafe_urls(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"articles.json"
            p.write_text(json.dumps({"articles":[{"title":"Energy market source report",
                "url":"https://username:pass@example.org/story"}]}))
            with self.assertRaises(SafetyError):
                validate_records(p,"articles")

    def test_metadata_only_passes(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"articles.json"
            p.write_text(json.dumps({"articles":[{"title":"Energy source-linked story",
                "url":"https://example.org/story"}]}))
            self.assertEqual(validate_records(p,"articles"),1)
            self.assertEqual(validate_all(p,Path(d)/"none.json",Path(d)/"none2.json")["publisher_metadata"],1)

    def test_empty_collector_state_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(SafetyError):
                validate_all(Path(d)/"a",Path(d)/"b",Path(d)/"c")


if __name__=="__main__":
    unittest.main()
