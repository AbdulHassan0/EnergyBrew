# EnergyBrew product

<!-- impeccable:product-schema 1 -->

## Platform
web

## Users
Energy-industry readers who want a quick, useful morning catch-up on natural gas, LNG, oil, electricity/power and energy infrastructure. Primary reader persona inferred from the user's industry focus; not yet user-tested.

## Product Purpose
EnergyBrew is a five-minute energy newsletter meant to accompany a morning cup of coffee. Its long-term purpose is a concise, well-sourced digest that highlights the most consequential energy developments without requiring readers to scan dozens of publishers.

## Positioning
A memorable morning ritual where energy markets meet coffee: a short, skimmable briefing built on genuine energy-specialist reporting and transparently attributed source material.

## Operating Context
- Desktop and mobile web, morning reading.
- Hosted frontend on GitHub Pages; private-source collection via GitHub Actions and the collector-state branch.
- Site is currently an **unapproved research preview** rather than a published newsletter or active email subscription.
- Existing visitor interactions: sector exploration, search, save links, follow original sources.

## Capabilities and Constraints
- Site uses plain HTML, CSS and JavaScript; no npm build required.
- Real current lead data comes from site_builder.py and source-linked metadata.
- Story facts, publisher dates and newsletter rights are **not** yet independently verified.
- No live subscriber signup, mailing service, paid plan or editorially approved summary currently exists.
- Research leads may use original publisher RSS dates, date-only regulatory dates, GDELT indexing dates or company release-feed dates; these must remain distinguishable.
- Make a small morning selection easy to read but do not falsely label unapproved leads as a finished curated newsletter.

## Brand Commitments
- Name: **EnergyBrew** (exact capitalization).
- Coffee and energy together; five minutes each morning.
- Clear, human, distinctive rather than generic trading-terminal look.
- Newsletter-first model, drawing inspiration from the utility and cadence of TLDR without copying layouts, assets or code.

## Evidence on Hand
- Real hosted research collector reports and newsroom health diagnostics in collector-state branch.
- Current frontend files: frontend/index.html, frontend/styles.css, frontend/app.js.
- No verified testimonial, signup count, publication history, licensed article body or editorial summary supplied.

## Product Principles
1. Respect the reader's morning: the essentials first and the rest opt-in.
2. Explain where every story came from and what its timestamp actually means.
3. Never make up articles, summaries, publication dates, subscriptions or market-impact claims.
4. Make source access fast and the reading experience inviting.
5. Keep the newsletter promise visible without misrepresenting the research-preview stage.

## Accessibility & Inclusion
Keyboard-operated controls, labeled form elements, generous tap targets, visible focus, reduced-motion support, responsive reading widths, strong contrast.
