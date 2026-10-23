# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Ajutoare comune care merg la fel pe Python 3 si pe Python 2.7 (imagini vechi). Facut de hdsatelit.com.

Doar biblioteca standard, fara alte importuri din plugin, ca modulul sa poata fi incarcat si de scripturile care
ruleaza singure (paznicul, releele).
"""
import os
import time


def inlocuieste(sursa, tinta):
    """Muta atomic `sursa` peste `tinta` (os.replace pe Python 3; pe Python 2.7 os.rename, atomic pe Linux)."""
    f = getattr(os, 'replace', None)
    if f is not None:
        f(sursa, tinta)
    elif os.name == 'nt' and os.path.exists(tinta):
        # doar probele pe PC cu Python 2.7: pe Windows os.rename nu scrie peste un fisier existent
        os.remove(tinta)
        os.rename(sursa, tinta)
    else:
        os.rename(sursa, tinta)


def monoton():
    """Secunde dintr-un ceas care nu sare cu ora sistemului (time.monotonic pe Python 3)."""
    f = getattr(time, 'monotonic', None)
    if f is not None:
        return f()
    try:
        with open('/proc/uptime') as u:
            return float(u.read().split()[0])
    except (IOError, OSError, ValueError, IndexError):
        return time.time()


# ---------------------------------------------------------------- semnalele enigma2 (liste sau obiecte)
# Pe cele mai multe imagini semnalele (eTimer.callback, eConsoleAppContainer.appClosed / dataAvail / stderrAvail /
# stdoutAvail) sunt liste Python: append / remove. Pe imaginile cu semnale-obiect ele au .connect(fn), care
# intoarce un obiect de legatura; legatura traieste DOAR cat traieste acel obiect (daca nu e pastrat, callback-ul nu
# mai vine niciodata, fara nicio eroare). Acolo eTimer nu are .callback, doar .timeout.
# Deci: orice legatura intoarce un „manier", iar proprietarul (obiectul care tine timerul sau containerul) il pastreaza
# cat vrea sa primeasca apeluri si il da la deconecteaza() cand nu mai vrea.

def conecteaza(semnal, fn):
    """Leaga fn la un semnal enigma2. -> manierul, de pastrat de proprietar.
    Lista Python (cele mai multe imagini): append, manierul e (lista, fn).
    Obiect cu connect (semnale-obiect): manierul e obiectul de legatura intors de connect."""
    if hasattr(semnal, 'append'):
        semnal.append(fn)
        return (semnal, fn)
    return semnal.connect(fn)


def conecteaza_timer(timer, fn):
    """Leaga fn la un eTimer. Unde exista lista .callback, ea se foloseste; altfel .timeout.connect
    (semnale-obiect). -> manierul, de pastrat de proprietar."""
    lista = getattr(timer, 'callback', None)
    if lista is not None and hasattr(lista, 'append'):
        lista.append(fn)
        return (lista, fn)
    return timer.timeout.connect(fn)


def deconecteaza(manier):
    """Desface o legatura facuta cu conecteaza / conecteaza_timer. Nu arunca. -> None (de pus in locul manierului).
    (lista, fn): scoate fn din lista, daca mai e acolo. Obiect de legatura (semnale-obiect): legatura moare cand ultima
    referinta dispare; proprietarul pune None in locul lui (valoarea intoarsa)."""
    if isinstance(manier, tuple) and len(manier) == 2:
        lista, fn = manier
        try:
            lista.remove(fn)
        except Exception:
            pass
    return None


def deconecteaza_toate(maniere):
    """Desface toate legaturile dintr-o lista de maniere si goleste lista. Nu arunca."""
    try:
        while maniere:
            deconecteaza(maniere.pop())
    except Exception:
        pass


# ---------------------------------------------------------------- sistemul de pornire si interpretorul
def systemd():
    """True daca receptorul porneste cu systemd (imaginile care il folosesc)."""
    return os.path.isdir('/run/systemd/system')


def comanda_repornire_interfata():
    """Comanda (lista argv, fara shell) care reporneste doar interfata enigma2, sau None.
    systemd: ['systemctl', 'restart', 'enigma2'] (unitatea enigma2.service; acolo enigma2 nu mai e ridicat de un
    script care il reporneste in bucla, deci semnalele singure l-ar lasa oprit).
    Fara systemd: None = ce se foloseste acum, adica paznicul trimite SIGTERM/SIGKILL pe pid-ul enigma2, iar scriptul
    de pornire al imaginii il ridica singur."""
    if systemd():
        return ['systemctl', 'restart', 'enigma2']
    return None


_INTERPRETOR = [None]


def _executabil(cale):
    return os.path.isfile(cale) and os.access(cale, os.X_OK)


def interpretor_python():
    """'python3' daca exista pe receptor, altfel 'python' (imagini doar cu Python 2.7), pentru comenzile
    eConsoleAppContainer. Se afla o singura data pe proces, cu cateva os.access pe /usr/bin si pe directoarele din
    PATH (nimic blocant: fara subprocess, fara `which`). Daca nu se gaseste nici unul, ramane 'python3'."""
    if _INTERPRETOR[0] is None:
        directoare = ['/usr/bin', '/bin', '/usr/local/bin'] + [d for d in os.environ.get('PATH', '').split(os.pathsep)
                                                            if d]
        ales = 'python3'
        if not any(_executabil(os.path.join(d, 'python3')) for d in directoare):
            if any(_executabil(os.path.join(d, 'python')) for d in directoare):
                ales = 'python'
        _INTERPRETOR[0] = ales
    return _INTERPRETOR[0]


# ---------------------------------------------------------------- textele in enigma2 pe Python 2.7
_UNICODE = type(u'')


def text_nativ(x):
    """Textul in forma pe care o foloseste enigma2 pe fiecare Python: pe 2.7 octeti UTF-8 (asa dau gettext si
    widget-urile), pe 3 str. JSON-ul da unicode pe 2.7; amestecat cu un text tradus cu diacritice ar da
    UnicodeDecodeError. Orice alt tip (numere, None) trece neschimbat."""
    if _UNICODE is str:
        return x.decode('utf-8', 'replace') if isinstance(x, bytes) else x
    return x.encode('utf-8') if isinstance(x, _UNICODE) else x


def e_text(x):
    """isinstance(x, str) care primeste si unicode pe 2.7 (valorile din JSON)."""
    return isinstance(x, (str, _UNICODE))


# ---------------------------------------------------------------- releele si detectorul pe Python 2.7 (LOT-015-PY27)
# Pe Python 3 numele de mai jos sunt chiar functiile si exceptiile standard (niciun strat in plus pe drumul datelor).
# Pe Python 2.7 erorile de fisier si de retea vin ca IOError/OSError/socket.error cu errno: aici se traduc in aceleasi
# clase ca pe Python 3, ca un `except BlockingIOError` scris o data sa mearga pe ambele.
import errno as _errno
import sys as _sys

PY2 = _sys.version_info[0] < 3

if PY2:
    import binascii as _binascii
    import subprocess as _subprocess

    class BlockingIOError(EnvironmentError):          # noqa: A001
        pass

    class InterruptedError(EnvironmentError):         # noqa: A001
        pass

    class BrokenPipeError(EnvironmentError):          # noqa: A001
        pass

    class TimeoutExpired(Exception):
        pass

    _BLOCAT = frozenset((_errno.EAGAIN, getattr(_errno, 'EWOULDBLOCK', _errno.EAGAIN), getattr(_errno, 'WSAEWOULDBLOCK', 10035)))
    _TEAVA = frozenset((_errno.EPIPE, getattr(_errno, 'ESHUTDOWN', 108)))

    def _tradus(e):
        n = getattr(e, 'errno', None)
        clasa = (BlockingIOError if n in _BLOCAT else InterruptedError if n == _errno.EINTR else
                 BrokenPipeError if n in _TEAVA else None)
        return None if clasa is None else clasa(n, getattr(e, 'strerror', None) or str(e))

    def citeste_fd(fd, marime):
        """os.read; pe 2.7 EAGAIN devine BlockingIOError, EINTR InterruptedError."""
        try:
            return os.read(fd, marime)
        except EnvironmentError as e:
            t = _tradus(e)
            if t is None:
                raise
            raise t

    def scrie_fd(fd, date):
        try:
            return os.write(fd, date)
        except EnvironmentError as e:
            t = _tradus(e)
            if t is None:
                raise
            raise t

    def primeste(sock, marime):
        try:
            return sock.recv(marime)
        except EnvironmentError as e:
            t = _tradus(e)
            if t is None:
                raise
            raise t

    def trimite(sock, date):
        try:
            return sock.send(date)
        except EnvironmentError as e:
            t = _tradus(e)
            if t is None:
                raise
            raise t

    def accepta(sock):
        try:
            return sock.accept()
        except EnvironmentError as e:
            t = _tradus(e)
            if t is None:
                raise
            raise t

    def din_octeti(b):
        """int.from_bytes(b, 'big')."""
        return int(_binascii.hexlify(b) or b'0', 16)

    def in_octeti(v, n):
        """v.to_bytes(n, 'big')."""
        return _binascii.unhexlify('%0*x' % (2 * n, v)) if n else b''

    def ceas_procesor():
        """time.process_time: secundele de procesor ale procesului (utilizator + sistem)."""
        t = os.times()
        return t[0] + t[1]

    ceas_precis = time.clock if _sys.platform == 'win32' else time.time

    def asteapta_proces(p, secunde):
        """Popen.wait(timeout): TimeoutExpired daca procesul nu a iesit in `secunde`."""
        capat = monoton() + secunde
        while p.poll() is None:
            if monoton() >= capat:
                raise TimeoutExpired('procesul %s nu a iesit in %s s' % (p.pid, secunde))
            time.sleep(0.02)
        return p.returncode

    def fisier_nul():
        """Pentru stdin/stdout/stderr ale unui proces copil: pe 2.7 nu exista subprocess.DEVNULL (se inchide dupa Popen)."""
        return open(os.devnull, 'r+b')

    INCHIDE_FD = _sys.platform != 'win32'             # pe Windows 2.7 close_fds nu merge impreuna cu redirectari
else:
    import builtins as _builtins
    import socket as _socket
    import subprocess as _subprocess
    BlockingIOError = _builtins.BlockingIOError       # noqa: A001
    InterruptedError = _builtins.InterruptedError     # noqa: A001
    BrokenPipeError = _builtins.BrokenPipeError       # noqa: A001
    TimeoutExpired = _subprocess.TimeoutExpired
    citeste_fd = os.read
    scrie_fd = os.write
    primeste = _socket.socket.recv
    trimite = _socket.socket.send
    accepta = _socket.socket.accept
    ceas_procesor = time.process_time
    ceas_precis = time.perf_counter

    def din_octeti(b):
        return int.from_bytes(b, 'big')

    def in_octeti(v, n):
        return v.to_bytes(n, 'big')

    def asteapta_proces(p, secunde):
        return p.wait(secunde)

    def fisier_nul():
        return _subprocess.DEVNULL

    INCHIDE_FD = True


def pereche_socluri():
    """socket.socketpair(); pe Windows cu Python 2.7 (fara socketpair) doua socluri legate prin 127.0.0.1."""
    import socket
    f = getattr(socket, 'socketpair', None)
    if f is not None:
        return f()
    asc = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        asc.bind(('127.0.0.1', 0))
        asc.listen(1)
        a = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            a.connect(asc.getsockname())
            b, _ = asc.accept()
        except Exception:
            a.close()
            raise
    finally:
        asc.close()
    return b, a
