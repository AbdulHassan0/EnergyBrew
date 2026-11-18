# EnergyBrew — Live energy news collection

**Status: LIVE RSS collection verified on GitHub-hosted runners (November 18, 2026).**

The repository contains a small, independent collector pilot. It gathers original-source article metadata from selected EIA, DOE, and European Commission RSS feeds; preserves results between scheduled jobs; and **never publishes newsletters or sends email**.

## Verified first-day results

Three successful GitHub Actions runs on November 18, 2026 demonstrated:
- 8/8 eligible official feeds successfully parsed;
- 6 distinct source-dated article links within the 48-hour collection window;
- 3 keyword-relevant energy-market candidates;
- zero duplicate links inserted by the third run.

These are **observed first-day results**, not a seven-day reliability record or 15–25 daily editorial stories.

## Where to see actual reports

- [Latest hosted RSS run](https://github.com/AbdulHassan0/EnergyBrew/blob/collector-state/state/latest.md)
- [Machine-readable run diagnostics](https://github.com/AbdulHassan0/EnergyBrew/blob/collector-state/state/latest.json)
- [Persistent article metadata and run history](https://github.com/AbdulHassan0/EnergyBrew/blob/collector-state/state/articles.json)
- [GitHub Actions run history](https://github.com/AbdulHassan0/EnergyBrew/actions/workflows/live-collector.yml)

The workflow runs **four times daily** on a UTC schedule and is also manually runnable from the Actions tab. Scheduled runs can be delayed by GitHub. Artifacts contain full per-run diagnostics and `editorial_candidates.json`.

## Architecture and safeguards

- `collector.py`: Python standard-library RSS/Atom collector with strict source publication-date handling, URL tracking removal, source-based identity, and keyword classification.
- `tests/test_collector.py`: offline regression tests for RSS parsing, Atom timestamps, persistence, and failure reporting.
- `.github/workflows/live-collector.yml`: internet-connected scheduled runner; restores and persists state in a separate `collector-state` branch.
- All data is **research-only**. Publisher-discovery timestamps never count as original publication dates. Access to an RSS feed is not a license to republish its content.
- No credentials, paid news subscriptions, or SMTP configuration are required for these eight eligible official feeds.

## What is not deployed

This is the **standalone live collector**, not yet the complete Energy TLDR newsletter web application or subscriber/email system. The full local web MVP exists separately as the v2.0 project archive. Joining the hosted collector to that editorial application is a subsequent deployment task.

## Next acceptance test

Run the collector for seven consecutive days, measure unique **relevant** article/event volume per day, inspect low-performing sources and category gaps, then expand with authorized energy-specialist providers. A successful HTTP request is not sufficient: the number of useful unique stories matters.
