# EnergyBrew — Five-minute morning energy newsletter (research preview)

**News-collection status (November 18, 2026): LIVE, WITH GAPS.** Public-source metadata collection has resumed. The last verified hosted run connected 15 of 15 RSS feeds, including Offshore Energy, OilPrice.com, Utility Dive and PJM Inside Lines. GDELT DOC can throttle; earlier GAL sampling gaps remain; the seven-day pilot is incomplete. A public-state safety gate rejects copyrighted text and sensitive fields.

This repository contains both **energy news collection infrastructure** and the [EnergyBrew website preview](https://abdulhassan0.github.io/EnergyBrew/). The web experience is built around **five minutes of energy news with your morning coffee**. It does not yet send subscriber emails or publish independently fact-checked, editorially approved summaries.

## Open EnergyBrew and its live source research

- **[Open EnergyBrew — five-minute morning preview](https://abdulhassan0.github.io/EnergyBrew/)** — responsive edition and searchable research desk with real, unapproved source leads
- **[Unified ranked EnergyBrew Research Desk](https://github.com/AbdulHassan0/EnergyBrew/blob/collector-state/state/desk_latest.md)** — prioritized energy stories with direct publisher links, source provenance and timestamp caveats
- [Daily collection reliability, article volume and scan gaps](https://github.com/AbdulHassan0/EnergyBrew/blob/collector-state/state/metrics_latest.md)
- [Collection health, live-source status and coverage gaps](https://github.com/AbdulHassan0/EnergyBrew/blob/collector-state/state/health_latest.md)
- [Timestamped official stories — last 24 hours](https://github.com/AbdulHassan0/EnergyBrew/blob/collector-state/state/editorial_candidates_24h.json)
- [Government pipeline and regulatory watchlist](https://github.com/AbdulHassan0/EnergyBrew/blob/collector-state/state/regulatory_watch.json)
- [Global news discovery (publisher dates unverified)](https://github.com/AbdulHassan0/EnergyBrew/blob/collector-state/state/research_leads_24h.json)
- [Company/newswire release leads (not independently verified)](https://github.com/AbdulHassan0/EnergyBrew/blob/collector-state/state/releases_leads_24h.json)

## Five-minute newsletter workflow (new)

- **[Approved edition archive](https://abdulhassan0.github.io/EnergyBrew/editions/)** — real approved issues only; empty until the first one passes human editorial verification
- [Morning editorial research queue workflow](https://github.com/AbdulHassan0/EnergyBrew/actions/workflows/morning-editorial.yml) — prepares source-linked, unapproved review draft and email layout; public-repo artifacts are not confidential
- [Human editorial checklist](newsletter/EDITORIAL.md) — original source/date/fact/rights review, summaries, and why-it-matters explanations
- [Newsletter renderer and publisher](newsletter.py) — fails closed for unapproved editions, generates responsive email HTML/plain text and an issue archive
- [Manual one-mailbox email test](https://github.com/AbdulHassan0/EnergyBrew/actions/workflows/newsletter-test-send.yml) — requires an approved issue, configured SMTP secrets, and explicit test-send permission; **no subscriber mailing is enabled**

**Hosting boundary:** GitHub and the collector-state branch are PUBLIC. The running collector stores public-source links/headlines only, with a metadata guard before persistence. Restricted feeds, credentials, confidential editorial material and subscriber data require a separate private workspace and appropriate rights.

## Live services

| Workflow | Function | Scheduled frequency |
|---|---|---|
| [Main official RSS + research pipeline](https://github.com/AbdulHassan0/EnergyBrew/actions/workflows/live-collector.yml) | EIA/DOE/NRC/EU/Federal Register feeds; GDELT DOC queries; GAL sample; press releases; merged research desk; newsroom health and volume reports | Four times daily |
| [Frequent global discovery](https://github.com/AbdulHassan0/EnergyBrew/actions/workflows/frequent-gal.yml) | GDELT rolling Global Article List; preserve discoveries; refresh ranked research desk and reliability scorecard | Every 15 minutes, subject to GitHub delays |

Collector jobs share one GitHub Actions state-writer concurrency group. Writes require a successful metadata safety gate. Staggered schedules help avoid collisions but cannot guarantee complete GDELT rolling-sample coverage.

**Provenance rules:** Original official publisher RSS timestamps, Federal Register publication dates, GDELT index-first-seen timestamps, and press-release feed dates are labeled **differently**. None guarantees truth or publication rights.

The source ranking is intentionally conservative: original official headlines rank above corporate promotional releases. The desk limits company releases and repeated links from one domain, flags low-commercial-value stories, and exposes category gaps. These are editorial research *candidates*, never fact-checked newsletter copy.

## Initial observations, not a reliability guarantee

The earlier November 18, 2026 hosted pilot observed **11 accessible official feeds**, alongside global discovery, press-release feeds, and a working shared state store. A private research desk run identified **55 relevant URL records in retained history**, selected 24 diverse research links across 21 domains, and kept their source classifications separate. Many of those links were **not** independently date-verified; only one high-signal official link was inside the observed 24-hour window.

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
- Build editorially verified five-minute summaries, approved newsletter editions, archives, subscriber signup and email delivery. The website *preview* has already been deployed.

**Current state: public-source RSS and discovery collection is working again, with conservative event deduplication and separate source provenance. Seven-day reliability and publication-grade coverage are not yet established. Engineering work is strictly limited to news collection and logic until the user approves a change.**
