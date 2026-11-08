# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Filesystem services for the paired HDS web interface.

This module deliberately has no Enigma2 or HTTP dependencies. Paths passed here
are already decoded, receiver-absolute paths. They are never URL-decoded here.
On Linux every traversal and mutation is relative to an open directory fd, with
O_NOFOLLOW. Read aliases are explicitly resolved and reopened; recursive copy
and deletion never follow links. ``root`` provides the same virtual paths in an
isolated test tree. Mutations require the canonical receiver path.
"""

import codecs
import contextlib
import errno
import functools
import gettext
import hashlib
import json
import os
import posixpath
import re
import secrets
import stat
import threading
import time

_ = gettext.gettext


CHUNK_SIZE = 64 * 1024
EDITOR_LIMIT = 1024 * 1024
AUDIT_LIMIT = 256 * 1024
MAX_ITEMS = 100
MAX_UPLOADS = 4
UPLOAD_TTL = 30 * 60
PLAN_TTL = 5 * 60
_PSEUDO = ("/proc", "/sys", "/dev")
_SYSTEM = ("/etc", "/usr", "/bin", "/sbin", "/lib", "/lib32", "/lib64", "/boot")
_PROTECTED = frozenset((
    "/", "/bin", "/boot", "/dev", "/etc", "/home", "/lib", "/lib32",
    "/lib64", "/lost+found", "/media", "/mnt", "/opt", "/proc", "/root",
    "/run", "/sbin", "/srv", "/sys", "/tmp", "/usr", "/var",
    "/etc/enigma2", "/etc/tuxbox", "/usr/bin", "/usr/sbin", "/usr/lib",
    "/usr/share", "/usr/share/enigma2", "/usr/lib/enigma2",
))


class FisiereError(Exception):
    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def _os_error(exc):
    table = {
        errno.ENOENT: ("not_found", _("Fișierul sau dosarul nu mai există."), 404),
        errno.EEXIST: ("exists", _("Există deja un element cu acest nume."), 409),
        errno.EACCES: ("permission", _("Permisiunile nu permit această operație."), 403),
        errno.EPERM: ("permission", _("Permisiunile nu permit această operație."), 403),
        errno.ENOTDIR: ("not_directory", _("Calea nu este un dosar sau conține o legătură simbolică. Deschide ținta legăturii înainte de scriere."), 400),
        errno.EISDIR: ("not_file", _("Calea nu este un fișier obișnuit."), 400),
        errno.ELOOP: ("symlink", _("Legăturile simbolice nu sunt urmărite la scriere. Deschide mai întâi ținta legăturii."), 400),
        errno.ENOSPC: ("no_space", _("Nu mai este spațiu disponibil pe disc."), 409),
        errno.EROFS: ("read_only", _("Sistemul de fișiere este doar pentru citire."), 403),
        errno.ENAMETOOLONG: ("invalid_path", _("Numele sau calea este prea lungă."), 400),
        errno.ENOTEMPTY: ("not_empty", _("Dosarul nu este gol."), 409),
    }
    return FisiereError(*table.get(exc.errno, ("filesystem", _("Operația pe disc nu a reușit."), 500)))


def _api(fn):
    @functools.wraps(fn)
    def wrapped(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except OSError as exc:
            raise _os_error(exc) from exc
    return wrapped


def _under(path, base):
    return path == base or path.startswith(base + "/")


def clean_path(path):
    """Validate one already-decoded absolute path; percent signs stay literal."""
    if not isinstance(path, str) or not path.startswith("/") or len(path) > 4096:
        raise FisiereError("invalid_path", _("Este necesară o cale absolută validă."))
    if "\\" in path or any(ord(c) < 32 or 127 <= ord(c) < 160 or 0xd800 <= ord(c) <= 0xdfff for c in path):
        raise FisiereError("invalid_path", _("Calea conține caractere nepermise."))
    if ".." in path.split("/"):
        raise FisiereError("invalid_path", _("Componentele «..» nu sunt permise."))
    # A leading double slash has special semantics on some operating systems.
    return "/" + "/".join(p for p in path.split("/") if p and p != ".")


def _name(name):
    if not isinstance(name, str) or not name or name in (".", "..") or "/" in name:
        raise FisiereError("invalid_name", _("Alege un nume simplu, fără separatori de cale."))
    clean_path("/" + name)
    if len(name.encode("utf-8")) > 255:
        raise FisiereError("invalid_name", _("Numele este prea lung."))
    return name


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
            getattr(info, "st_mtime_ns", int(info.st_mtime * 1000000000)))


def _same_inode(a, b):
    return (a.st_dev, a.st_ino, stat.S_IFMT(a.st_mode)) == (b.st_dev, b.st_ino, stat.S_IFMT(b.st_mode))


class _Directory:
    """A directory anchor, including a conservative fallback for Windows tests."""
    def __init__(self, core, fd=None, local=None):
        self.core, self.fd, self.local = core, fd, local

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        self.close()

    def path(self, name):
        return os.path.join(self.local, name)

    def info(self, name):
        if self.fd is not None:
            return os.stat(name, dir_fd=self.fd, follow_symlinks=False)
        return os.lstat(self.path(name))

    def exists(self, name):
        try:
            return self.info(name)
        except FileNotFoundError:
            return None

    def names(self):
        return os.listdir(self.fd if self.fd is not None else self.local)

    def open(self, name, flags, mode=0o600):
        flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        if self.fd is not None:
            return os.open(name, flags, mode, dir_fd=self.fd)
        before = self.exists(name)
        if before is not None and stat.S_ISLNK(before.st_mode):
            raise FisiereError("symlink", _("Legăturile simbolice nu sunt urmărite."))
        return os.open(self.path(name), flags | getattr(os, "O_BINARY", 0), mode)

    def child(self, name):
        before = self.info(name)
        if not stat.S_ISDIR(before.st_mode):
            raise FisiereError("symlink" if stat.S_ISLNK(before.st_mode) else "not_directory",
                               _("Dosarul nu poate fi deschis pentru scriere. Deschide mai întâi ținta legăturii simbolice."))
        if self.fd is not None:
            fd = self.open(name, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            if not _same_inode(before, os.fstat(fd)):
                os.close(fd)
                raise FisiereError("conflict", _("Dosarul s-a schimbat. Reîncarcă lista."), 409)
            return _Directory(self.core, fd=fd)
        local = self.path(name)
        self.core._confined(local)
        return _Directory(self.core, local=local)

    def mkdir(self, name, mode=0o755):
        if self.fd is not None:
            os.mkdir(name, mode, dir_fd=self.fd)
        else:
            os.mkdir(self.path(name), mode)

    def unlink(self, name, directory=False):
        fn = os.rmdir if directory else os.unlink
        if self.fd is not None:
            fn(name, dir_fd=self.fd)
        else:
            fn(self.path(name))

    def rename(self, name, target, target_name, no_replace=False):
        if self.fd is not None and target.fd is not None:
            if no_replace:
                # renameat2 makes the collision rule atomic, including for directories.
                # Never fall back to a check followed by an overwriting rename.
                try:
                    import ctypes
                    libc = ctypes.CDLL(None, use_errno=True)
                    renameat2 = libc.renameat2
                    renameat2.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int,
                                         ctypes.c_char_p, ctypes.c_uint)
                    renameat2.restype = ctypes.c_int
                    result = renameat2(self.fd, os.fsencode(name), target.fd, os.fsencode(target_name), 1)
                    if result == 0:
                        return
                    error = ctypes.get_errno()
                    if error not in (errno.ENOSYS, errno.EINVAL, errno.ENOTSUP):
                        raise OSError(error, os.strerror(error))
                except (ImportError, AttributeError):
                    pass
                # Older libc/kernel: link+unlink is atomic against collisions for
                # non-directories. Refuse directory moves rather than overwrite.
                info = self.info(name)
                if stat.S_ISDIR(info.st_mode):
                    raise FisiereError("atomic_unavailable", _("Sistemul nu oferă mutare atomică fără suprascriere pentru dosare. Copiază dosarul și verifică rezultatul înainte de ștergere."), 409)
                os.link(name, target_name, src_dir_fd=self.fd, dst_dir_fd=target.fd, follow_symlinks=False)
                self.unlink(name)
                return
            os.replace(name, target_name, src_dir_fd=self.fd, dst_dir_fd=target.fd)
        else:
            if no_replace:
                # Windows rename already fails atomically if the target exists.
                os.rename(self.path(name), target.path(target_name))
            else:
                os.replace(self.path(name), target.path(target_name))

    def readlink(self, name):
        if self.fd is not None:
            return os.readlink(name, dir_fd=self.fd)
        return os.readlink(self.path(name))

    def symlink(self, value, name):
        if self.fd is not None:
            os.symlink(value, name, dir_fd=self.fd)
        else:
            os.symlink(value, self.path(name))

    def sync(self):
        if self.fd is not None:
            try:
                os.fsync(self.fd)
            except OSError as exc:
                if exc.errno not in (errno.EINVAL, errno.ENOTSUP, errno.EROFS):
                    raise


class FisiereCore:
    def __init__(self, root="/", recordings_path=None,
                 shortcuts_path="/etc/enigma2/hds-fisiere-scurtaturi.json",
                 audit_path="/home/root/logs/hds-fisiere.log"):
        self.root = os.path.realpath(os.path.abspath(root))
        self.recordings_path = recordings_path
        self.shortcuts_path = clean_path(shortcuts_path)
        self.audit_path = clean_path(audit_path)
        self._anchored = os.open in getattr(os, "supports_dir_fd", ()) and hasattr(os, "O_NOFOLLOW")
        self._lock = threading.RLock()
        self._plans = {}
        self._uploads = {}

    def _confined(self, local):
        resolved = os.path.realpath(local)
        try:
            inside = os.path.commonpath((self.root, resolved)) == self.root
        except ValueError:
            inside = False
        if not inside:
            raise FisiereError("outside_root", _("Calea iese din rădăcina permisă."), 403)

    def _write_allowed(self, path):
        path = clean_path(path)
        if any(_under(path, base) for base in _PSEUDO):
            raise FisiereError("protected", _("Scrierea în /proc, /sys și /dev nu este permisă."), 403)
        return path

    def _destructive_allowed(self, path):
        path = self._write_allowed(path)
        if path in _PROTECTED:
            raise FisiereError("protected", _("Rădăcina și dosarele de bază ale sistemului sunt protejate."), 403)
        return path

    def _write_anchor_allowed(self, directory):
        """Also reject bind aliases of the receiver's pseudo filesystems.

        Device identities are meaningful only against the real receiver root;
        synthetic /proc directories in a test tree are ordinary test files.
        """
        if directory.fd is None or self.root != os.path.abspath(os.path.sep):
            return
        device = os.fstat(directory.fd).st_dev
        root_device = os.stat(self.root, follow_symlinks=False).st_dev
        for base in ("/proc", "/sys", "/dev", "/dev/pts", "/dev/shm"):
            try:
                info = os.stat(base, follow_symlinks=False)
                if stat.S_ISDIR(info.st_mode) and info.st_dev != root_device and device == info.st_dev:
                    raise FisiereError("protected", _("Scrierea în sistemele de fișiere /proc, /sys și /dev, inclusiv prin aliasuri, nu este permisă."), 403)
            except FileNotFoundError:
                continue

    def _directory(self, path, write=False):
        path = self._write_allowed(path) if write else clean_path(path)
        if self._anchored:
            fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0))
            current = _Directory(self, fd=fd)
        else:
            current = _Directory(self, local=self.root)
        try:
            for part in path.strip("/").split("/") if path != "/" else ():
                following = current.child(part)
                current.close()
                current = following
            if write:
                self._write_anchor_allowed(current)
            return current
        except BaseException:
            current.close()
            raise

    @_api
    def resolve_path(self, path):
        """Resolve read aliases in the virtual receiver tree, then reopen by fd.

        Absolute symlink targets refer to the receiver root, including when root
        is an isolated test tree. Resolving never authorizes writes via an alias.
        """
        path = clean_path(path)
        pending = path.strip("/").split("/") if path != "/" else []
        resolved, links = [], 0
        while pending:
            part = pending.pop(0)
            if part in ("", "."):
                continue
            if part == "..":
                if resolved:
                    resolved.pop()
                continue
            _name(part)
            with self._directory("/" + "/".join(resolved)) as parent:
                info = parent.info(part)
                if stat.S_ISLNK(info.st_mode):
                    links += 1
                    if links > 40:
                        raise FisiereError("symlink_loop", _("Legăturile simbolice formează o buclă."))
                    target = parent.readlink(part)
                    if len(target) > 4096 or "\\" in target or any(ord(c) < 32 or 127 <= ord(c) < 160 for c in target):
                        raise FisiereError("invalid_path", _("Legătura simbolică are o țintă nepermisă."))
                    if target.startswith("/"):
                        resolved = []
                    pending = target.split("/") + pending
                    continue
                if pending and not stat.S_ISDIR(info.st_mode):
                    raise FisiereError("not_directory", _("O componentă a căii nu este un dosar."))
            resolved.append(part)
        return "/" + "/".join(resolved)

    @contextlib.contextmanager
    def _parent(self, path, write=False):
        path = self._write_allowed(path) if write else clean_path(path)
        if path == "/":
            raise FisiereError("protected", _("Rădăcina este protejată."), 403)
        with self._directory(posixpath.dirname(path), write=write) as directory:
            yield directory, posixpath.basename(path), path

    def _ensure_directory(self, path):
        """Create only application-owned support paths, without traversing links."""
        path = self._write_allowed(path)
        current = self._directory("/")
        try:
            for part in path.strip("/").split("/") if path != "/" else ():
                self._write_anchor_allowed(current)
                try:
                    following = current.child(part)
                except FileNotFoundError:
                    current.mkdir(part, 0o755)
                    following = current.child(part)
                current.close()
                current = following
        finally:
            current.close()

    @staticmethod
    def _cancelled(cancelled):
        if cancelled and cancelled():
            raise FisiereError("cancelled", _("Operația a fost oprită."), 409)

    @staticmethod
    def _progress(progress, state, path):
        if progress:
            progress({"bytes": state["bytes"], "files": state["files"], "current": path, "path": path})

    def _audit(self, operation, paths, outcome="ok"):
        # Never log file contents, editor text, shortcut labels, request bodies or errors.
        try:
            if paths and all(p in (self.audit_path, self.audit_path + ".1") for p in paths):
                # Reading or editing the journal must not change its own version.
                return
            safe = lambda value: "".join(c if ord(c) >= 32 and not 127 <= ord(c) < 160 else "?" for c in str(value))[:4096]
            record = {"time": int(time.time()), "operation": safe(operation)[:48],
                      "paths": [safe(p)[:512] for p in paths[:32]], "result": safe(outcome)[:32]}
            data = (json.dumps(record, ensure_ascii=True, separators=(",", ":")) + "\n").encode("ascii")
            with self._lock:
                self._ensure_directory(posixpath.dirname(self.audit_path))
                with self._parent(self.audit_path, write=True) as (parent, name, unused):
                    info = parent.exists(name)
                    if info is not None and not stat.S_ISREG(info.st_mode):
                        return
                    if info is not None and info.st_size + len(data) > AUDIT_LIMIT:
                        parent.rename(name, parent, name + ".1")
                    fd = parent.open(name, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
                    try:
                        os.write(fd, data)
                    finally:
                        os.close(fd)
        except (OSError, FisiereError, ValueError):
            # A full/read-only log partition must not turn a completed operation into an error.
            pass

    @_api
    def list_directory(self, path, offset=0, limit=100):
        requested_path = clean_path(path)
        path = self.resolve_path(requested_path)
        try:
            offset, limit = int(offset), int(limit)
        except (ValueError, TypeError):
            raise FisiereError("pagination", _("Pagina solicitată nu este validă."))
        if offset < 0 or limit < 1 or limit > 500:
            raise FisiereError("pagination", _("Pagina trebuie să conțină între 1 și 500 de elemente."))
        entries = []
        with self._directory(path) as directory:
            for name in directory.names():
                try:
                    info = directory.info(name)
                except FileNotFoundError:
                    continue
                kind = ("directory" if stat.S_ISDIR(info.st_mode) else "file" if stat.S_ISREG(info.st_mode)
                        else "symlink" if stat.S_ISLNK(info.st_mode) else "other")
                entry = {"name": name, "path": posixpath.join(path, name), "type": kind,
                         "size": info.st_size, "mtime": info.st_mtime,
                         "mode": "%04o" % stat.S_IMODE(info.st_mode),
                         "uid": getattr(info, "st_uid", 0), "gid": getattr(info, "st_gid", 0)}
                if kind == "symlink":
                    try:
                        entry["link_target"] = directory.readlink(name)
                        entry["resolved_path"] = self.resolve_path(entry["path"])
                        if entry["resolved_path"] == "/":
                            entry["is_directory"] = True
                        else:
                            with self._parent(entry["resolved_path"]) as (link_parent, link_name, unused):
                                entry["is_directory"] = stat.S_ISDIR(link_parent.info(link_name).st_mode)
                    except (OSError, FisiereError):
                        entry.setdefault("link_target", "")
                        entry["is_directory"] = False
                entries.append(entry)
        entries.sort(key=lambda entry: (entry["type"] != "directory", entry["name"].casefold(), entry["name"]))
        total = len(entries)
        self._audit("list", [path])
        return {"path": path, "requested_path": requested_path,
                "parent": posixpath.dirname(path) if path != "/" else None,
                "entries": entries[offset:offset + limit], "total": total,
                "offset": offset, "limit": limit, "has_more": offset + limit < total}

    def _paths(self, items):
        if not isinstance(items, (list, tuple)) or not items or len(items) > MAX_ITEMS:
            raise FisiereError("items", _("Selectează între 1 și 100 de elemente."))
        result = []
        for item in items:
            path = clean_path(item.get("path") if isinstance(item, dict) else item)
            if path not in result:
                result.append(path)
        return result

    def _copy_entry(self, source, name, target, target_name, path, target_path, state, progress, cancelled):
        self._cancelled(cancelled)
        info = source.info(name)
        if target.exists(target_name) is not None:
            raise FisiereError("exists", _("Există deja un element cu acest nume."), 409)
        made = False
        try:
            if stat.S_ISLNK(info.st_mode):
                target.symlink(source.readlink(name), target_name)
                made = True
            elif stat.S_ISDIR(info.st_mode):
                target.mkdir(target_name, 0o700)
                made = True
                with source.child(name) as child_source, target.child(target_name) as child_target:
                    self._write_anchor_allowed(child_target)
                    for child in child_source.names():
                        # Reject unusual names consistently with the public path boundary.
                        _name(child)
                        self._copy_entry(child_source, child, child_target, child,
                                         posixpath.join(path, child), posixpath.join(target_path, child),
                                         state, progress, cancelled)
                    self._attributes(child_target.fd, info, child_target.local)
                    child_target.sync()
            elif stat.S_ISREG(info.st_mode):
                input_fd = source.open(name, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
                try:
                    if not _same_inode(info, os.fstat(input_fd)):
                        raise FisiereError("conflict", _("Fișierul sursă s-a schimbat."), 409)
                    output_fd = target.open(target_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                    made = True
                    try:
                        while True:
                            self._cancelled(cancelled)
                            chunk = os.read(input_fd, CHUNK_SIZE)
                            if not chunk:
                                break
                            self._write_all(output_fd, chunk)
                            state["bytes"] += len(chunk)
                            self._progress(progress, state, path)
                        if _identity(info) != _identity(os.fstat(input_fd)):
                            raise FisiereError("conflict", _("Fișierul sursă s-a schimbat în timpul copierii."), 409)
                        self._attributes(output_fd, info)
                        os.fsync(output_fd)
                    finally:
                        os.close(output_fd)
                finally:
                    os.close(input_fd)
            else:
                raise FisiereError("special_file", _("Dispozitivele, socketurile și conductele nu pot fi copiate."))
            state["files"] += 1
            self._progress(progress, state, path)
        except BaseException:
            if made:
                try:
                    self._remove_entry(target, target_name, None)
                except (OSError, FisiereError):
                    pass
            raise

    @staticmethod
    def _write_all(fd, data):
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError(errno.EIO, "short write")
            view = view[written:]

    @staticmethod
    def _attributes(fd, info, local=None):
        if fd is not None:
            if hasattr(os, "fchown"):
                current = os.fstat(fd)
                if (current.st_uid, current.st_gid) != (info.st_uid, info.st_gid):
                    os.fchown(fd, info.st_uid, info.st_gid)
            if hasattr(os, "fchmod"):
                os.fchmod(fd, stat.S_IMODE(info.st_mode))
        elif local:
            os.chmod(local, stat.S_IMODE(info.st_mode))

    def _remove_entry(self, parent, name, cancelled):
        self._cancelled(cancelled)
        self._write_anchor_allowed(parent)
        info = parent.info(name)
        if stat.S_ISDIR(info.st_mode):
            with parent.child(name) as child:
                self._write_anchor_allowed(child)
                parent_device = os.fstat(parent.fd).st_dev if parent.fd is not None else os.stat(parent.local).st_dev
                if info.st_dev != parent_device:
                    raise FisiereError("mount_point", _("Punctele de montare nu pot fi șterse. Selectează conținutul lor după ce deschizi discul."), 403)
                for entry in child.names():
                    self._remove_entry(child, entry, cancelled)
            # Never follow a swapped symlink: rmdir either removes the directory or fails.
            if not _same_inode(info, parent.info(name)):
                raise FisiereError("conflict", _("Dosarul s-a schimbat în timpul operației."), 409)
            parent.unlink(name, directory=True)
        else:
            if not _same_inode(info, parent.info(name)):
                raise FisiereError("conflict", _("Elementul s-a schimbat în timpul operației."), 409)
            parent.unlink(name)

    @_api
    def operate(self, action, items=None, destination=None, name=None, mode=None,
                progress=None, cancelled=None):
        if action not in ("copy", "move", "rename", "mkdir", "newfile", "chmod"):
            raise FisiereError("action", _("Operația solicitată nu este disponibilă."))
        state = {"bytes": 0, "files": 0}
        results, errors = [], []
        if action in ("mkdir", "newfile"):
            destination = self._write_allowed(destination)
            name = _name(name)
            path = posixpath.join(destination, name)
            with self._directory(destination, write=True) as parent:
                if action == "mkdir":
                    parent.mkdir(name)
                else:
                    fd = parent.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
                    os.close(fd)
                parent.sync()
            self._audit(action, [path])
            return {"action": action, "results": [{"path": path}], "errors": [], "cancelled": False}
        paths = self._paths(items)
        if name is not None:
            name = _name(name)
            if len(paths) != 1:
                raise FisiereError("items", _("Un nume nou poate fi folosit pentru un singur element."))
        if action == "rename" and (len(paths) != 1 or name is None):
            raise FisiereError("items", _("Redenumirea necesită un element și un nume nou."))
        if action in ("copy", "move") and destination is None:
            raise FisiereError("destination", _("Alege dosarul destinație."))
        if destination is not None:
            destination = self._write_allowed(destination)
        if action == "chmod":
            try:
                parsed_mode = int(mode, 8) if isinstance(mode, str) else int(mode)
            except (TypeError, ValueError):
                raise FisiereError("mode", _("Permisiunile trebuie scrise în format octal, de exemplu 0755."))
            if parsed_mode < 0 or parsed_mode > 0o7777:
                raise FisiereError("mode", _("Permisiunile nu sunt valide."))
        # Validate every destructive source before starting a batch.
        for path in paths:
            if action in ("move", "rename"):
                self._destructive_allowed(path)
            elif action == "chmod":
                self._write_allowed(path)
        was_cancelled = False
        for path in paths:
            try:
                self._cancelled(cancelled)
                with self._parent(path, write=action != "copy") as (source, source_name, unused):
                    if action == "chmod":
                        info = source.info(source_name)
                        if not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
                            raise FisiereError("special_file", _("Permisiunile pot fi schimbate numai pentru fișiere și dosare obișnuite."))
                        flags = os.O_RDONLY | (getattr(os, "O_DIRECTORY", 0) if stat.S_ISDIR(info.st_mode) else 0)
                        fd = source.open(source_name, flags)
                        try:
                            self._write_anchor_allowed(_Directory(self, fd=fd))
                            if not _same_inode(info, os.fstat(fd)):
                                raise FisiereError("conflict", _("Elementul s-a schimbat."), 409)
                            if hasattr(os, "fchmod"):
                                os.fchmod(fd, parsed_mode)
                            else:
                                os.chmod(source.path(source_name), parsed_mode)
                        finally:
                            os.close(fd)
                        results.append({"path": path, "mode": "%04o" % parsed_mode})
                    else:
                        dest_dir = destination if destination is not None else posixpath.dirname(path)
                        dest_name = name or source_name
                        dest_path = self._write_allowed(posixpath.join(dest_dir, dest_name))
                        if path == dest_path or _under(dest_path, path):
                            raise FisiereError("destination", _("Destinația nu poate fi elementul sursă sau un subdosar al lui."))
                        with self._directory(dest_dir, write=True) as target:
                            if target.exists(dest_name) is not None:
                                raise FisiereError("exists", _("Există deja un element cu acest nume."), 409)
                            if action == "copy":
                                self._copy_entry(source, source_name, target, dest_name, path, dest_path,
                                                 state, progress, cancelled)
                            else:
                                try:
                                    source.rename(source_name, target, dest_name, no_replace=True)
                                except (OSError, FisiereError) as exc:
                                    streamed = (isinstance(exc, OSError) and exc.errno in (errno.EXDEV, errno.ENOTSUP, errno.ENOSYS)) or (isinstance(exc, FisiereError) and exc.code == "atomic_unavailable")
                                    if not streamed:
                                        raise
                                    self._copy_entry(source, source_name, target, dest_name, path, dest_path,
                                                     state, progress, cancelled)
                                    self._remove_entry(source, source_name, cancelled)
                            target.sync()
                        results.append({"path": path, "destination": dest_path})
                self._audit(action, [path] + ([dest_path] if action != "chmod" else []))
            except (FisiereError, OSError) as exc:
                error = _os_error(exc) if isinstance(exc, OSError) else exc
                errors.append({"path": path, "code": error.code, "message": error.message})
                self._audit(action, [path], error.code)
                if error.code == "cancelled":
                    was_cancelled = True
                    break
        return {"action": action, "results": results, "errors": errors, "cancelled": was_cancelled,
                "bytes": state["bytes"], "files": state["files"]}

    @_api
    def plan_delete(self, paths):
        paths = self._paths(paths)
        # A parent selection subsumes its children.
        paths = [p for p in paths if not any(p != q and _under(p, q) for q in paths)]
        identities = {}
        for path in paths:
            self._destructive_allowed(path)
            with self._parent(path, write=True) as (parent, name, unused):
                info = parent.info(name)
                if stat.S_ISDIR(info.st_mode):
                    with parent.child(name) as child:
                        self._write_anchor_allowed(child)
                        parent_device = os.fstat(parent.fd).st_dev if parent.fd is not None else os.stat(parent.local).st_dev
                        if info.st_dev != parent_device:
                            raise FisiereError("mount_point", _("Punctele de montare nu pot fi șterse. Selectează conținutul lor după ce deschizi discul."), 403)
                identities[path] = _identity(info)
        now = time.time()
        token = secrets.token_urlsafe(24)
        with self._lock:
            self._plans = {key: value for key, value in self._plans.items() if value["expires"] > now}
            if len(self._plans) >= 32:
                oldest = min(self._plans, key=lambda key: self._plans[key]["expires"])
                del self._plans[oldest]
            self._plans[token] = {"paths": paths, "identities": identities, "expires": now + PLAN_TTL}
        system = any(any(_under(p, base) for base in _SYSTEM) for p in paths)
        if any(_under(p, "/boot") for p in paths):
            warning = _("Fișierele din /boot pornesc nucleul receptorului. Ștergerea lor poate împiedica pornirea și poate cere rescrierea imaginii.")
        elif any(_under(p, "/etc") for p in paths):
            warning = _("Ștergi configurări ale sistemului. Se pot pierde canalele, accesul la rețea ori pornirea serviciilor receptorului.")
        elif system:
            warning = _("Ștergi programe sau fișiere ale sistemului. Pluginurile, interfața ori pornirea receptorului pot înceta să funcționeze.")
        else:
            warning = _("Ștergerea este definitivă, inclusiv pentru conținutul dosarelor selectate.")
        return {"token": token, "paths": paths, "expires": now + PLAN_TTL,
                "warning": warning,
                "system": system}

    @_api
    def execute_delete(self, token, progress=None, cancelled=None):
        if not isinstance(token, str):
            raise FisiereError("confirmation", _("Confirmarea ștergerii nu este validă."), 409)
        with self._lock:
            plan = self._plans.pop(token, None)
        if not plan or plan["expires"] <= time.time():
            raise FisiereError("confirmation", _("Confirmarea a expirat sau a fost deja folosită. Verifică din nou selecția."), 409)
        # Check the complete plan before removing its first item.
        for path in plan["paths"]:
            self._destructive_allowed(path)
            with self._parent(path, write=True) as (parent, name, unused):
                if _identity(parent.info(name)) != plan["identities"][path]:
                    raise FisiereError("conflict", _("Selecția s-a schimbat. Confirmă din nou ștergerea."), 409)
        results, errors = [], []
        stopped = False
        for path in plan["paths"]:
            try:
                with self._parent(path, write=True) as (parent, name, unused):
                    self._remove_entry(parent, name, cancelled)
                    parent.sync()
                results.append({"path": path})
                self._audit("delete", [path])
                if progress:
                    progress({"files": len(results), "current": path})
            except (FisiereError, OSError) as exc:
                error = _os_error(exc) if isinstance(exc, OSError) else exc
                errors.append({"path": path, "code": error.code, "message": error.message})
                self._audit("delete", [path], error.code)
                if error.code == "cancelled":
                    stopped = True
                    break
        return {"action": "delete", "results": results, "errors": errors, "cancelled": stopped}

    def _read_regular(self, parent, name, limit=None):
        before = parent.info(name)
        if not stat.S_ISREG(before.st_mode):
            raise FisiereError("not_file", _("Este necesar un fișier obișnuit; legăturile simbolice nu sunt urmărite."))
        if limit is not None and before.st_size > limit:
            raise FisiereError("too_large", _("Editorul acceptă fișiere de cel mult 1 MiB."), 413)
        fd = parent.open(name, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
        try:
            opened = os.fstat(fd)
            if not _same_inode(before, opened):
                raise FisiereError("conflict", _("Fișierul s-a schimbat. Reîncarcă-l."), 409)
            chunks, size = [], 0
            while True:
                chunk = os.read(fd, CHUNK_SIZE)
                if not chunk:
                    break
                size += len(chunk)
                if limit is not None and size > limit:
                    raise FisiereError("too_large", _("Editorul acceptă fișiere de cel mult 1 MiB."), 413)
                chunks.append(chunk)
            if _identity(opened) != _identity(os.fstat(fd)):
                raise FisiereError("conflict", _("Fișierul s-a schimbat în timpul citirii."), 409)
            return b"".join(chunks), opened
        finally:
            os.close(fd)

    @staticmethod
    def _text(raw):
        encoding, bom, body = "utf-8", b"", raw
        for mark, codec in ((codecs.BOM_UTF32_LE, "utf-32-le"), (codecs.BOM_UTF32_BE, "utf-32-be"),
                            (codecs.BOM_UTF8, "utf-8"), (codecs.BOM_UTF16_LE, "utf-16-le"),
                            (codecs.BOM_UTF16_BE, "utf-16-be")):
            if raw.startswith(mark):
                encoding, bom, body = codec, mark, raw[len(mark):]
                break
        try:
            text = body.decode(encoding)
        except UnicodeDecodeError:
            if bom:
                raise FisiereError("encoding", _("Codificarea fișierului nu este validă."))
            encoding = "latin-1"
            text = body.decode(encoding)
        if any((ord(c) < 32 and c not in "\t\r\n\f") or 127 <= ord(c) < 160 for c in text):
            raise FisiereError("binary", _("Fișierul conține date binare și nu poate fi editat ca text."))
        endings = re.findall(r"\r\n|\r|\n", text)
        kinds = set(endings)
        eol = "mixed" if len(kinds) > 1 else {"\n": "lf", "\r\n": "crlf", "\r": "cr"}.get(next(iter(kinds), ""), "none")
        return text, {"encoding": encoding, "bom": bool(bom), "eol": eol}, bom

    @_api
    def editor_read(self, path):
        path = self.resolve_path(path)
        with self._parent(path) as (parent, name, path):
            raw, info = self._read_regular(parent, name, EDITOR_LIMIT)
        text, format_info, unused = self._text(raw)
        self._audit("editor_read", [path])
        return {"path": path, "text": text, "version": hashlib.sha256(raw).hexdigest(),
                "format": format_info, "size": len(raw), "mode": "%04o" % stat.S_IMODE(info.st_mode)}

    def _temporary(self, parent):
        for unused in range(20):
            name = ".hds-fisiere-" + secrets.token_hex(12) + ".tmp"
            try:
                return name, parent.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                continue
        raise FisiereError("temporary", _("Nu se poate crea un fișier temporar."), 500)

    def _backup(self, parent, name, path, raw, info):
        if not any(_under(path, base) for base in _SYSTEM) or name.endswith(".hds-inainte"):
            return
        backup_name, fd = self._temporary(parent)
        try:
            self._write_all(fd, raw)
            self._attributes(fd, info)
            os.fsync(fd)
            os.close(fd)
            fd = None
            parent.rename(backup_name, parent, name + ".hds-inainte")
            parent.sync()
        finally:
            if fd is not None:
                os.close(fd)
            try:
                parent.unlink(backup_name)
            except FileNotFoundError:
                pass

    def _replace_bytes(self, parent, name, path, data, expected=None, old_raw=None, info=None):
        temp_name, fd = self._temporary(parent)
        try:
            self._write_all(fd, data)
            if info is not None:
                self._attributes(fd, info)
            elif hasattr(os, "fchmod"):
                os.fchmod(fd, 0o644)
            os.fsync(fd)
            os.close(fd)
            fd = None
            current = parent.exists(name)
            if expected is None:
                if current is not None:
                    raise FisiereError("conflict", _("Destinația a apărut între timp. Reîncarcă lista."), 409)
            elif current is None or _identity(current) != expected:
                raise FisiereError("conflict", _("Fișierul s-a schimbat. Reîncarcă-l înainte de salvare."), 409)
            if info is not None and old_raw is not None:
                self._backup(parent, name, path, old_raw, info)
                if _identity(parent.info(name)) != expected:
                    raise FisiereError("conflict", _("Fișierul s-a schimbat în timpul salvării. Reîncarcă-l."), 409)
            parent.rename(temp_name, parent, name, no_replace=expected is None)
            parent.sync()
        finally:
            if fd is not None:
                os.close(fd)
            try:
                parent.unlink(temp_name)
            except FileNotFoundError:
                pass

    @_api
    def editor_save(self, path, text, version, format=None):
        """Atomically save against a SHA-256 version, retaining encoding and EOL.

        Mixed EOL is lossless for edits with an unchanged line count, including
        textarea-normalized LF input. Line insertions/deletions are refused.
        ``format`` is informational; the original file determines its encoding.
        """
        path = self._write_allowed(path)
        if not isinstance(text, str) or not isinstance(version, str) or re.fullmatch(r"[0-9a-f]{64}", version) is None:
            raise FisiereError("editor", _("Textul sau versiunea editorului nu este validă."))
        if len(text) > EDITOR_LIMIT:
            raise FisiereError("too_large", _("Editorul acceptă fișiere de cel mult 1 MiB."), 413)
        with self._lock, self._parent(path, write=True) as (parent, name, unused):
            raw, info = self._read_regular(parent, name, EDITOR_LIMIT)
            if not secrets.compare_digest(hashlib.sha256(raw).hexdigest(), version):
                raise FisiereError("conflict", _("Fișierul a fost modificat în altă parte. Reîncarcă-l înainte de salvare."), 409)
            original, format_info, bom = self._text(raw)
            if format_info["eol"] == "mixed":
                # A browser textarea normalizes CRLF to LF. Preserve the exact
                # original terminator of every line when its line count stays
                # stable. Refuse insertions/deletions rather than guessing which
                # original terminators belong to newly arranged lines.
                endings = re.findall(r"\r\n|\r|\n", original)
                parts = re.split(r"\r\n|\r|\n", text)
                if len(parts) != len(endings) + 1:
                    raise FisiereError("mixed_newlines", _("Fișierul are terminatori de linie amestecați. Editorul păstrează formatul pentru modificări cu același număr de linii; pentru adăugarea sau ștergerea liniilor folosește un editor care păstrează fiecare terminator."), 409)
                text = "".join(part + ending for part, ending in zip(parts, endings)) + parts[-1]
            if any((ord(c) < 32 and c not in "\t\r\n\f") or 127 <= ord(c) < 160 for c in text):
                raise FisiereError("binary", _("Textul conține caractere binare nepermise."))
            if format_info["eol"] in ("lf", "crlf", "cr"):
                ending = {"lf": "\n", "crlf": "\r\n", "cr": "\r"}[format_info["eol"]]
                text = re.sub(r"\r\n|\r|\n", lambda unused: ending, text)
            try:
                data = bom + text.encode(format_info["encoding"])
            except UnicodeEncodeError:
                raise FisiereError("encoding", _("Unele caractere nu pot fi reprezentate în codificarea originală."))
            if len(data) > EDITOR_LIMIT:
                raise FisiereError("too_large", _("Editorul acceptă fișiere de cel mult 1 MiB."), 413)
            if data != raw:
                self._replace_bytes(parent, name, path, data, _identity(info), raw, info)
        self._audit("editor_save", [path])
        return {"path": path, "text": text, "version": hashlib.sha256(data).hexdigest(),
                "format": format_info, "size": len(data), "mode": "%04o" % stat.S_IMODE(info.st_mode)}

    @_api
    def open_download(self, path):
        path = self.resolve_path(path)
        if ((path.startswith("/proc/") and posixpath.basename(path) in ("mem", "kcore", "kmsg", "sysrq-trigger", "pagemap"))
                or posixpath.basename(path) in ("trace_pipe", "trace_pipe_raw")):
            raise FisiereError("unsafe_stream", _("Acest flux special al nucleului nu poate fi descărcat din interfața web."), 403)
        with self._parent(path) as (parent, name, path):
            before = parent.info(name)
            if not stat.S_ISREG(before.st_mode):
                raise FisiereError("not_file", _("Numai fișierele obișnuite pot fi descărcate."))
            fd = parent.open(name, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
            try:
                info = os.fstat(fd)
                if not _same_inode(before, info):
                    raise FisiereError("conflict", _("Fișierul s-a schimbat."), 409)
                stream = os.fdopen(fd, "rb")
            except BaseException:
                os.close(fd)
                raise
        self._audit("download", [path])
        size = None if _under(path, "/proc") or _under(path, "/sys") else info.st_size
        return stream, size, name

    def _expire_uploads(self):
        for upload_id, upload in list(self._uploads.items()):
            if upload["expires"] <= time.time():
                self._abort_upload(upload_id)

    @_api
    def maintenance(self):
        """Called by the web worker timer even when no new request arrives."""
        with self._lock:
            before = len(self._uploads)
            self._expire_uploads()
            now = time.time()
            self._plans = {key: value for key, value in self._plans.items() if value["expires"] > now}
            return {"uploads": list(self._uploads), "expired": before - len(self._uploads)}

    def _upload(self, upload_id):
        if not isinstance(upload_id, str):
            raise FisiereError("upload", _("Încărcarea nu este validă."), 404)
        self._expire_uploads()
        upload = self._uploads.get(upload_id)
        if upload is None:
            raise FisiereError("upload", _("Încărcarea a expirat sau nu mai există."), 404)
        return upload

    @_api
    def begin_upload(self, path, size=None):
        path = self._write_allowed(path)
        if size is not None and (isinstance(size, bool) or not isinstance(size, int) or size < 0):
            raise FisiereError("upload_size", _("Dimensiunea încărcării nu este validă."))
        with self._lock:
            self._expire_uploads()
            if len(self._uploads) >= MAX_UPLOADS:
                raise FisiereError("upload_busy", _("Sunt deja prea multe încărcări în curs."), 409)
            with self._parent(path, write=True) as (parent, name, unused):
                info = parent.exists(name)
                if info is not None and not stat.S_ISREG(info.st_mode):
                    raise FisiereError("not_file", _("Destinația trebuie să fie un fișier obișnuit."))
                temp_name, fd = self._temporary(parent)
                # Keep the parent anchor alive for the whole upload, never reopen it by path.
                try:
                    held = _Directory(self, fd=os.dup(parent.fd)) if parent.fd is not None else _Directory(self, local=parent.local)
                except BaseException:
                    os.close(fd)
                    parent.unlink(temp_name)
                    raise
                upload_id = secrets.token_urlsafe(24)
                self._uploads[upload_id] = {"parent": held, "name": name, "path": path,
                    "temporary": temp_name, "fd": fd, "offset": 0, "size": size,
                    "original": _identity(info) if info is not None else None,
                    "expires": time.time() + UPLOAD_TTL}
        return {"id": upload_id, "offset": 0, "size": size}

    @_api
    def write_upload(self, upload_id, offset, chunk):
        if not isinstance(chunk, (bytes, bytearray)) or len(chunk) > CHUNK_SIZE:
            raise FisiereError("upload_chunk", _("Blocul încărcat trebuie să aibă cel mult 64 KiB."))
        with self._lock:
            upload = self._upload(upload_id)
            if not isinstance(offset, int) or isinstance(offset, bool) or offset != upload["offset"]:
                raise FisiereError("upload_offset", _("Ordinea blocurilor încărcate nu este validă."), 409)
            if upload["size"] is not None and offset + len(chunk) > upload["size"]:
                raise FisiereError("upload_size", _("Încărcarea depășește dimensiunea declarată."))
            self._write_all(upload["fd"], chunk)
            upload["offset"] += len(chunk)
            upload["expires"] = time.time() + UPLOAD_TTL
            return {"id": upload_id, "offset": upload["offset"]}

    @_api
    def finish_upload(self, upload_id):
        with self._lock:
            upload = self._upload(upload_id)
            if upload["size"] is not None and upload["offset"] != upload["size"]:
                raise FisiereError("upload_size", _("Încărcarea este incompletă."), 409)
            parent, name, path = upload["parent"], upload["name"], upload["path"]
            current = parent.exists(name)
            expected = upload["original"]
            if (expected is None and current is not None) or (expected is not None and (current is None or _identity(current) != expected)):
                self._abort_upload(upload_id)
                raise FisiereError("conflict", _("Destinația s-a schimbat în timpul încărcării."), 409)
            try:
                if current is not None:
                    self._attributes(upload["fd"], current)
                    if any(_under(path, base) for base in _SYSTEM):
                        self._backup_stream(parent, name, path, current)
                elif hasattr(os, "fchmod"):
                    os.fchmod(upload["fd"], 0o644)
                os.fsync(upload["fd"])
                os.close(upload["fd"])
                upload["fd"] = None
                latest = parent.exists(name)
                if expected is not None and (latest is None or _identity(latest) != expected):
                    raise FisiereError("conflict", _("Destinația s-a schimbat în timpul salvării încărcării."), 409)
                parent.rename(upload["temporary"], parent, name, no_replace=expected is None)
                parent.sync()
                size = upload["offset"]
            except BaseException:
                self._abort_upload(upload_id)
                raise
            del self._uploads[upload_id]
            parent.close()
        self._audit("upload", [path])
        return {"path": path, "size": size}

    def _backup_stream(self, parent, name, path, info):
        if name.endswith(".hds-inainte"):
            return
        temp, output_fd = self._temporary(parent)
        input_fd = None
        try:
            input_fd = parent.open(name, os.O_RDONLY)
            if _identity(os.fstat(input_fd)) != _identity(info):
                raise FisiereError("conflict", _("Destinația s-a schimbat în timpul încărcării."), 409)
            while True:
                chunk = os.read(input_fd, CHUNK_SIZE)
                if not chunk:
                    break
                self._write_all(output_fd, chunk)
            if _identity(os.fstat(input_fd)) != _identity(info):
                raise FisiereError("conflict", _("Destinația s-a schimbat în timpul încărcării."), 409)
            self._attributes(output_fd, info)
            os.fsync(output_fd)
            os.close(output_fd)
            output_fd = None
            parent.rename(temp, parent, name + ".hds-inainte")
        finally:
            if input_fd is not None:
                os.close(input_fd)
            if output_fd is not None:
                os.close(output_fd)
            try:
                parent.unlink(temp)
            except FileNotFoundError:
                pass

    def _abort_upload(self, upload_id):
        upload = self._uploads.pop(upload_id, None)
        if upload is None:
            return
        try:
            if upload["fd"] is not None:
                os.close(upload["fd"])
            try:
                upload["parent"].unlink(upload["temporary"])
            except FileNotFoundError:
                pass
        finally:
            upload["parent"].close()

    @_api
    def abort_upload(self, upload_id):
        with self._lock:
            self._abort_upload(upload_id)
        return {"aborted": True}

    def close(self):
        with self._lock:
            for upload_id in list(self._uploads):
                self._abort_upload(upload_id)
            self._plans.clear()

    def _default_shortcuts(self):
        recording = self.recordings_path() if callable(self.recordings_path) else self.recordings_path
        entries = [
            ("extensions", _("Pluginuri"), "/usr/lib/enigma2/python/Plugins/Extensions"),
            ("systemplugins", _("Pluginuri de sistem"), "/usr/lib/enigma2/python/Plugins/SystemPlugins"),
            ("tuxbox", _("Configurări module de acces"), "/etc/tuxbox/config"),
            ("softcams", _("Programele modulelor"), "/usr/softcams"),
            ("satellites", _("satellites.xml"), "/etc/tuxbox/satellites.xml"),
            ("enigma2", _("Lista de canale și setările"), "/etc/enigma2"),
            ("skins", _("Teme"), "/usr/share/enigma2"),
            ("logs", _("Jurnale"), "/home/root/logs"),
        ]
        if recording:
            entries.append(("recordings", _("Înregistrări"), clean_path(recording)))
        entries.extend((("run-media", _("Discuri /run/media"), "/run/media"), ("media", _("Discuri /media"), "/media")))
        return [{"id": "default-" + key, "name": name, "path": path, "default": True} for key, name, path in entries]

    def _shortcuts(self):
        try:
            with self._parent(self.shortcuts_path) as (parent, name, unused):
                raw, unused_info = self._read_regular(parent, name, 128 * 1024)
        except FileNotFoundError:
            return self._default_shortcuts(), None, None
        try:
            saved = json.loads(raw.decode("utf-8"))
            items = saved.get("items") if isinstance(saved, dict) else saved
            if not isinstance(items, list) or len(items) > 64:
                raise ValueError("items")
            result, ids = [], set()
            for item in items:
                if not isinstance(item, dict):
                    raise ValueError("item")
                shortcut_id, label = item.get("id"), item.get("name")
                if not isinstance(shortcut_id, str) or not shortcut_id or len(shortcut_id) > 80 or shortcut_id in ids:
                    raise ValueError("id")
                if not isinstance(label, str) or not label.strip() or len(label) > 120 or any(ord(c) < 32 for c in label):
                    raise ValueError("name")
                ids.add(shortcut_id)
                result.append({"id": shortcut_id, "name": label, "path": clean_path(item.get("path")),
                               "default": bool(item.get("default", False))})
            recording = self.recordings_path() if callable(self.recordings_path) else self.recordings_path
            if recording:
                current_recording = clean_path(recording)
                for item in result:
                    if item["id"] == "default-recordings" and item["default"]:
                        # Keep the chosen label/order; a removed built-in remains
                        # removed. Only its receiver configuration path is live.
                        item["path"] = current_recording
            return result, raw, unused_info
        except (ValueError, UnicodeError, FisiereError):
            raise FisiereError("shortcuts_invalid", _("Fișierul scurtăturilor nu este valid. Păstrează-l pentru verificare înainte de modificare."), 409)

    @_api
    def shortcuts_list(self):
        with self._lock:
            return self._shortcuts()[0]

    @_api
    def shortcuts_update(self, action, id=None, name=None, path=None, order=None):
        with self._lock:
            items, old_raw, info = self._shortcuts()
            selected = next((item for item in items if item["id"] == id), None)
            if action in ("add", "rename"):
                if not isinstance(name, str) or not name.strip() or len(name) > 120 or any(ord(c) < 32 or 127 <= ord(c) < 160 for c in name):
                    raise FisiereError("shortcut_name", _("Numele scurtăturii trebuie să aibă între 1 și 120 de caractere."))
                name = name.strip()
            if action == "add":
                if len(items) >= 64:
                    raise FisiereError("shortcuts_limit", _("Pot fi păstrate cel mult 64 de scurtături."))
                items.append({"id": "user-" + secrets.token_hex(10), "name": name, "path": clean_path(path), "default": False})
            elif action == "rename":
                if selected is None:
                    raise FisiereError("shortcut", _("Scurtătura nu mai există."), 404)
                selected["name"] = name
                if path is not None:
                    selected["path"] = clean_path(path)
            elif action == "remove":
                if selected is None:
                    raise FisiereError("shortcut", _("Scurtătura nu mai există."), 404)
                items.remove(selected)
            elif action == "reorder":
                if not isinstance(order, list) or len(order) != len(items) or any(not isinstance(key, str) for key in order) or len(set(order)) != len(items) or set(order) != {item["id"] for item in items}:
                    raise FisiereError("shortcut_order", _("Ordinea scurtăturilor nu este validă."))
                by_id = {item["id"]: item for item in items}
                items = [by_id[key] for key in order]
            else:
                raise FisiereError("action", _("Operația pentru scurtături nu este disponibilă."))
            self._ensure_directory(posixpath.dirname(self.shortcuts_path))
            data = (json.dumps({"version": 1, "items": items}, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            with self._parent(self.shortcuts_path, write=True) as (parent, filename, unused):
                # Shortcut preferences have their own atomic storage; no system-file backup.
                self._replace_bytes(parent, filename, self.shortcuts_path, data,
                                    _identity(info) if info is not None else None, info=info)
        self._audit("shortcut_" + action, [self.shortcuts_path])
        return items
