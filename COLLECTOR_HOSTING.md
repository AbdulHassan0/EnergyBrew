# Independent GDELT collector worker

This is an **optional news-collection-only** deployment path. It is NOT
deployed yet; the successful GitHub Actions tests do not establish 24/7 uptime.

GitHub scheduled events may be delayed or dropped, even with redundant cron
entries. To achieve a reliable five-minute GAL sample cadence, run the
standard-library Python 3.12 collector as a continuously running process on
an internet-connected Linux machine with a **persistent mounted disk**.

Example Docker setup:

    docker build -f Dockerfile.collector -t energybrew-collector .
    mkdir -p energybrew-state
    sudo chown 10001:10001 energybrew-state
    docker run -d --name energybrew-collector --restart unless-stopped \
      --mount type=bind,source="$(pwd)/energybrew-state",target=/data \
      energybrew-collector

Use a **single** collector writer for each mounted state volume. An exclusive
Linux file lock prevents accidental concurrent worker instances on the same
volume; it does NOT coordinate remote machines or GitHub Actions writers.
The worker currently writes only its own persistent local GDELT discovery
state. No automatic push to the public collector-state GitHub branch and no
unverified automatic publication.

Monitor /data/output/worker_health.json for freshness, errors and consecutive
failures. It marks three consecutive failures critical; an external service
manager or uptime alerting system must monitor the process, since an
unexpected crash can prevent the worker from updating its own heartbeat.
Configure disk backups and host restarts.

Run an isolated one-time sample for testing:

    python collector_daemon.py --state ./state/discovery.json \
      --output ./output/worker --once

For seven-day reliability measurement the collector retains up to 6,500 GAL
run records, sufficient for eight days at the minimum supported 120-second
poll interval. Identical cached GAL RSS payloads are recognized as repeat
observations and receive no extra optimistic coverage-window credit; legacy
runs without a payload fingerprint remain explicitly uncertain.

Every cycle uses the existing GAL parser, rejects stale upstream feeds, and
validates the metadata-only state in a separate staging file BEFORE replacing
persistent state. After acquiring its exclusive lock, a restarted worker discards any abandoned uncommitted staging file without touching its last durable committed state. Unrecoverable state corruption and safety failures stop the
process visibly instead of silently destroying history. The worker never
pretends historical index windows were backfilled.

Remaining work before production adoption: provision a host, validate
permissions/rate limits, configure persistent storage and restart policy,
wire controlled metadata-only synchronization to the website research
pipeline, add external heartbeat alerts, and measure seven consecutive
days of actual running coverage. GitHub cron remains a pilot fallback until
then. A live hosted Docker deployment is NOT claimed.

For a supervised Linux server with daily Central-time RSS preflight and immutable
morning research jobs, see the installable `deploy/systemd/` units and
`MORNING_HOST_RUNNER.md`. Those files are deployment recipes only, not a
live cloud deployment or guaranteed 07:00 delivery.
