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

## Ready-to-install systemd units for a single Linux/Docker host

These versioned units in `deploy/systemd/` replace manually handwritten cron
entries on a **provisioned, always-on Linux VPS**. They are intentionally NOT
installed by committing to GitHub, do NOT send a newsletter, and will not
fix historical GDELT gaps. Do not enable the older manual Docker daemon at the
same time: one persistent writer per mounted volume.

Run on a Linux server with Docker, systemd, adequate disk, and an
internet connection. The unit files assume an application checkout at
`/opt/energybrew`, a build tagged `energybrew-collector:latest`,
the Docker binary at `/usr/bin/docker`, and a writable persistent state
directory `/opt/energybrew/energybrew-state` owned by container UID 10001.
Adjust the units to real host paths before enabling them.

    cd /opt/energybrew
    mkdir -p energybrew-state
    sudo chown 10001:10001 energybrew-state
    docker build -f Dockerfile.collector -t energybrew-collector:latest .
    sudo cp deploy/systemd/*.service deploy/systemd/*.timer /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable --now energybrew-gal.service
    sudo systemctl enable --now energybrew-rss-refresh.timer \
      energybrew-preflight.timer energybrew-morning.timer
    systemctl list-timers 'energybrew-*'
    journalctl -u energybrew-gal.service -n 40 --no-pager

Schedules are explicit `America/Chicago` (DST-aware):
- **05:35:** safely fetch publisher RSS into the persistent metadata store
- **05:45:** write an unfrozen early morning research preview
- **06:24:** refresh publisher RSS ahead of the fixed 06:30 research cutoff
- **06:38:** run the existing final metadata refresh, gate freshness and freeze
  an immutable research-only candidate snapshot if all conditions pass
- **Every five minutes:** independent continuous GAL collection via the
  persistent `energybrew-gal.service`

If the server misses a timer, `Persistent=false` prevents a belated catch-up
from misrepresenting an on-time research edition. This also means an independent
external monitor MUST detect missed timers and stale heartbeats. A successful
`systemctl` enable is NOT evidence that a 7 a.m. newsletter was prepared.

The host's GAL `discovery.json` stays local: no automatic branch synchronization.
`press_releases.json` is optional in these morning jobs, but if absent,
issuer-announcement leads are NOT collected on this host; that limitation must
be reported. Persistent state backup, off-host monitoring, verified source
rights, Docker image update procedure, and at least seven days of successful
field operation remain required before claiming production readiness.

**Render-like shared-disk limitation:** these units assume one real Linux
host with all scheduled containers mounting the SAME persistent directory.
Cloud services with disk mounts isolated per service cannot reproduce this
layout by starting a separate cron service; the scheduling must instead be
integrated into the single disk-owning service, or a different host chosen.
