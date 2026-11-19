"""Issuer feed staging guards do not grant verification or distribution rights."""
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from host_release_refresh import run_refresh

NOW=datetime(2026,11,19,13,0,tzinfo=timezone.utc)
RSS=b"""<rss><channel><item><title>US natural gas pipeline expansion approved</title>
<link>https://aggregator.example.com/claim</link>
<source url="https://issuer.example.com/releases/approved">Issuer Inc.</source>
<pubDate>Thu, 19 Nov 2026 12:00:00 GMT</pubDate>
</item></channel></rss>"""


class ReleaseHostTests(unittest.TestCase):
    def test_success_creates_metadata_only_preserved_state(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            result=run_refresh(root,now=NOW,fetcher=lambda _: (RSS,200))
            self.assertEqual(result["status"],"ok")
            self.assertEqual(result["publication"],"never_send_or_autoapprove")
            saved=json.loads((root/"press_releases.json").read_text())
            self.assertEqual(saved["leads"][0]["url"],
                             "https://issuer.example.com/releases/approved")
            self.assertFalse(saved["leads"][0]["named_issuer_verified"])
            self.assertFalse(saved["leads"][0]["published_time_verified"])
            self.assertFalse((root/"press_releases.host-stage.json").exists())

    def test_bad_durable_state_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            state=root/"press_releases.json"
            state.write_text("unreadable json")
            with self.assertRaises(ValueError):
                run_refresh(root,now=NOW,fetcher=lambda _:(RSS,200))
            self.assertEqual(state.read_text(),"unreadable json")

    def test_upstream_failure_is_explicitly_degraded(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            result=run_refresh(root,now=NOW,fetcher=lambda _: (b"",500))
            self.assertEqual(result["status"],"degraded")
            self.assertEqual(result["leads_24h"],0)

    def test_rejects_invalid_local_timestamp(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                run_refresh(temp,now=datetime(2026,11,19,13,0))


if __name__=="__main__":
    unittest.main()
