# EnergyBrew visual system

<!-- Distinct product redesign, November 2026. Source: Impeccable craft-floor and Read-mode guidance. -->

## Design intent
A newspaper folded beside a morning coffee, not a Bloomberg terminal. The product is a newsletter readers can enjoy in five minutes. Use clear editorial hierarchy, a single compelling headline area, restraint in the reading column and a coffee-colored ritual motif.

## Visual world
- Warm oat paper \`#F7F2E9\`, cream \`#FCFAF5\`, espresso ink \`#28211C\`.
- Deep roasted coffee \`#392B25\`, burnt persimmon \`#C75B37\` for intentional emphasis.
- Faded sage \`#556D59\` as quiet secondary detail and source status.
- Serif display: Fraunces (with Georgia fallback). Sans UI: DM Sans (with Arial fallback). Avoid using display type in controls.
- Shapes: rectangular print panels, restrained 1px rules, occasional corner rounding on buttons only, no glass or generic metric cards.
- Logo: confident EnergyBrew wordmark plus one consistent authored cup SVG icon.
- Photography not required. Focus on typography, a single coffee-cup vector device and a large five-minute numeral.
- Motion: a single meaningful reading-progress fill, no entrance animation.
- Information cues: provenance as visible, precise text; no fake publication credentials.

## Surface: / (Read, with Persuade introduction)
### First viewport
Brand masthead; hero promise \`Your daily shot of energy.\`; five-minute coffee ritual artwork; one primary action to open the research edition.

### Main visitor path
1. Understand the five-minute newsletter promise.
2. Preview a small, diverse set of **unapproved** research leads.
3. Mark morning items read, save, or follow source links.
4. Switch to a deeper source-linked desk when desired.
5. Learn how editorial verification and email delivery differ from the existing preview.

### Functional vocabulary
- \`The morning brew\` = short six-link preview, not an approved published issue.
- \`Full research desk\` = ranked source-linked candidate feed with category filters and search.
- Reading progress reflects manually marked stories, not unverified analytics.
- Source links are external and explicit; origin labels show the actual date basis.

### Status and honesty
Make the preview disclaimer and exact refresh date visible. If feed loading fails, report it and provide retry. Old feed snapshots do not become falsely dated as today's edition. Newsletter email signup is visibly not available yet.

## Interaction and responsive
- Mobile-first semantic content order, desktop split hero, single-column reading on phones.
- Controls reachable with keyboard and with 44px-ish hit areas.
- Article headlines remain readable without cramped cards.
- Search/filters only in the full desk view to preserve a focused five-minute reading mode.
- Respect reduced motion and never rely on color alone.

## Non-goals for this build
No working email capture without a real backend, no fake article summaries, no made-up editorial narrative, no stock market charts or mock commodity prices.
