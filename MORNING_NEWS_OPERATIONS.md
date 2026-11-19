# EnergyBrew morning collection readiness (news logic only)

**Objective:** a reviewable research candidate set ready ahead of the intended
07:00 morning briefing. Nothing is sent, published or automatically approved.

Pilot schedule: **America/Chicago**; timezone is configurable and adjusts for
US daylight saving time. This is NOT an assumption that all future subscriber
deliveries should use Central Time.

- **05:45 local:** monitor overnight sampling and generate an **unfrozen preflight** with `python morning_readiness.py --preflight`; this is the editor’s early review queue, not the final cutoff-complete candidate set.
- **06:10 local (free GitHub mode):** a best-effort publisher RSS scan
  is scheduled with paired CST/CDT UTC entries and a strict actual
  06:05–06:25 local gate. The scan records its completion timestamp;
  if it finishes after 06:30, its output does NOT count as cutoff-ready.
  GitHub may delay or omit cron entirely. GDELT coverage is independent.
- **06:20–06:30 local (continuously hosted mode):** targeted final
  RSS/GDELT collection on a persistent local or hosted worker.
- **06:30 local:** hard research cutoff: no post-cutoff publisher timestamps,
  GDELT first-seen metadata, or press-release feed timestamps in this edition.
  Date-only official notices from the edition date are excluded because their
  availability at 06:30 cannot be established.
- **Story recency:** primary headlines must have a source-supplied timestamp
  or GDELT observation since the preceding day's 06:30 local cutoff. The
  36-hour candidate lookback is kept only for a separate *background context*
  queue. Within the primary queue, stories are marked as overnight (after
  18:00 local) or earlier since the previous cutoff. GDELT time labels are
  observations, NOT verified original publication times.
- **Repeat review:** when a previous frozen RESEARCH file is supplied using
  `--prior-research`, exact recurring URLs and conservative likely same-event
  links are flagged. They are never automatically removed because yesterday's
  research candidate might not actually have been sent.
- **06:30–06:45 local:** use previously collected state only; do not
  fetch publisher feeds postcutoff. Validate source freshness, evaluate
  6-hour GDELT
  sampled-window coverage, rank/deduplicate the six subject categories, and
  produce an immutable **research-only** candidate JSON snapshot.
- **06:45–06:55 local:** source checks, human editorial verification, permissions
  and editorial sign-off belong to a separate later workflow; these are NOT
  implemented as publishing, sending, or an automatic approval decision.
- **07:00 local:** intended product delivery time, **not implemented here**.

Defaults: RSS last connected run ≤90 minutes before cutoff; successful GAL
sample ≤20 minutes before cutoff; RSS minimum connected ratio 80%; an optimistic
upper bound of at least 75% overnight GAL sampled-window coverage. These are
conservative PILOT thresholds, not guarantees of completeness. The measured
coverage upper bound must not be misrepresented as confirmed news recall.

Publisher RSS-timestamped reporting must ground at least one primary research
candidate. GDELT-only discovery is never sufficient for readiness. All
candidates still require human editorial review before any future sending.

Immutable research snapshots require a **persistent shared output volume**.
Separate GitHub Actions runners are ephemeral: the pilot artifacts do not
enforce cross-run uniqueness. Production needs durable daily uniqueness
constraints and transactional storage.

Research window: previous 36 hours ending exactly at 06:30; sufficient for
overnight/previous-day reporting without allowing post-cutoff future leaks.
Reruns cannot rewrite a previously frozen snapshot, even with new article
information. A blocked readiness audit is retained but no frozen research
candidate file is created. The research snapshot is **not an edition approved
for sending**.

Run, with local public-only state:
    python morning_readiness.py --rss state/articles.json \
      --discovery state/discovery.json --releases state/press_releases.json \
      --output output/morning --time-zone America/Chicago

For testing a particular edition:
    python morning_readiness.py --edition-date 2026-11-19

The existing state-publication safety gate remains enforced. No article text,
subscriber information, email-delivery code or newsletter template is touched.

**Free GitHub Actions RSS mode:** `python collector.py` now issues the
15 configured RSS requests with at most five parallel network workers,
while parsing, per-source retries, staging and state persistence remain
source-aware. This reduces head-of-line blocking on slow publisher feeds,
but GitHub's scheduled-run timing is still best-effort and cannot guarantee
overnight GDELT coverage or a 07:00 email. No paid host is required to
use the existing public-repository CI workflows.

**Deployment risks:** Current GitHub Actions schedules have substantial gaps;
the continuously hosted worker is built but not deployed. A reliable 06:20
refresh and cutoff job need a persistent host and external alerting. Morning
readiness alone does not guarantee delivery at 07:00. The human review and
fact verification still need a separate approved workflow.

## Pilot observation: November 19, 2026 morning cutoff

From retained `collector-state` run records at **06:30 CST (12:30 UTC)**:
the successful GDELT samples collectively covered only **35 of 360 minutes**
(approximately **9.79% upper-bound potential time coverage**) over the preceding
six hours. The last successful GAL sample before cutoff was approximately
**31 minutes old**. The latest preceding RSS scan connected **14/15 feeds**.
These are observed collection diagnostics, not a determination of how many
real-world news events occurred. Under current readiness thresholds, this
research edition is **BLOCKED**, not automatically approvable or sendable.

A tested morning preparation workflow alone does not repair this: the
continuous collector must be deployed on a reliable, internet-connected host
with persistent state and independent alerts before claiming dependable
daily 07:00 readiness.

## PJM single-publisher safe recovery

PJM Inside Lines has occasionally returned malformed XML even with HTTP 200.
A live 2026-11-19 GitHub runner verified the regular feed and its same-domain
WordPress Atom alternate parse successfully; RSS2 alternate returned identical
bytes to the primary. The collector now retries the primary three times on
transient failures and uses Atom only on the **last resort fourth request**.
HTTP 429 is never circumvented. Fallback usage, original parse error and
actual endpoint are persisted in source health; success does not imply a
second independent news publisher or permission to redistribute article text.

## Time provenance and editorial cutoff integrity

For every newly observed RSS article, GDELT GAL/DOC discovery or issuer
announcement, the collector now separately records
`first_collector_observed_utc`. This is when EnergyBrew's collection of
that exact URL became available, not the publisher or aggregator's earlier
`pubDate`, `seendate`, or feed metadata. News observed after 06:30 Central
cannot be credited to a 06:30 morning issue even when its upstream timestamp
is older. Legacy links missing a real first-observation date remain
explicitly flagged for editorial review; timestamps are never invented.
