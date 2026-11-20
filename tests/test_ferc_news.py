"""FERC official listing parser and state-safety regression checks (offline)."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ferc_news import SOURCE_NAME, collect, parse_listing

NOW = datetime(2026, 11, 20, 2, 30, tzinfo=timezone.utc)


def page(rows):
    body = "".join(
        f'<div class="views-row"><h3><a href="{uri}">{title}</a></h3>'
        f'<span class="date">{stamp}</span></div>'
        for uri,title,stamp in rows
    )
    return ('<!doctype html><html><body><main>'
            + body + '</main></body></html>').encode()


FERC_RELEASE = (
    "/news-events/news/ferc-approves-major-gas-infrastructure-facilities-get-american-energy-moving",
    "FERC Approves Major Gas Infrastructure Facilities to Get American Energy Moving",
    "November 19, 2026",
)


class FercNewsTests(unittest.TestCase):
    def test_real_style_regulatory_release_is_captured_date_only(self):
        data=page([FERC_RELEASE])
        rows=parse_listing(data,now=NOW)
        self.assertEqual(len(rows),1)
        a=rows[0]
        self.assertEqual(a["source"],SOURCE_NAME)
        self.assertEqual(a["category"],"Infrastructure & Investment")
        self.assertEqual(a["published_precision"],"day")
        self.assertEqual(a["published_utc"],"2026-11-19T00:00:00+00:00")
        self.assertEqual(a["first_collector_observed_utc"],NOW.isoformat())
        self.assertFalse(a["editorial_candidate"])
        self.assertNotIn("article_body",str(a))
        self.assertNotIn("summary_excerpt",str(a))

    def test_false_category_and_outside_domains_not_articles(self):
        news=page([
            ("https://other.example/news-events/news/ferc-approves-gas-project",
             "FERC approves gas infrastructure project", "November 19, 2026"),
            ("/news-events/news/news-releases-headlines",
             "News Releases and Headlines", "November 19, 2026"),
            ("/news-events/news/ferc-scammers-warning",
             "Fraud alert scammers pretend to be agency officials", "November 19, 2026"),
            FERC_RELEASE,
        ])
        rows=parse_listing(news,now=NOW)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["title"],FERC_RELEASE[1])

    def test_dated_source_required_no_guess_from_neighboring_item(self):
        first=(FERC_RELEASE[0],FERC_RELEASE[1],"")
        other=("/news-events/news/natural-gas-pipeline-gas-infrastructure-approval",
               "FERC Approves Natural Gas Pipeline Infrastructure Project",
               "November 19, 2026")
        rows=parse_listing(page([first,other]),now=NOW)
        self.assertEqual(len(rows),1)
        self.assertIn("pipeline",rows[0]["url"])

    def test_dedup_and_save_without_overwriting_existing_rss(self):
        with tempfile.TemporaryDirectory() as temp:
            state=Path(temp)/"articles.json"
            existing={"url":"https://www.eia.gov/todayinenergy/detail.php?id=123",
                      "title":"U.S. natural gas storage report",
                      "published_utc":NOW.isoformat(),
                      "published_precision":"timestamp"}
            state.write_text(json.dumps({"articles":[existing],"runs":[{"run_utc":NOW.isoformat()}],
                                         "source_health":{}}))
            fetching=lambda _:(page([FERC_RELEASE,FERC_RELEASE]),200)
            first=collect(state,Path(temp)/"out",now=NOW,fetcher=fetching)
            self.assertEqual(first["new_links"],1)
            saved=json.loads(state.read_text())
            self.assertEqual(len(saved["articles"]),2)
            self.assertEqual(saved["articles"][0],existing)
            stored=next(x for x in saved["articles"] if x["source"]==SOURCE_NAME)
            self.assertEqual(stored["first_collector_observed_utc"],NOW.isoformat())
            second=collect(state,Path(temp)/"out",
                           now=NOW+timedelta(minutes=10),fetcher=fetching)
            self.assertEqual(second["new_links"],0)
            again=json.loads(state.read_text())
            self.assertEqual(next(x for x in again["articles"] if x["source"]==SOURCE_NAME)
                             ["first_collector_observed_utc"],NOW.isoformat())

    def test_upstream_failure_keeps_original_state_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            state=Path(d)/"articles.json"
            state.write_text(json.dumps({"articles":[],"runs":[]}),encoding="utf-8")
            original=state.read_bytes()
            with self.assertRaisesRegex(ValueError,"HTTP 503"):
                collect(state,Path(d)/"out",now=NOW,
                        fetcher=lambda _:(b"unavailable",503))
            self.assertEqual(original,state.read_bytes())

    def test_non_html_or_undated_index_fails_visibly(self):
        with self.assertRaisesRegex(ValueError,"not an HTML"):
            parse_listing(b"<rss><item>FERC gas</item></rss>",now=NOW)
        with self.assertRaisesRegex(ValueError,"No dated"):
            parse_listing(page([(FERC_RELEASE[0], FERC_RELEASE[1], "")]),now=NOW)


if __name__=="__main__":
    unittest.main()
