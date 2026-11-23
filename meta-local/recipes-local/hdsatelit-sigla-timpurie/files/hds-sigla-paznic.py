#!/usr/bin/python3
# Copyright (C) 2026 moneasoftware.com & hdsatelit.com
# SPDX-License-Identifier: GPL-2.0-only
"""Own the frame player's descendants until the GUI takes the decoder."""
import ctypes
import fcntl
import os
import select
import signal
import sys
import time


def read(path):
    try:
        with open(path, encoding='ascii', errors='replace') as f:
            return f.read().strip()
    except OSError:
        return ''


def write(path, value):
    with open(path, 'w', encoding='ascii') as f:
        f.write(value + '\n')


def main():
    action, root, player, logo, bind, old = sys.argv[1:]
    state = os.environ.get('HDS_SIGLA_STARE', root + '/run/hds-sigla-timpurie')
    os.makedirs(state, mode=0o700, exist_ok=True)
    if os.path.islink(state) or os.stat(state).st_uid != os.geteuid():
        return 1
    lock = os.open(state + '/lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    stopped = state + '/stop'
    if action == 'stop':
        # A start still in flight must not acquire the decoder after this stop.
        fd = os.open(stopped, os.O_CREAT | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        os.close(fd)
        end = time.monotonic() + 2
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return 0
            except BlockingIOError:
                if time.monotonic() >= end:
                    return 1
                time.sleep(.05)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return 0
    if action == 'refresh':
        # Only the GUI launcher requests a new frame after a completed handoff.
        try:
            os.unlink(stopped)
        except FileNotFoundError:
            pass
    if os.path.exists(stopped):
        return 0
    ready_r, ready_w = os.pipe()
    daemon = os.fork()
    if daemon:
        os.close(ready_w)
        # Only acknowledge startup, never wait for the decoding work.
        if select.select([ready_r], [], [], 1)[0]:
            os.read(ready_r, 1)
        os.close(ready_r)
        return 0
    os.close(ready_r)
    os.setsid()
    null = os.open('/dev/null', os.O_RDWR)
    for fd in (0, 1, 2):
        os.dup2(null, fd)
    os.close(null)
    child = None
    stopping = False

    def stop_signal(signum, frame):
        nonlocal stopping
        stopping = True

    def children(check_status=True):
        result = []
        # Some receiver kernels omit task/children. The private session and
        # held launcher PID identify our descendants using mandatory stat fields.
        with os.scandir('/proc') as entries:
            numbers = [entry.name for entry in entries if entry.name.isdigit()]
        for number in numbers:
            pid = int(number)
            stat = read('/proc/%s/stat' % number).rsplit(')', 1)
            if len(stat) != 2:
                continue
            fields = stat[1].split()
            if len(fields) < 4 or fields[2:4] != [str(child), str(child)]:
                continue
            if fields[0] != 'Z':
                result.append(pid)
            elif pid != child and int(fields[1]) == os.getpid():
                _, status = os.waitpid(pid, os.WNOHANG)
                if status and check_status:
                    raise RuntimeError('frame child failed')
        return result

    def terminate():
        if child is None:
            return
        # The launcher's PID stays reserved (WNOWAIT) even after its fork.
        # Thus this process group can never belong to somebody else's player.
        try:
            os.killpg(child, signal.SIGKILL)
        except ProcessLookupError:
            pass
        # A driver may ignore SIGKILL. Release the lock after a fixed grace.
        end = time.monotonic() + 1
        while time.monotonic() < end:
            try:
                if not children(False):
                    break
            except OSError:
                pass
            time.sleep(.05)

    try:
        signal.signal(signal.SIGTERM, stop_signal)
        signal.signal(signal.SIGINT, stop_signal)
        if ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0):
            raise OSError('subreaper unavailable')
        children()
        if old in ('0', '1'):
            write(bind, '0')
        group_r, group_w = os.pipe()
        child = os.fork()
        if child == 0:
            os.close(group_r)
            os.close(lock)
            os.close(ready_w)
            os.setsid()
            os.write(group_w, b'1')
            os.close(group_w)
            try:
                os.execv(player, [player, logo])
            except OSError:
                os._exit(127)
        os.close(group_w)
        if os.read(group_r, 1) != b'1':
            child = None
            raise RuntimeError('frame group unavailable')
        os.close(group_r)
        os.write(ready_w, b'1')
        os.close(ready_w)
        limit = float(os.environ.get('HDS_SIGLA_TERMEN', '120')) if root else 120
        deadline = time.monotonic() + max(.1, limit)
        while not stopping and not os.path.exists(stopped):
            status = os.waitid(os.P_PID, child, os.WEXITED | os.WNOHANG | os.WNOWAIT)
            if status and (status.si_code != os.CLD_EXITED or status.si_status):
                break
            alive = children()
            if alive and time.monotonic() >= deadline:
                break
            # A successful decoder leaves a frozen frame; do not clear it at 5s.
            time.sleep(.05 if root else .2)
    except (OSError, RuntimeError, ValueError):
        pass
    finally:
        # Restore even if a driver cannot yet release its process.
        if old in ('0', '1'):
            try:
                write(bind, old)
            except OSError:
                pass
        terminate()
        # Never wait on a descendant that is still stuck in the driver.
        while True:
            try:
                pid, _ = os.waitpid(-1, os.WNOHANG)
                if not pid:
                    break
            except ChildProcessError:
                break
        os.close(lock)
    os._exit(0)


if __name__ == '__main__':
    sys.exit(main())
