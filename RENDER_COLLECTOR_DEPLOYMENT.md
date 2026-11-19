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

The Docker image runs Python 3.12 as nonroot UID 10001 after a short
root-owned mount bootstrap. `render_entrypoint.py` checks that `/data`
is writable after dropping privileges; it changes ownership of the disk
mount ROOT only when it is root-owned, never recursively alters stored files.
A disk with unexpected ownership or permissions fails visibly at startup. This is separate from the optional systemd
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

- Publisher RSS: one immediate startup scan outside the protected morning
  window, then every two hours; critical source outages back off 20 minutes.
  A separate 05:20–07:15 reserved window prevents nonessential refreshes
  from delaying time-critical research preparation.
- Issuer/newswire release RSS: one research-only refresh at worker startup
  outside the protected morning window, then every three hours. Failures
  retry after 30 minutes and remain labeled degraded; claims are unverified.
- GAL: every five minutes, continuously; never retroactively fills missed
  GDELT index time. Successful and failed runs are individually measured.
- 05:35: safely refresh publisher RSS metadata.
- 05:45: create an **unfrozen** overnight editorial preview.
- 06:24: refresh publisher RSS before the fixed 06:30 cutoff.
  Initial requests use bounded five-thread fanout; failed sources retry
  independently against fresh network responses rather than cached failures.
- 06:38: read the already-completed 06:24 publisher snapshot (NO additional
  RSS network poll) and prepare the immutable research-only candidate snapshot
  if all freshness, quorum, cutoff and safety gates pass. A missing or failed
  06:24 refresh explicitly blocks the morning research freeze.

One retry is permitted for transient job failure inside its short window.
The ledger records a job as started **before** execution; process restarts
cannot pretend a job did not start. No retry after a window has closed.
A blocked final result does not silently turn into readiness.

**Data boundaries:** Issuer announcements are unverified primary-source
claims. They must not be labeled as independently reported facts or sent
without source verification. GDELT discovery timestamps are not confirmed article
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
