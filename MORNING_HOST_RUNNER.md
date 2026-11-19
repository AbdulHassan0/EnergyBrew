# Persistent morning preparation on the collector host

After deploying the continuously running GDELT collector worker on a persistent
Linux volume, schedule this separate one-shot morning *news-processing* task
at 06:38 in America/Chicago. This is independent from GitHub cron reliability
and never sends newsletters or publishes stories.

At **05:45 Central**, run an *early, unfrozen research preflight* against
the collector's durable history. It shows editors overnight leads already
observed, but it is never treated as a finalized edition:

    docker run --rm --name energybrew-preflight \
      --mount type=bind,source="$(pwd)/energybrew-state",target=/data \
      --entrypoint python energybrew-collector \
      morning_readiness.py --rss /data/articles.json \
      --discovery /data/discovery.json \
      --releases /data/press_releases.json \
      --output /data/morning --preflight

The host should schedule the preflight at 05:45 local and the separate final
runner at 06:38 local. Both use America/Chicago timezone and account for
daylight saving time. Independent heartbeats/alerts are needed because either
run can be missed if the host is unavailable. GitHub Actions has parallel
best-effort pilot schedules but does **not** guarantee these times.

Example manual run, using the same persistent bind mount as the GAL collector:

    docker run --rm --name energybrew-morning \
      --mount type=bind,source="$(pwd)/energybrew-state",target=/data \
      --entrypoint python energybrew-collector \
      morning_host_runner.py --root /data --time-zone America/Chicago

For scheduling on an always-on Linux server, use a systemd timer with
OnCalendar=*-*-* 06:38:00 America/Chicago and a service that executes the
above one-shot container. Enable the timer and supervise failures; this is
not deployed yet. Configure a volume backup and independent monitoring.

The runner obtains its own exclusive morning lock, updates only its separate
RSS state with guarded staging, reads the continuously updated GDELT state,
applies the 06:30 editorial cutoff, and saves a local immutable snapshot when
all freshness and source-quality checks pass. No company article text or
subscriber data is stored. Existing GAL worker data are never modified.

If a collection gate fails, a blocker audit is saved but no new research
snapshot is released. If a run occurs after 06:49 local, it fails visibly
rather than pretending the 07:00 deadline can still be met. If a research
snapshot already exists, differing results cannot overwrite it. A prior-day
research snapshot can flag possible repeats; this is not proof that a story
was actually published.

**Still to deploy:** persistent host, external uptime alerts, supervised
morning service, measured seven-day operation, editorial/factual verification.
The 07:00 email-delivery system is out of scope until expressly authorized.
