# Free local news collection (optional)

Run EnergyBrew's public-news metadata worker on a computer you already have.
**No paid Render plan, no frontend changes, no subscriber email.**
This does not remotely install or launch anything on your device.

## Windows 10/11, Python 3.12

1. Clone `https://github.com/AbdulHassan0/EnergyBrew`.
2. Open PowerShell in the repository. Run `py -3.12 -m pip install tzdata`
   so Python `zoneinfo` has America/Chicago daylight-saving rules.
3. Start it:
   `powershell -ExecutionPolicy Bypass -File .\deploy\windows\run-energybrew-news.ps1`
4. Keep the PC awake, connected, and running the process. Optionally register
   the script as a Windows Task Scheduler logon task, with restart-on-failure
   and only one instance. This repository does not register the task for you.
5. Check `%LOCALAPPDATA%\EnergyBrew\NewsState\render_worker_heartbeat.json`,
   `output\gal-worker\worker_health.json`, and
   `render_schedule.json` under that state directory.

Linux/macOS with Python 3.12 and timezone data:
`python3 render_worker.py --root ./local-news-state`

The worker samples GDELT approximately every five minutes; separately polls
publisher RSS every two hours and issuer announcements every three hours;
and uses 05:35/05:45/06:24/06:38 America/Chicago research-only morning gates.
It preserves source provenance and records missed windows.

## Limits

Local collection only runs while the computer is awake and connected.
Windows runtime is **not** verified by the Linux CI tests, even though the
cross-platform file-lock branches are implemented. GitHub Actions maintains
a separate `collector-state` history; local results do not sync to it.
Keep the state folder out of the public Git repository. Do not expose secrets.

This collector does **not** automatically fact-check, approve, publish, or
email editions. Reliability remains unproven until observed on a real machine.

## Windows CI evidence

The `collector-daemon-ci.yml` workflow also runs portable locking and
morning scheduling unit tests on an actual standard GitHub-hosted Windows
runner. A passing CI test establishes platform import, path, locking and
offline scheduler compatibility, **not** 24/7 runtime reliability, a live
publisher connection or Task Scheduler/autostart behavior.

## Local pilot health command

After starting the local collector, check health from the repository folder:

`py -3.12 local_pilot_report.py --root "$env:LOCALAPPDATA\EnergyBrew\NewsState"`

This read-only command reports heartbeat age, most recent successful GDELT
sample, publisher feed recency, the final Central morning job, and the upper
bound on 24-hour sampling coverage. A newly started collector will correctly
report that the seven-day pilot is **not** yet complete. Status never means
subscriber email delivery or production approval.

## Optional Windows logon auto-start (explicit opt-in)

**Do not run this on a computer that cannot stay awake overnight and online.**
An interactive Windows sign-in task cannot collect while the user is logged
out, the PC is asleep, disconnected or powered off. It is not a production SLA.

From a PowerShell terminal in the cloned repository:

```powershell
# Preview only: prints the task and makes NO system changes.
.\deploy\windows\install-news-task.ps1

# Only if you want this PC to run the research collector at sign-in:
.\deploy\windows\install-news-task.ps1 -Install -StartNow

# Update the task after moving your clone:
.\deploy\windows\install-news-task.ps1 -Install -Replace

# Remove the task, keeping your historical news state:
.\deploy\windows\install-news-task.ps1 -Remove
```

The script registers for the current signed-in user (no stored password),
uses one instance, restarts after process failures, sets no task runtime
limit and checks Python 3.12 and Central timezone data first. Do not change
its account to SYSTEM because that would switch the per-user state folder.
The installer is only code in the repository until YOU explicitly run it.
The local-health command above verifies observed results rather than
assuming task registration implies successful collection.

## Safeguards for the 06:30 morning cutoff

The local scheduler will not treat the 06:24 publisher refresh as adequate
unless the persisted attempt **started at/after 06:24 and finished by
06:30** America/Chicago. Earlier and slower scans do not satisfy that exact
prerequisite even if they returned HTTP 200. After 07:00 the local pilot
health report additionally requires the actual immutable frozen research
file for that edition—not just an `ok` status in the scheduler ledger.
