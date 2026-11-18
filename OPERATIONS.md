# EnergyBrew — News Collection Operations

This is an operating pilot for internal research, **not** a licensed news redistribution service or automated newsletter publisher.

## Current hosted workflow

- **Primary official RSS collector:** [Actions](https://github.com/AbdulHassan0/EnergyBrew/actions/workflows/live-collector.yml), scheduled at 04:17 / 10:17 / 16:17 / 22:17 UTC. Includes official EIA, DOE, NRC, European Commission, and Federal Register sources.
- **Rolling global discovery sampler:** [Actions](https://github.com/AbdulHassan0/EnergyBrew/actions/workflows/frequent-gal.yml), scheduled at minute 7, 22, 37 and 52 each hour. The GDELT Global Article List is a rolling approximately 15-minute index feed, and GitHub schedule delays can create sampling gaps.
- Both workflows use the same GitHub Actions concurrency group and shared private `collector-state` branch. This is **pilot-scale state storage**, not a production database.
- The full publishing website, automated email sender, and subscriber analytics are **not** deployed with these workflows. Nothing is auto-approved or emailed.

## Live reports

1. [Research Desk — ranked, clearly unapproved leads](https://github.com/AbdulHassan0/EnergyBrew/blob/collector-state/state/desk_latest.md)
2. [Reliability scorecard — daily volume and missing scans](https://github.com/AbdulHassan0/EnergyBrew/blob/collector-state/state/metrics_latest.md)
3. [Newsroom health — official RSS vs GDELT DOC vs GAL](https://github.com/AbdulHassan0/EnergyBrew/blob/collector-state/state/health_latest.md)
4. [Official publisher timestamped 24-hour leads](https://github.com/AbdulHassan0/EnergyBrew/blob/collector-state/state/editorial_candidates_24h.json)
5. [Regulatory notices — publication DATE only](https://github.com/AbdulHassan0/EnergyBrew/blob/collector-state/state/regulatory_watch.json)
6. [Raw global discovery research links](https://github.com/AbdulHassan0/EnergyBrew/blob/collector-state/state/research_leads_24h.json)
7. [Company/newswire claims — unverified](https://github.com/AbdulHassan0/EnergyBrew/blob/collector-state/state/releases_leads_24h.json)

## Interpreting the dashboard accurately

| Lane | What its timestamps prove | What they do NOT prove |
|---|---|---|
| Official RSS | Original publisher-provided publication timestamp on a feed | Story facts independently verified |
| Federal Register | Publication calendar DATE | Intraday breaking-news time |
| GDELT DOC / GAL | Time GDELT first indexed the URL | Original publisher article publication time, truth, or a license |
| Company press release aggregator | Third-party feed's recorded time | Independent editorial reporting, named issuer, or original publisher time |

**Do not add GDELT links or press release claims directly to a sent newsletter.** Editors must check the actual linked source, date, business impact, facts and usage rights.

## Reliability thresholds and incident response

- If the primary collector's last successful scan is more than 12 hours old, open its Actions history. Inspect failing source rows and retry only after identifying the reason.
- If the GAL sampler is older than 35 minutes or recorded a gap over 20 minutes, inspect its Actions run. An index sampling gap cannot automatically be filled using the current rolling RSS snapshot; label coverage incomplete.
- If GDELT DOC returns 429, honor its persistent cooldown; the independent GAL path should continue. **Do not** accelerate retries.
- If a feed says HTTP 200 but has 0 current articles, count connectivity as successful and current coverage as 0. Do not manufacture stories or change publication dates.
- If source permissions are not sufficiently clear for commercial automated polling, leave the feed off until permission is obtained.
- If GitHub Actions or state persistence fails, preserve existing state, keep the run failure visible, and do not claim a healthy scan.

## Acceptance criteria for a seven-day live pilot

- Seven consecutive days of hosted observations; the report must explicitly say `seven_day_pilot_complete = true`.
- Review missing scheduled scans and measured GAL sampling gaps.
- Record source connectivity separately from fresh relevant publisher-timestamped articles.
- Report by category: Natural Gas & LNG, Power & Electricity, Oil & Energy, Infrastructure & Investment.
- Calculate URL duplicates separately from possible repeated reporting of the same real event.
- Examine false positives (school energy tips, promotional releases, tag pages, unrelated keyword collisions), false negatives and multilingual headline needs.
- Target **15–25 distinct, useful daily editorial research stories**, but **never label GDELT index-first-seen links as original publisher-timestamped stories**.
- No publication or email without manual editorial approval and licensing review.

## Sustainable hosting note

Scheduled GitHub Actions use plan-dependent private-repository minutes and artifacts quotas. A 15-minute rolling sampler may consume meaningful included runner minutes. Monitor [GitHub Actions usage and billing](https://github.com/settings/billing). If it becomes expensive or is chronically delayed, move the collector to a continuously running service and proper database; do not silently slow polling and misrepresent coverage.

State branch commits on every scan are a convenient pilot method, **not appropriate indefinitely** for high-volume research. A durable production database with backups, retained ingestion logs, access controls, and job-level alerts is the next hosting milestone.

## Next commercial news-source expansion

Specialist energy publishers (S&P Global Energy, NGI, RBN, Argus, Reuters, etc.) offer far better headline coverage than official newsrooms. However, being able to view or subscribe to an RSS feed is not a commercial right to poll or republish it. Obtain a feed/news/API license where required. Prefer metadata/original links, original summaries based on facts, and a record of usage rights and allowed retention.
