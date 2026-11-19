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
