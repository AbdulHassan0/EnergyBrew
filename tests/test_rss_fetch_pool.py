"""Bounded HTTP fanout and fresh retries, with no internet access."""
import threading
import unittest
from unittest.mock import patch

from rss_fetch_pool import concurrent_first_fetches


class RSSFetchPoolTests(unittest.TestCase):
    def test_duplicate_source_url_fetched_once_per_first_attempt(self):
        calls=[]
        sources=[("a","https://x.test/rss"),("b","https://x.test/rss")]
        pool,get=concurrent_first_fetches(
            sources=sources, fetcher=lambda u:(calls.append(u) or (b"<rss/>",200)))
        try:
            self.assertEqual(get("https://x.test/rss")[1],200)
            self.assertEqual(calls,["https://x.test/rss"])
        finally:
            pool.shutdown(wait=True)

    def test_retry_after_cached_error_is_new_network_request(self):
        calls=[]
        def fake(url):
            calls.append(url)
            if len(calls)==1:
                raise TimeoutError("first request failed")
            return b"fresh",200
        pool,get=concurrent_first_fetches(
            sources=[("x","https://x.test/rss")],fetcher=fake,sleep=lambda t:None)
        try:
            with self.assertRaises(TimeoutError):
                get("https://x.test/rss")
            self.assertEqual(get("https://x.test/rss"),(b"fresh",200))
            self.assertEqual(len(calls),2)
        finally:
            pool.shutdown(wait=True)

    def test_alternate_is_on_demand_not_prefetched_or_arbitrary(self):
        calls=[]
        primary="https://official.test/feed/"
        fallback="https://official.test/feed/atom/"
        pool,get=concurrent_first_fetches(
            sources=[("official",primary)],
            fetcher=lambda url:(calls.append(url) or (b"<rss/>",200)),
            on_demand_urls=[fallback])
        try:
            self.assertEqual(get(primary)[1],200)
            self.assertEqual(calls,[primary])
            with self.assertRaises(ValueError):
                get("https://unknown.test/feed")
            self.assertEqual(get(fallback)[1],200)
            self.assertEqual(calls,[primary,fallback])
        finally:
            pool.shutdown(wait=True)

    def test_rejects_unlisted_host_without_http_request(self):
        pool,get=concurrent_first_fetches(
            sources=[],fetcher=lambda _:(_ for _ in ()).throw(AssertionError("http")))
        try:
            with self.assertRaises(ValueError):
                get("https://different.example")
        finally:
            pool.shutdown(wait=True)

    def test_bounds_concurrency_even_with_many_publishers(self):
        urls=[("source"+str(i),"https://x.test/"+str(i)) for i in range(18)]
        active=0
        maximum=0
        lock=threading.Lock()
        gate=threading.Event()
        concurrent=threading.Event()
        def fake(url):
            nonlocal active,maximum
            with lock:
                active+=1
                maximum=max(maximum,active)
                if active==3:
                    concurrent.set()
            gate.wait(4)
            with lock:
                active-=1
            return b"ok",200
        pool,get=concurrent_first_fetches(sources=urls,fetcher=fake,workers=4)
        try:
            self.assertTrue(concurrent.wait(4))
            gate.set()
            for _,url in urls:
                self.assertEqual(get(url)[1],200)
            self.assertLessEqual(maximum,4)
            self.assertGreaterEqual(maximum,3)
        finally:
            gate.set()
            pool.shutdown(wait=True)

    def test_worker_cap_enforced(self):
        for n in (-1,0,11):
            with self.subTest(workers=n),self.assertRaises(ValueError):
                concurrent_first_fetches(sources=[],fetcher=lambda u:None,workers=n)


if __name__=="__main__":
    unittest.main()
