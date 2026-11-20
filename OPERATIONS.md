# EnergyBrew — News Collection Operations

This is an operating pilot for public-source news metadata collection, **not** a licensed news redistribution service or independently verified publisher. The repository and collector-state branch are PUBLIC, so article bodies, snippets, credentials and confidential information must never be retained.

## Current hosted workflow

- **Primary source-aware RSS collector:** [Actions](https://github.com/AbdulHassan0/EnergyBrew/actions/workflows/live-collector.yml), scheduled at 04:17 / 10:17 / 16:17 / 22:17 UTC. Includes EIA, DOE, NRC, European Commission, Federal Register, Offshore Energy, OilPrice.com, Utility Dive, and PJM Inside Lines sources. Connected sources include government agencies, specialist publishers, and an independent grid-operator's primary feed; classes are never conflated.
- **Primary rolling GDELT sampler:** [Actions](https://github.com/AbdulHassan0/EnergyBrew/actions/workflows/frequent-gal.yml), scheduled at minute 6, 16, 26, 36, 46 and 56 (UTC) every hour.
- **Staggered backup sampler:** [Actions](https://github.com/AbdulHassan0/EnergyBrew/actions/workflows/hourly-discovery.yml), scheduled at minute 1, 11, 21, 31, 41 and 51 (UTC). Both use the same state-write lock. The nominal five-minute combined sampling cadence is **not guaranteed**: GitHub Actions cron may delay or skip runs. No historical articles are inferred from missed snapshots.
- **Fast-sampler responsibilities (November 19 update):** Both rolling GAL workflows restore retained state, fetch the live GAL index, run the public-metadata gate, and persist the sampled response *before* optional summaries. They do **not** rebuild the full research desk, seven-day reliability scorecard, source-gap reconciliation, or newsroom report each time. This reduces shared-writer lock time and avoids treating delayed analytics as a missed ingestion attempt. Full analytics and persistent `metrics_latest`/`source_gap_latest` updates are handled by the four-times-daily `live-collector.yml` runs. `gal_latest` is refreshed by each successful fast-sampler state write. Health metrics may therefore be older than the newest GAL sample; always inspect their `generated_utc` or `audit_utc` timestamps.
- Source-level transient RSS errors use bounded retries (one extra attempt generally; two extra for PJM). HTTP 429 is never automatically retried, and permanently invalid feeds stay marked failed. Per-source recovery and outage diagnostics are recorded in collector state.
- **GDELT DOC throttle circuit:** if DOC returns HTTP 429/503, it stops that run's remaining DOC queries and remembers an escalating cooldown: 90 minutes, 3 hours, 6 hours, then 12 hours for successive throttle episodes. A longer valid `Retry-After` header takes precedence (bounded at 24 hours). One successful DOC response clears the throttle streak. **The independent GAL rolling feed is never held in the DOC cooldown.**
- **Retry reporting:** the RSS health report distinguishes source connectivity from temporary retry attempts and successful recoveries. The retained scan history records per-run recovery events; existing historical runs without those fields remain valid, with counts assumed zero for reporting only.
- The collectors use a shared concurrency group and PUBLIC collector-state branch. All writes pass the strict public_collector_guard.py metadata-only gate (including a legacy snippet migration). This is **pilot-scale state storage**, not a private or licensed feed warehouse.
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
| Government agency RSS | Original agency-feed publication timestamp | Independent fact verification or commercial redistribution permission |
| Grid operator primary RSS (PJM) | PJM's own source-feed timestamp | Government agency status or independent journalistic reporting |
| Specialist publisher RSS | Publisher-provided RSS publication timestamp | Independently verified facts, original article rights, or commercial reuse permission |
| Federal Register | Publication calendar DATE | Intraday breaking-news time |
| GDELT DOC / GAL | Time GDELT first indexed the URL | Original publisher article publication time, truth, or a license |
| Company press release aggregator | Third-party feed's recorded time | Independent editorial reporting, named issuer, or original publisher time |

**Do not add GDELT links or press release claims directly to a sent newsletter.** Editors must check the actual linked source, date, business impact, facts and usage rights.

## Morning editorial cutoff handoff (06:30 Central)

The 06:45 editorial preparation now calls `cutoff_desk.py` against the latest saved `articles.json`, `discovery.json`, and `press_releases.json` source history. This avoids trusting a ranked desk regenerated hours earlier. Only records with a **known local first-collection timestamp at or before 06:30 Central** can enter this morning queue. Records first collected later and legacy records without a local observation clock are excluded and counted; original publisher/source timestamps must also qualify within the morning's allowable date window. GDELT index timestamps remain unverified publisher dates. This is source-evidence filtering, not editorial fact checking.

The generated `MORNING_CUTOFF_DESK.json` includes readiness blockers, source-category exclusions, and a research-only status. The older periodically generated desk remains available for broader ongoing research, but is no longer the source for compiling an edition's morning pilot. The 06:45 job may generate review material even when strict overnight availability checks block `ready_for_editor_review`; this never overrides approval and email-send controls.

## Reliability thresholds and incident response

- If the primary collector's last successful scan is more than 12 hours old, open its Actions history. Inspect failing source rows and retry only after identifying the reason.
- If the latest successful GAL sample is older than **25 minutes**, or any successful-sample interval exceeds **15 minutes**, inspect the actual Actions timestamps and source run. Missed index snapshots cannot be recovered from the current rolling feed.
- Review `gal_sampled_window_24h` and `gal_sampled_window_7d` in [reliability metrics](https://github.com/AbdulHassan0/EnergyBrew/blob/collector-state/state/metrics_latest.json). These are **upper bounds** on observable time using an assumed 15-minute rolling window per successful sample, not proof of full news coverage. `unobserved_minutes_at_least` measures at least how much time the collector could not have sampled. A seven-hour gap must not be portrayed as a minor single incident.
- If GDELT DOC returns 429, honor its persistent cooldown; the independent GAL path should continue. **Do not** accelerate retries.
- If a feed says HTTP 200 but has 0 current articles, count connectivity as successful and current coverage as 0. Do not manufacture stories or change publication dates.
- If source permissions are not sufficiently clear for commercial automated polling, leave the feed off until permission is obtained. Specifically, Rigzone and Oil & Gas Journal RSS prohibit commercial use without separate rights; do not integrate them on the basis of public accessibility.
- If GitHub Actions or state persistence fails, preserve existing state, keep the run failure visible, and do not claim a healthy scan.

## Acceptance criteria for a seven-day live pilot

- Seven consecutive days of hosted observations; the report must explicitly say `seven_day_pilot_complete = true`.
- Review actual missed scheduled polls, measured GAL gaps, longest uncovered span, 24h and seven-day potential coverage upper bounds. The pilot is **not** complete while any seven-day window remains unobserved.
- Record source connectivity separately from fresh relevant publisher-timestamped articles; distinguish agency, grid-operator primary, specialist-publisher, GDELT-first-seen, and press-release claims.
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

## Workflow notifications and failure triage — November 19, 2026

**Background:** GitHub sent repeated "EnergyBrew live RSS collection: All jobs
have failed" emails during rapid development. Investigation of specific
November 19 runs (including 44532719422 and 44534002288) found failures in
new morning regression test fixtures, NOT proof that all RSS feeds were down.
The prior workflow also continued its "always" public-metadata guard despite
never restoring state, creating a misleading second SafetyError.

**Permanent separation:**

- \`news-logic-ci.yml\` runs all Python tests on collection-code/test changes,
  without hitting external news feeds, publishing metadata or claiming a live
  run. **Code test failures report under "news logic CI" only.**
- \`live-collector.yml\` runs on its four daily scheduled slots or deliberate
  manual dispatch, not each push. The live run still performs its critical RSS
  and public-source safety tests. The safety gate and state push run only
  after the earlier required steps succeed.
- \`frequent-gal.yml\`, \`hourly-discovery.yml\` and
  \`morning-news-readiness.yml\` are time- or manually triggered only, rather
  than also firing on development pushes.
- \`scheduler-audit.yml\` audits scheduling once daily rather than hourly.
  A genuine sustained missed-schedule incident may still produce a **real
  failure notification**. This is deliberate; don't suppress genuine outages.
- A failing source scan, failed public-metadata guard, or failed morning
  readiness is actionable and should remain visible in Actions.

**Proof:** First separate CI run
\`https://github.com/AbdulHassan0/EnergyBrew/actions/runs/44536947333\`
passed 211 tests. No live RSS collector was triggered by that commit.

**Still unproven:** the next scheduled RSS run must succeed on the new
configuration, and persistent hosting is not deployed. GitHub schedules
remain best effort. This workflow change cannot stop notification emails
for *historically* failed runs or control the GitHub notification preference
on the user's account.
