# EnergyBrew morning collection readiness (news logic only)

**Objective:** a reviewable research candidate set ready ahead of the intended
07:00 morning briefing. Nothing is sent, published or automatically approved.

Pilot schedule: **America/Chicago**; timezone is configurable and adjusts for
US daylight saving time. This is NOT an assumption that all future subscriber
deliveries should use Central Time.

- **05:45 local:** monitor overnight GDELT sampling and RSS source health; investigate gaps.
- **06:20–06:30 local:** targeted final RSS/GDELT collection on a persistent host.
- **06:30 local:** hard research cutoff: no post-cutoff publisher timestamps,
  GDELT first-seen metadata, or press-release feed timestamps in this edition.
  Date-only official notices from the edition date are excluded because their
  availability at 06:30 cannot be established.
- **06:30–06:45 local:** validate source freshness, evaluate 6-hour GDELT
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

**Deployment risks:** Current GitHub Actions schedules have substantial gaps;
the continuously hosted worker is built but not deployed. A reliable 06:20
refresh and cutoff job need a persistent host and external alerting. Morning
readiness alone does not guarantee delivery at 07:00. The human review and
fact verification still need a separate approved workflow.
