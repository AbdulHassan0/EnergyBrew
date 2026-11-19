"""Render-only disk bootstrap; drop root privileges before news collection.

Render attaches a disk at runtime, after Docker image build steps. An image
directory chown alone does not ensure the mounted disk is writable. This
bootstrap touches only the mount root (not recursive historical files) and
executes the real worker as unprivileged UID 10001.
"""
from __future__ import annotations

import json
import os
import pwd
import sys
import tempfile
from pathlib import Path


def prepare_user(root=Path("/data"), user="energybrew"):
    account = pwd.getpwnam(user)
    root = Path(root)
    if os.geteuid() == 0:
        root.mkdir(parents=True, exist_ok=True)
        current = root.stat()
        if current.st_uid == 0:
            os.chown(root, account.pw_uid, account.pw_gid)
        elif current.st_uid != account.pw_uid:
            raise PermissionError(
                "Persistent disk owned by an unexpected account; do not "
                "recursively change preserved news history."
            )
        os.setgroups([])
        os.setgid(account.pw_gid)
        os.setuid(account.pw_uid)
    if os.geteuid() != account.pw_uid:
        raise PermissionError("Render worker did not drop to intended UID")
    # A real file creation test is stronger than relying on os.access alone.
    with tempfile.TemporaryFile(dir=root):
        pass
    return {"uid": os.geteuid(), "mount_path": str(root),
            "disk_write_check": "passed"}


def main(argv=None):
    argv = list(argv if argv is not None else sys.argv[1:])
    summary = prepare_user()
    if argv == ["--smoke"]:
        print(json.dumps(summary))
        return 0
    print(json.dumps({"event": "render_worker_disk_ready", **summary}),
          flush=True)
    os.execvp("python", ["python", "/app/render_worker.py", *argv])


if __name__ == "__main__":
    raise SystemExit(main())
