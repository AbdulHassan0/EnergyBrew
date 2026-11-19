"""Bounded concurrent initial RSS requests, with real independent retries.

HTTP requests start in a five-thread pool, but collector parsing, persistence
and per-source health bookkeeping remain deterministic and sequential. An
initial exception never reuses an old response for a subsequent retry.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor


def concurrent_first_fetches(*, sources, fetcher, workers=5, sleep=None,
                             on_demand_urls=()):
    if not 1 <= workers <= 10:
        raise ValueError("RSS worker count must be 1..10")
    if not callable(fetcher):
        raise ValueError("RSS network fetcher required")
    # URLs are de-duplicated before network requests even if several source
    # labels accidentally point to the same endpoint.
    urls=list(dict.fromkeys(url for _label,url in sources))
    # The fallback allowlist is authored in code, not learned from untrusted
    # feed items or redirects. It is NEVER prefetched when primary feeds work.
    on_demand=set(on_demand_urls) - set(urls)
    executor=ThreadPoolExecutor(max_workers=workers,
                                thread_name_prefix="energybrew-rss")
    try:
        first={url:executor.submit(fetcher,url) for url in urls}
    except BaseException:
        executor.shutdown(wait=True,cancel_futures=True)
        raise
    attempts={}
    pause=sleep if sleep is not None else time.sleep

    def get(url):
        if url in on_demand:
            return fetcher(url)
        if url not in first:
            raise ValueError("Unconfigured RSS URL")
        times=attempts.get(url,0)
        attempts[url]=times+1
        if times==0:
            return first[url].result()
        pause(min(2 ** (times-1),3))
        return fetcher(url)

    return executor,get
