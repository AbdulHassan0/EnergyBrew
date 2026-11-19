# Render: single persistent EnergyBrew news collector (research only)

**Not deployed merely by this file.** Render app access must be connected in
the current ChatGPT workspace or deployment must be initiated in Render.
Provisioning can incur costs: this requires a paid background worker and disk.
Do not create a free web service or multiple independent Render cron services
as a substitute for durable collection.

## Why one worker

Render cron jobs **cannot attach or read another service's persistent disk**.
EnergyBrew needs a single disk-owning worker with a 5-minute GAL sampling
thread and a morning scheduling thread. This is implemented in
`render_worker.py` and defined declaratively in `render.yaml`. The worker does
not accept HTTP, publish articles, update the website, or send mail.

The Docker image runs Python 3.12 as nonroot UID 10001. Mount `/data` to
one persistent Render disk and ensure it is writable to that UID. The service
fails early if it cannot write. This is separate from the optional systemd
deployment for a directly controlled Linux VPS. **Use one deployment method,
never two simultaneous writers to the same state.**

## Enable in the Render Dashboard

1. Connect GitHub repo `AbdulHassan0/EnergyBrew` to Render.
2. Choose **New > Blueprint** and select the repo's `main` branch.
3. Review `render.yaml`: one **background worker**, **Ohio region**, paid
   `0.5c-512mb` instance and 1 GiB disk mounted at `/data`.
   Confirm the current quoted costs and billing preference before approving.
4. Deploy, then read the worker logs. Subsequent code pushes wait for
   GitHub CI checks to pass before auto-deploying the worker. Check that `/data/render_worker_heartbeat.json`
   and `/data/output/gal-worker/worker_health.json` update as expected.
5. Verify at least one genuine HTTP 200 GDELT poll, index freshness, unique
   payload fingerprint and metadata-only state guard. A successful build is
   not the same as a successful live feed poll.
6. Observe the 05:35, 05:45, 06:24 and 06:38 Central research jobs and
   the `/data/render_schedule.json` ledger. A missed window remains missed.
7. Configure independent external heartbeat alerting, storage backups and
   seven full days of reliable live sampling before claiming production ready.

## Single-worker operating schedule (America/Chicago, DST-aware)

- GAL: every five minutes, continuously; never retroactively fills missed
  GDELT index time. Successful and failed runs are individually measured.
- 05:35: safely refresh publisher RSS metadata.
- 05:45: create an **unfrozen** overnight editorial preview.
- 06:24: refresh publisher RSS before the fixed 06:30 cutoff.
- 06:38: prepare the immutable research-only candidate snapshot if all
  freshness, quorum, cutoff and safety gates pass.

One retry is permitted for transient job failure inside its short window.
The ledger records a job as started **before** execution; process restarts
cannot pretend a job did not start. No retry after a window has closed.
A blocked final result does not silently turn into readiness.

**Data boundaries:** GDELT discovery timestamps are not confirmed article
publication times. The worker collects safe headline/link metadata only.
No copied articles, proprietary content, subscriber information or API keys.
Render workers do not have a public website URL.

**Limits before production:** publisher RSS instability (including PJM),
GDELT feed caching, source-rights verification, no verified seven-day pilot,
unconfigured external monitoring, optional company-release state not collected
on this host, and no controlled synchronization back to the site's research
state. No on-time newsletter delivery is implemented.

Official documentation:
- https://render.com/docs/disks
- https://render.com/docs/cronjobs
- https://render.com/docs/background-workers
- https://render.com/docs/blueprint-spec
