# EnergyBrew — Live Energy News Collector

**Live GitHub-hosted RSS collection verified on November 18, 2026.**

This private repository contains the independent production-pilot collector, not yet the public Energy TLDR newsletter website. It collects source-linked research metadata only, with no auto-approval, subscriber email, or publication.

## Live status — verified November 18, 2026

The most recent completed [GitHub Actions run](https://github.com/AbdulHassan0/EnergyBrew/actions/workflows/live-collector.yml) verified:

| Measurement | Result |
|---|---:|
| Reachable and parseable eligible official RSS feeds | **10 / 10** |
| Publisher-timestamped RSS entries within 48 hours | **6** |
| High-signal editorial candidates in the 48-hour feed window | **2** |
| Editorial candidates published within the **last 24 hours** | **1** |
| Federal Register date-only entries in collection window | **12** |
| High-signal regulatory watchlist leads retained | **4** |
| Unique stored article links retained for seven days | **18** |

**Caution:** These are observed first-day counts, not seven-day reliability statistics or unique independently verified news events. Regulatory notices have date precision only and are not placed in the last-24-hour breaking-news shortlist.

## Browse actual results

- [Latest collection report](https://github.com/AbdulHassan0/EnergyBrew/blob/collector-state/state/latest.md)
- [Last 24 hours — editorial candidates](https://github.com/AbdulHassan0/EnergyBrew/blob/collector-state/state/editorial_candidates_24h.json)
- [Seven-day editorial research queue](https://github.com/AbdulHassan0/EnergyBrew/blob/collector-state/state/editorial_candidates.json)
- [Regulatory pipeline watchlist](https://github.com/AbdulHassan0/EnergyBrew/blob/collector-state/state/regulatory_watch.json)
- [Daily article-volume report](https://github.com/AbdulHassan0/EnergyBrew/blob/collector-state/state/volume_7d.json)
- [Source-level health and exceptions](https://github.com/AbdulHassan0/EnergyBrew/blob/collector-state/state/latest.json)
- [Complete source-linked article metadata](https://github.com/AbdulHassan0/EnergyBrew/blob/collector-state/state/articles.json)
- [GitHub Actions execution history](https://github.com/AbdulHassan0/EnergyBrew/actions/workflows/live-collector.yml)

## Sources and editorial safeguards

Enabled feeds are eight original EIA, DOE, and European Commission official sources, a DOE Grid Deployment feed, and a Federal Register notices feed.

- Federal Register feeds were originally configured as separate DOE and FERC feeds, but the live API returned overlapping identical documents. The collector now uses a single neutral regulatory feed and deduplicates by canonical URL across source labels and historical state.
- Official Federal Register documents are retained as **date-only regulatory leads**, never as precisely timed breaking news.
- DOE Grid Deployment is reachable but its observed feed items were all older than the 48-hour window on the first run.
- Relevance scores are conservative, explainable keyword-based signals, **not fact-checking**.
- Specialist publisher RSS, such as S&P Global Energy and Oil & Gas Journal, remains disabled absent appropriate commercial collection rights.

## Reliability and deployment

The collector runs **four times daily** in GitHub Actions, at 04:17, 10:17, 16:17, and 22:17 UTC (subject to GitHub scheduling delays). Each hosted run:

1. Checks the repository remains private and runs automated tests.
2. Loads preserved state from the `collector-state` branch.
3. Downloads allowed official RSS feeds and validates publication timestamps.
4. Separates high-signal recent editorial leads from date-only regulatory leads.
5. Deduplicates by canonical URL and persists seven-day article/run history.
6. Saves human-readable reports and downloadable GitHub Actions artifacts.
7. Never publishes, sends emails, or claims the headlines have been fact-checked.

All source-linked research is for editorial consideration; an accessible RSS feed does not grant rights to reproduce copyrighted full text.

## Next milestones

1. Run an uninterrupted seven-day pilot and report actual useful unique daily article volume.
2. Expand permitted specialist feeds and/or licensed news discovery APIs after validating terms and host access.
3. Integrate the separate verified collector with the full Energy TLDR editorial website and approval workflow.
4. Add monitoring for missing scheduled jobs, failure alerts and source freshness by sector.
