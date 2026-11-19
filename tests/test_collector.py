"""Offline regression checks; no live network or commercial publisher access."""
import json
import hashlib
import tempfile
import unittest
import threading
from unittest.mock import patch
from datetime import datetime, timezone, timedelta
from pathlib import Path
from collector import clean_url, collect, parse_feed, published_date, SOURCES, DAY_PRECISION_SOURCES, SPECIALIST_NEWS_SOURCES, SYSTEM_OPERATOR_SOURCES
from editorial import evaluate
from xml.etree import ElementTree as ET

NOW = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)

def sample(title="LNG terminal expansion approved", when="Wed, 18 Nov 2026 10:00:00 GMT", url="https://example.gov/energy?utm_source=test"):
    return (f"<rss version='2.0'><channel><item><title>{title}</title><link>{url}</link>"
            f"<pubDate>{when}</pubDate><guid>unique-guid-1</guid>"
            "<description>Natural gas LNG market project</description></item></channel></rss>").encode()

def fixture_fetch(url):
    unique = hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
    return sample(url=f"https://example.gov/unique-story/{unique}"), 200

class CollectorTests(unittest.TestCase):
    def test_pjm_last_resort_atom_fallback_after_three_malformed_primary_responses(self):
        with tempfile.TemporaryDirectory() as tmp:
            primary="https://insidelines.pjm.com/feed/"
            atom="https://insidelines.pjm.com/feed/atom/"
            requested=[]
            def fake(url):
                requested.append(url)
                if url==primary:
                    return b"<rss><channel><item><title>invalid & XML</title></item></channel></rss>",200
                return fixture_fetch(url)
            report=collect(Path(tmp)/"state.json",Path(tmp)/"out",
                           now=NOW,fetcher=fake)
            pjm=next(x for x in report["sources"] if x["source"]=="PJM Inside Lines")
            self.assertEqual(report["feeds_connected"],len(SOURCES))
            self.assertEqual(requested.count(primary),3)
            self.assertEqual(requested.count(atom),1)
            self.assertTrue(pjm["fallback_used"])
            self.assertEqual(pjm["actual_feed_url"],atom)
            self.assertIn("ParseError",pjm["primary_error_before_fallback"])
            self.assertEqual(pjm["request_attempts"],4)
            self.assertTrue(report["source_health"]["PJM Inside Lines"]["last_fallback_used"])

    def test_pjm_429_does_not_probe_alternate_to_avoid_rate_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            primary="https://insidelines.pjm.com/feed/"
            atom="https://insidelines.pjm.com/feed/atom/"
            requested=[]
            def fake(url):
                requested.append(url)
                if url==primary:
                    return b"",429
                if url==atom:
                    raise AssertionError("Never use alternate after 429")
                return fixture_fetch(url)
            report=collect(Path(tmp)/"state.json",Path(tmp)/"out",
                           now=NOW,fetcher=fake)
            pjm=next(x for x in report["sources"] if x["source"]=="PJM Inside Lines")
            self.assertFalse(pjm["connected"])
            self.assertEqual(pjm["request_attempts"],1)
            self.assertEqual(requested.count(atom),0)

    def test_publisher_cli_uses_real_bounded_parallel_fetch_pool(self):
        from collector import main
        with tempfile.TemporaryDirectory() as d:
            seen=set()
            active=0
            maximum=0
            guard=threading.Lock()
            ready=threading.Event()
            def fake(url):
                nonlocal active,maximum
                with guard:
                    seen.add(threading.get_ident())
                    active+=1
                    maximum=max(active,maximum)
                    if len(seen)>=3:
                        ready.set()
                if not ready.wait(timeout=5):
                    raise AssertionError("RSS CLI did not start three parallel workers")
                result=fixture_fetch(url)
                with guard:
                    active-=1
                return result
            with patch("collector.fetch_feed",side_effect=fake):
                rc=main(["--state",str(Path(d)/"articles.json"),
                         "--output",str(Path(d)/"out")])
            self.assertEqual(rc,0)
            self.assertGreaterEqual(len(seen),3)
            self.assertLessEqual(maximum,5)
            self.assertTrue((Path(d)/"articles.json").exists())

    def test_explicit_live_finish_clock_overrides_injected_start_timestamp(self):
        with tempfile.TemporaryDirectory() as temp:
            done=NOW+timedelta(minutes=9)
            result=collect(Path(temp)/"state.json",Path(temp)/"out",
                           now=NOW,fetcher=fixture_fetch,
                           completion_clock=lambda:done)
            self.assertEqual(result["run_utc"],NOW.isoformat())
            self.assertEqual(result["completed_utc"],done.isoformat())
            data=json.loads((Path(temp)/"state.json").read_text())
            self.assertTrue(all(x["first_collected_utc"]==done.isoformat()
                                for x in data["articles"]))

    def test_first_collected_timestamp_is_preserved_across_later_polls(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"state.json"
            out=Path(d)/"out"
            first=collect(path,out,now=NOW,fetcher=fixture_fetch)
            original=json.loads(path.read_text())
            row=original["articles"][0]
            self.assertEqual(row["first_collected_utc"],NOW.isoformat())
            self.assertEqual(first["completed_utc"],NOW.isoformat())
            later=NOW+timedelta(minutes=10)
            collect(path,out,now=later,fetcher=fixture_fetch)
            second=json.loads(path.read_text())
            self.assertEqual(second["articles"][0]["first_collected_utc"],NOW.isoformat())

    def test_rss_dates_links(self):
        items, rejected, seen = parse_feed(sample(), "Official", NOW, 48)
        self.assertEqual((len(items), seen), (1, 1))
        self.assertEqual(items[0]["url"], "https://example.gov/energy")
        self.assertEqual(items[0]["category"], "LNG")
        self.assertEqual(rejected["undated"], 0)

    def test_publisher_feed_tier_not_misrepresented_as_agency(self):
        items,_,_ = parse_feed(sample(title="LNG export shipping supply agreement"),"Offshore Energy News",NOW,48)
        self.assertEqual(items[0]["source_class"],"specialist_publisher")
        self.assertIn("Offshore Energy News",SPECIALIST_NEWS_SOURCES)

    def test_pjm_is_original_grid_operator_not_a_government_agency(self):
        items,_,_ = parse_feed(sample(title="PJM power grid reliability updates"),"PJM Inside Lines",NOW,48)
        self.assertIn("PJM Inside Lines", SYSTEM_OPERATOR_SOURCES)
        self.assertEqual(items[0]["source_class"],"system_operator_primary")

    def test_day_only_regulatory_source_preserves_date_without_release_time(self):
        xml=b"""<rss version='2.0'><channel><item>
            <title>FERC pipeline environmental permit notice</title>
            <link>https://example.gov/ferc/2026-11-18</link>
            <pubDate>2026-11-18</pubDate></item></channel></rss>"""
        entries,skips,seen=parse_feed(xml,"Federal Register notices",NOW,48,date_precision="day")
        self.assertEqual((len(entries),seen),(1,1))
        self.assertEqual(entries[0]["published_utc"],"2026-11-18T00:00:00+00:00")
        self.assertEqual(entries[0]["published_precision"],"day")
        self.assertFalse(entries[0]["editorial_candidate"])
        # Same date-only payload cannot masquerade as a timestamped news headline.
        regular,rejections,_=parse_feed(xml,"Other Publisher",NOW,48)
        self.assertFalse(regular)
        self.assertEqual(rejections["undated"],1)

    def test_http_200_invalid_rss_root_does_not_count_connected(self):
        with tempfile.TemporaryDirectory() as d:
            empty=b"<rss version='2.0'></rss>"
            def fake(url):
                return (empty,200) if url==SOURCES[0][1] else fixture_fetch(url)
            report=collect(Path(d)/"db.json",Path(d)/"out",now=NOW,fetcher=fake)
            self.assertEqual(report["feeds_connected"],len(SOURCES)-1)
            self.assertEqual(report["scan_state"],"degraded")
            self.assertIn("required channel",report["sources"][0]["error"])

    def test_transient_malformed_pjm_retries_and_recovers_without_fake_success(self):
        with tempfile.TemporaryDirectory() as d:
            counts = {}
            def recover(url):
                counts[url] = counts.get(url, 0) + 1
                if url.endswith("insidelines.pjm.com/feed/") and counts[url] < 3:
                    return b"<rss><channel><item><title>bad & token</title></item></channel></rss>", 200
                return fixture_fetch(url)
            report = collect(Path(d)/"state.json",Path(d)/"out",now=NOW,fetcher=recover)
            pjm = next(x for x in report["sources"] if x["source"]=="PJM Inside Lines")
            self.assertEqual(pjm["request_attempts"],3)
            self.assertEqual(pjm["transient_retry_count"],2)
            self.assertTrue(pjm["recovered_after_retry"])
            self.assertTrue(pjm["connected"])
            self.assertNotIn("error",pjm)
            self.assertEqual(report["scan_state"],"healthy")
            self.assertEqual(report["feeds_recovered_after_retry"],1)
            source=json.loads((Path(d)/"state.json").read_text())["source_health"]["PJM Inside Lines"]
            self.assertEqual(source["total_recoveries"],1)
            self.assertEqual(source["consecutive_failures"],0)

    def test_always_malformed_pjm_stays_failed_after_bounded_attempts(self):
        with tempfile.TemporaryDirectory() as d:
            counts={}
            def always_bad(url):
                counts[url] = counts.get(url,0) + 1
                if url.startswith("https://insidelines.pjm.com/feed/"):
                    return b"<rss><channel><item><title>bad & markup</title></item></channel></rss>",200
                return fixture_fetch(url)
            report=collect(Path(d)/"state.json",Path(d)/"out",now=NOW,fetcher=always_bad)
            pjm=next(x for x in report["sources"] if x["source"]=="PJM Inside Lines")
            self.assertFalse(pjm["connected"])
            self.assertEqual(pjm["request_attempts"],4)
            self.assertEqual(counts["https://insidelines.pjm.com/feed/"],3)
            self.assertEqual(counts["https://insidelines.pjm.com/feed/atom/"],1)
            self.assertEqual(report["feeds_connected"],len(SOURCES)-1)
            self.assertEqual(report["scan_state"],"degraded")
            self.assertIn("ParseError",pjm["error"])

    def test_nonretryable_http_429_does_not_hammer_rate_limited_source(self):
        with tempfile.TemporaryDirectory() as d:
            attempts={}
            def rate_limited(url):
                attempts[url]=attempts.get(url,0)+1
                if url==SOURCES[0][1]:
                    return b"",429
                return fixture_fetch(url)
            report=collect(Path(d)/"db.json",Path(d)/"out",now=NOW,fetcher=rate_limited)
            self.assertEqual(attempts[SOURCES[0][1]],1)
            source=report["sources"][0]
            self.assertEqual(source["request_attempts"],1)
            self.assertEqual(source["transient_retry_count"],0)
            self.assertFalse(source["connected"])

    def test_transient_http_503_recovers_on_second_attempt(self):
        with tempfile.TemporaryDirectory() as d:
            attempts={}
            def flaky(url):
                attempts[url]=attempts.get(url,0)+1
                if url==SOURCES[0][1] and attempts[url]==1:
                    return b"",503
                return fixture_fetch(url)
            report=collect(Path(d)/"db.json",Path(d)/"out",now=NOW,fetcher=flaky)
            self.assertEqual(report["feeds_recovered_after_retry"],1)
            self.assertEqual(report["transient_retries"],1)
            self.assertEqual(report["scan_state"],"healthy")

    def test_source_freshness_is_measured_separately_from_connectivity(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"db.json"
            report=collect(path,Path(d)/"out",now=NOW,fetcher=fixture_fetch)
            source=report["sources"][0]
            self.assertTrue(source["connected"])
            self.assertIsNotNone(source["newest_feed_published_utc"])
            stored=json.loads(path.read_text())["source_health"][source["source"]]
            self.assertEqual(stored["newest_feed_published_utc"],source["newest_feed_published_utc"])

    def test_updated_is_not_published(self):
        xml = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Gas LNG</title><link href="https://example.gov/x"/><updated>2026-11-18T10:00:00Z</updated></entry></feed>'
        items, rejected, seen = parse_feed(xml, "Official", NOW, 48)
        self.assertEqual(seen, 1)
        self.assertEqual(len(items), 0)
        self.assertEqual(rejected["undated"], 1)

    def test_rejects_old_future_undated(self):
        for date, label in [("Wed, 01 Jan 2020 10:00:00 GMT", "old"), ("Wed, 25 Nov 2026 10:00:00 GMT", "future"), ("", "undated")]:
            items, rejected, _ = parse_feed(sample(when=date), "Official", NOW, 48)
            self.assertFalse(items)
            self.assertEqual(rejected[label], 1)

    def test_public_history_has_no_publisher_excerpt(self):
        with tempfile.TemporaryDirectory() as d:
            state=Path(d)/"state.json"
            collect(state,Path(d)/"out",now=NOW,fetcher=fixture_fetch)
            saved=json.loads(state.read_text())
            self.assertTrue(saved["articles"])
            self.assertTrue(all("summary_excerpt" not in x for x in saved["articles"]))

    def test_sensitive_link_query_and_credentials(self):
        self.assertFalse(clean_url("https://user:secret@example.com/story"))
        self.assertEqual(clean_url("https://example.com/story?utm_source=site&token=secret&id=5"),"https://example.com/story?id=5")

    def test_state_persists_without_duplication(self):
        with tempfile.TemporaryDirectory() as d:
            state = Path(d) / "state.json"
            out = Path(d) / "out"
            fetch = fixture_fetch
            first = collect(state, out, now=NOW, fetcher=fetch)
            self.assertEqual(first["feeds_connected"], len(SOURCES))
            self.assertEqual(first["relevant_fresh_entries"], len(SOURCES)-len(DAY_PRECISION_SOURCES))
            self.assertEqual(len(json.loads((out/"editorial_candidates.json").read_text())), len(SOURCES)-len(DAY_PRECISION_SOURCES))
            self.assertEqual(first["new_article_links"], len(SOURCES))  # source identities are independent
            second = collect(state, out, now=NOW + timedelta(hours=1), fetcher=fetch)
            self.assertEqual(second["new_article_links"], 0)
            self.assertEqual(len(json.loads(state.read_text())["articles"]), len(SOURCES))
            self.assertEqual(len(json.loads(state.read_text())["runs"]), 2)

    def test_relevance_requires_sector_context(self):
        self.assertTrue(evaluate("LNG export terminal expansion approved")["editorial_candidate"])
        self.assertTrue(evaluate("PJM seeks faster connections for data center power demand")["editorial_candidate"])
        self.assertFalse(evaluate("Company announces a new project and commission approval")["editorial_candidate"])
        self.assertFalse(evaluate("Spoiled ingredients and boiler maintenance project")["editorial_candidate"])

    def test_named_energy_developments_do_not_disappear(self):
        self.assertTrue(evaluate("Venture Global signs LNG supply agreement with buyer")["editorial_candidate"])
        self.assertTrue(evaluate("Chevron nears major Beacon Offshore acquisition")["editorial_candidate"])
        self.assertTrue(evaluate("Cheniere approves new Corpus Christi expansion")["editorial_candidate"])
        self.assertTrue(evaluate("Calpine advances power generation project")["editorial_candidate"])
        self.assertFalse(evaluate("City approves new hotel and restaurant")["editorial_candidate"])

    def test_date_only_regulatory_leads_are_not_fresh_editorial_headlines(self):
        items, rejected, seen = parse_feed(sample(), "Federal Register FERC notices", NOW, 48, date_precision="day")
        self.assertEqual(seen, 1)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["published_precision"], "day")
        self.assertEqual(items[0]["status"], "research_date_only")
        self.assertFalse(items[0]["editorial_candidate"])

    def test_daily_volume_separates_regulatory_notices(self):
        with tempfile.TemporaryDirectory() as d:
            state, out = Path(d)/"state.json", Path(d)/"out"
            report = collect(state, out, now=NOW, fetcher=fixture_fetch)
            volumes = json.loads((out/"volume_7d.json").read_text())
            self.assertEqual(report["relevant_fresh_entries"], len(SOURCES)-len(DAY_PRECISION_SOURCES))
            self.assertEqual(report["date_only_entries"], 1)
            self.assertEqual(report["editorial_candidates_24h"], len(SOURCES)-len(DAY_PRECISION_SOURCES))
            self.assertEqual(len(json.loads((out/"editorial_candidates_24h.json").read_text())), len(SOURCES)-len(DAY_PRECISION_SOURCES))
            self.assertEqual(volumes["days"][0]["editorial_candidates"], len(SOURCES)-len(DAY_PRECISION_SOURCES))
            self.assertEqual(volumes["days"][0]["regulatory_date_only_leads"], 1)
            self.assertEqual(len(json.loads((out/"editorial_candidates.json").read_text())), len(SOURCES)-len(DAY_PRECISION_SOURCES))

    def test_old_federal_register_duplication_is_folded_by_url(self):
        with tempfile.TemporaryDirectory() as d:
            state, out = Path(d)/"state.json", Path(d)/"out"
            old_a = parse_feed(sample(url="https://example.gov/fed-notice"), "Federal Register FERC notices", NOW, 48, date_precision="day")[0][0]
            old_b = parse_feed(sample(url="https://example.gov/fed-notice"), "Federal Register DOE notices", NOW, 48, date_precision="day")[0][0]
            state.write_text(json.dumps({"articles":[old_a,old_b],"runs":[]}))
            report=collect(state,out,now=NOW,fetcher=fixture_fetch)
            data=json.loads(state.read_text())["articles"]
            duplicated=[x for x in data if x["url"]=="https://example.gov/fed-notice"]
            self.assertEqual(len(duplicated),1)
            self.assertEqual(duplicated[0]["source"],"Federal Register notices")
            self.assertFalse(duplicated[0]["editorial_candidate"])
            self.assertEqual(report["distinct_article_links_7d"],len(SOURCES)+1)

    def test_failure_is_visible(self):
        with tempfile.TemporaryDirectory() as d:
            def fail(url):
                raise OSError("offline")
            report = collect(Path(d)/"db.json", Path(d)/"out", now=NOW, fetcher=fail)
            self.assertEqual(report["feeds_connected"], 0)
            self.assertEqual(len(report["sources"]), len(SOURCES))
            self.assertIn("offline", (Path(d)/"out/latest.md").read_text())

    def test_invalid_schema_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            state=Path(d)/"db.json"
            state.write_text(json.dumps(["bad-state"]))
            with self.assertRaises(ValueError):
                collect(state,Path(d)/"out",now=NOW,fetcher=fixture_fetch)

    def test_http_503_rss_body_is_not_a_successful_connection(self):
        with tempfile.TemporaryDirectory() as d:
            r=collect(Path(d)/"db.json",Path(d)/"out",now=NOW,
                      fetcher=lambda url:(sample(),503))
            self.assertEqual(r["scan_state"],"critical")
            self.assertEqual(r["feeds_connected"],0)

    def test_single_connected_feed_fails_minimum_quorum(self):
        with tempfile.TemporaryDirectory() as d:
            state=Path(d)/"db.json"
            def one(url):
                if url==SOURCES[0][1]:
                    return sample(),200
                raise OSError("offline")
            r=collect(state,Path(d)/"out",now=NOW,fetcher=one)
            self.assertEqual(r["feeds_connected"],1)
            self.assertEqual(r["scan_state"],"critical")
            second=collect(state,Path(d)/"out",now=NOW+timedelta(hours=1),fetcher=one)
            self.assertEqual(second["scan_state"],"critical")
            history=json.loads(state.read_text())
            self.assertEqual(history["source_health"][SOURCES[1][0]]["consecutive_failures"],2)
            self.assertEqual(history["source_health"][SOURCES[0][0]]["consecutive_successes"],2)

    def test_zero_new_headlines_is_success_if_feeds_parse(self):
        with tempfile.TemporaryDirectory() as d:
            state=Path(d)/"db.json"
            r=collect(state,Path(d)/"out",now=NOW,fetcher=fixture_fetch)
            self.assertEqual(r["scan_state"],"healthy")
            second=collect(state,Path(d)/"out",now=NOW+timedelta(hours=1),fetcher=fixture_fetch)
            self.assertEqual(second["new_article_links"],0)
            self.assertEqual(second["scan_state"],"healthy")

    def test_homepage_url_is_not_an_article_even_with_a_valid_date(self):
        entries,rejected,_ = parse_feed(sample(
            title="FERC official pipeline filing notice",
            url="https://ferc.gov/"),"Regulator",NOW,48)
        self.assertEqual(entries,[])
        self.assertEqual(rejected["homepage_link"],1)
        # Deep links with query identifiers remain actionable.
        valid,_,_=parse_feed(sample(
            title="FERC official pipeline filing notice",
            url="https://ferc.gov/?filing=20261118"),"Regulator",NOW,48)
        self.assertEqual(len(valid),1)

    def test_invalid_existing_state_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            state = Path(d)/"db.json"
            state.write_text("{broken")
            with self.assertRaises(ValueError):
                collect(state, Path(d)/"out", now=NOW, fetcher=lambda _: (sample(),200))
            self.assertEqual(state.read_text(), "{broken")

if __name__ == "__main__":
    unittest.main()
