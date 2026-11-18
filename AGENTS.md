# EnergyBrew — active development scope

## Binding user instruction (November 18, 2026)

**WORK ON NEWS COLLECTION AND NEWS LOGIC ONLY.** Do not start, modify, or refactor the frontend, newsletter design, newsletter publishing, email delivery, subscriber features, monetization, marketing, or unrelated product work until the user expressly gives permission.

Permitted work: public-source discovery, feed/API vetting, live collection, resilient scheduling, safe state, rate-limit and error handling, ranking, classification, deduplication, source/date provenance, news relevance and accuracy, measured coverage, CI tests, false positives/negatives, telemetry, and operational reliability.

## Non-negotiable news engineering requirements

- The repository and collector-state branch are PUBLIC. State may include public headline/link metadata only. The public_collector_guard.py safety gate must pass before every state write. Never remove the guard to force a green job.
- Do not persist article bodies, long article excerpts, secrets, credentials, email addresses, subscriber information, private editorial material, or proprietary-source outputs.
- Respect publishers' terms, permitted API/RSS usage and rate limits. Rigzone and Oil & Gas Journal RSS state personal/non-commercial restrictions; do not connect them to the commercial news product without permission.
- GDELT first-indexed times are not publisher publication times; press release aggregator times are not verified publisher publication times; government date-only notices are not intraday timestamps.
- Keep agency RSS, grid-operator primary-source RSS, independent specialist RSS, unverified GDELT discovery, and issuer announcements separate in provenance and metrics.
- A 200 response is connectivity evidence, not daily news volume or coverage proof. Report missing scans, failures, upstream throttling, zero-item responses, and stale feed times faithfully.
- Avoid claiming 100% coverage or independent fact-checking. One article URL may have multiple known source observations. Different links about the same event should be grouped conservatively while keeping all original URLs for review.
- Preserve downstream compatibility and verify with offline tests and hosted GitHub Actions before claiming improvements. Do not hide failures.

## Acceptance priorities

1. Resolve observed GDELT sampling gaps and improve seven-day operating reliability measurement.
2. Grow distinct *relevant* news coverage for natural gas, LNG, oil, power, and infrastructure, not just raw article volume.
3. Harden source failures, crawl freshness, API throttling and state consistency.
4. Improve precision/recall with adversarial headline tests, source diversity, and transparent rankings.
5. Keep user-visible reports honest about source limitations, date basis and rights.

This file guides future engineering and is not a promise of unrequested background work. Only the user's express approval can lift the news-only scope.
