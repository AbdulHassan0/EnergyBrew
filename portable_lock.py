"""Portable nonblocking file locks for EnergyBrew research state writers.

POSIX uses flock; Windows uses a one-byte msvcrt region lock. The caller owns
the open file handle and releases the lock by closing it, never unlinking it.
"""
from __future__ import annotations
import os


def lock_exclusive_nonblocking(handle):
    if os.name == "nt":
        import msvcrt
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write("0")
            handle.flush()
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise BlockingIOError("Another EnergyBrew collector owns the state lock") from exc
    else:
        import fcntl
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    return handle
