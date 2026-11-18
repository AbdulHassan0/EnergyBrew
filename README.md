# EnergyBrew — Live Energy News Research Collector

**Status: both hosted collection workflows verified running on GitHub Actions (November 18, 2026).**

This private GitHub repository contains Energy TLDR's **live news research infrastructure**. It does not yet host the public newsletter website or send emails. No unverified source is automatically approved for publication.

## Open the latest real-world news

- **[Unified ranked EnergyBrew Research Desk](https://github.com/AbdulHassan0/EnergyBrew/blob/collector-state/state/desk_latest.md)** — prioritized energy stories with direct publisher links, source provenance and timestamp caveats
- [Daily collection reliability, article volume and scan gaps](https://github.com/AbdulHassan0/EnergyBrew/blob/collector-state/state/metrics_latest.md)
- [Collection health, live-source status and coverage gaps](https://github.com/AbdulHassan0/EnergyBrew/blob/collector-state/state/health_latest.md)
- [Timestamped official stories — last 24 hours](https://github.com/AbdulHassan0/EnergyBrew/blob/collector-state/state/editorial_candidates_24h.json)
- [Government pipeline and regulatory watchlist](https://github.com/AbdulHassan0/EnergyBrew/blob/collector-state/state/regulatory_watch.json)
- [Global news discovery (publisher dates unverified)](https://github.com/AbdulHassan0/EnergyBrew/blob/collector-state/state/research_leads_24h.json)
- [Company/newswire release leads (not independently verified)](https://github.com/AbdulHassan0/EnergyBrew/blob/collector-state/state/releases_leads_24h.json)

## Live services

| Workflow | Function | Scheduled frequency |
|---|---|---|
| [Main official RSS + research pipeline](https://github.com/AbdulHassan0/EnergyBrew/actions/workflows/live-collector.yml) | EIA/DOE/NRC/EU/Federal Register feeds; GDELT DOC queries; GAL sample; press releases; merged research desk; newsroom health and volume reports | Four times daily |
| [Frequent global discovery](https://github.com/AbdulHassan0/EnergyBrew/actions/workflows/frequent-gal.yml) | GDELT rolling Global Article List; preserve discoveries; refresh ranked research desk and reliability scorecard | Every 15 minutes, subject to GitHub delays |

Both use the same GitHub Actions concurrency group when writing private historical state, avoiding concurrent modifications of the `collector-state` branch.

**Provenance rules:** Original official publisher RSS timestamps, Federal Register publication dates, GDELT index-first-seen timestamps, and press-release feed dates are labeled **differently**. None guarantees truth or publication rights.

The source ranking is intentionally conservative: original official headlines rank above corporate promotional releases. The desk limits company releases and repeated links from one domain, flags low-commercial-value stories, and exposes category gaps. These are editorial research *candidates*, never fact-checked newsletter copy.

## Initial observations, not a reliability guarantee

The November 18, 2026 hosted pilot observed **11 accessible official feeds**, alongside global discovery, press-release feeds, and a working shared state store. A private research desk run identified **55 relevant URL records in retained history**, selected 24 diverse research links across 21 domains, and kept their source classifications separate. Many of those links were **not** independently date-verified; only one high-signal official link was inside the observed 24-hour window.

The **seven-day operational pilot is incomplete**. GitHub Actions schedules may be late or missed, especially for a rolling 15-minute feed. [The reliability scorecard](https://github.com/AbdulHassan0/EnergyBrew/blob/collector-state/state/metrics_latest.md) is the source of truth rather than these dated figures.

## Developer commands (Python 3.12; no npm)

```bash
python -m unittest discover -s tests -v
python collector.py --state state/articles.json --output output/collector --hours 48
python discovery.py --state state/discovery.json --output output/discovery --max-queries 4
python gal.py --state state/discovery.json --output output/gal
python press_releases.py --state state/press_releases.json --output output/releases
python research_desk.py --rss-state state/articles.json --discovery-state state/discovery.json --releases-state state/press_releases.json --output output/desk
python ops_metrics.py --rss state/articles.json --discovery state/discovery.json --releases state/press_releases.json --output output/operations
```

**Before collecting third-party sources commercially:** confirm permitted automated access, retention, and downstream display rights. Publicly reachable RSS feeds are not automatically licensed for commercial use. Company announcements are issuer claims, and GDELT discovery links require source-date and factual checks.

See [OPERATIONS.md](OPERATIONS.md) for incident response, sampling-gap diagnostics, acceptance criteria, GitHub Actions billing considerations, and remaining production work.

## Still to ship

- Complete an uninterrupted seven-day internet-connected measurement pilot.
- Obtain authorized specialist energy-news feeds/APIs to improve LNG, oil and power coverage.
- Validate original publisher dates for discovery leads and preserve editorial sign-off.
- Move high-volume state from Git commits to a durable database before scale.
- Deploy the full Energy TLDR subscriber website, archive and email delivery workflow separately.

**Current state: live research collection is real; automatic publication-grade energy coverage is not yet established.**
