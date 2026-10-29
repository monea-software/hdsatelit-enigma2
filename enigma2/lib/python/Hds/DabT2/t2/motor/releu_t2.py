# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Releul DVB-T2 din satelit (T2-MI): fluxurile pe 127.0.0.1:8889, controlul pe 127.0.0.1:8890. Facut de hdsatelit.com.
Ruleaza ca proces separat (nice 10), pornit de plugin; niciodata in enigma2.

  python3 releu_t2.py /tmp/hdst2mi-feed.json [--port 8889] [--port-control 8890] [--inactiv 30] [--iesi-fara-clienti]

  Portul fluxurilor (feed http_port, --port):
  GET /t2/<feed>/<plp>              TS DVB-T2 decapsulat (video/mp2t)
  Portul de control (feed port_control, --port-control, implicit portul fluxurilor + 1):
  GET /stare                        JSON: sursa, debit, decapsulatoare, procesor, memorie
  GET /t2/<feed>/<plp>/servicii     JSON din PAT si SDT ale fluxului scos (cand sunt complete sau dupa 6 s)

MODUL BINAR (implicit pe receptor: binarul exista, drumul e http8001, nu e sursa falsa): releul Python NU atinge datele.
bin/t2mi_decap asculta singur pe portul fluxurilor (-u, cel mult 8 clienti), se conecteaza la 8001 doar cat are clienti
(-h, -I), numara sesiunile 8001 (-c) si scrie statistici (-j) si pachetele PAT/SDT (-P) in fisiere mici din /tmp.
Releul raspunde doar pe portul de control (citeste acele fisiere la cerere) si supravegheaza binarul: il reporneste daca
iese (cel mult 5 ori in 10 minute), il opreste la iesire. Binarul se porneste din firul principal (PR_SET_PDEATHSIG
se leaga de firul care l-a pornit).
REZERVA (binar lipsa, alt drum, --sursa-falsa): releul de dinainte, cu fluxurile pe portul fluxurilor; acelasi handler
raspunde si pe portul de control.

Sursa implicita: http://127.0.0.1:8001/<referinta purtatorului> (DOVEDIT pe receptor: singurul drum T2-MI
fara pierderi; TAP pierde ~35%). Tunerul il acordeaza streamserverul enigma2, nu releul: primele date pot veni
dupa pana la 90 s (rotirea antenei); raspunsul 400 in corp (tuner ocupat) se reincearca singur.
Referinta: feed['ref_8001'] sau feed['purtator'] = {sid, tsid, onid, ns} -> 1:0:1:SID:TSID:ONID:NS:0:0:0:.

Memorie: vezi REGULILE din comun/surse.py (demux cel mult 1 MB, nimic mare in /tmp). Releul nu scrie fisiere; in
modul binar binarul scrie doar fisiere mici (statistici sub 16 KB, PAT/SDT cel mult 64 KB, contorul de sesiuni).
Cai (feed sau argumente): fisier_stat / --fisier-stat, fisier_psi / --fisier-psi, fisier_sesiuni / --fisier-sesiuni.

In rezerva munca grea o face tot binarul, prin teava: releul ii da TS pe stdin si publica stdout. Daca binarul
lipseste se foloseste motor/t2mi.py (referinta, lent).
Sursa (surse.pachete_ts) porneste la primul client si se opreste dupa --inactiv secunde fara clienti.
Forma datelor din TAP se afla la pornire: pachete de 188 -> t2mi_decap -p PID; unitati fara antete -> -r.
Optional in feed: drum_ts (http8001|tap|dvr|fifo), port_8001, termen_8001, fifo, nule (true = -n), direct (true = binarul
citeste singur fd-ul demux-ului, fara Python pe drum; cere si forma: ts188|sarcina).
Merge pe Python 3 si pe Python 2.7 (imagini vechi, fara al doilea Python): ajutoarele din comun/compat.py."""
from __future__ import division

import json
import math
import os
import platform
import select
import signal
import socket
import subprocess
import sys
import threading
import time

AICI = os.path.dirname(os.path.abspath(__file__))
RADACINA = os.path.dirname(AICI)
# Codul comun (surse.py, releu_http.py, text_dvb.py) se cauta in ordine: in imaginea HDSatelit doua niveluri mai sus
# (Hds/DabT2/t2/motor -> Hds/DabT2); ca plugin in Plugins/SystemPlugins/HdsComun (langa Extensions, apoi calea
# fixa), inaintea directoarelor comun/ de dinainte (un rest ramas de la o instalare veche nu are voie sa fie luat in
# locul lui); in surse (S) comunul e S/comun, gasit prin ultima cale. Un dosar intra numai daca are surse.py.
for _d in (AICI, RADACINA):
    if os.path.isdir(_d) and _d not in sys.path:
        sys.path.append(_d)
for _d in (os.path.normpath(os.path.join(AICI, '..', '..')),
           os.path.normpath(os.path.join(AICI, '..', '..', '..', 'SystemPlugins', 'HdsComun')),
           '/usr/lib/enigma2/python/Plugins/SystemPlugins/HdsComun',
           os.path.join(RADACINA, 'comun'), os.path.normpath(os.path.join(AICI, '..', '..', '..', 'comun'))):
    if os.path.isfile(os.path.join(_d, 'surse.py')) and _d not in sys.path:
        sys.path.append(_d)

import releu_http as H             # noqa: E402
import surse                       # noqa: E402

if sys.version_info[0] < 3:        # Python 2.7: aceleasi nume ca pe Python 3
    from compat import (monoton as _monoton, ceas_procesor as _ceas_procesor, scrie_fd as _scrie_fd,  # noqa: E402
                        asteapta_proces as _asteapta_proces, TimeoutExpired as _TimeoutExpired,
                        fisier_nul as _fisier_nul, INCHIDE_FD as _INCHIDE_FD, BlockingIOError, BrokenPipeError)
    OSError = EnvironmentError     # noqa: A001  (pe 2.7 IOError si socket.error nu sunt OSError)
    _PY2 = True
    _B = bytearray                 # bytes(...) pe 2.7 e str: str[i] da un sir, nu un numar
else:
    _monoton = time.monotonic
    _ceas_procesor = time.process_time
    _scrie_fd = os.write
    _TimeoutExpired = subprocess.TimeoutExpired
    _INCHIDE_FD = True
    _PY2 = False
    _B = bytes

    def _asteapta_proces(p, secunde):
        return p.wait(secunde)

    def _fisier_nul():
        return subprocess.DEVNULL


def _fir(tinta, nume, args=()):
    """threading.Thread(..., daemon=True); pe 2.7 Thread nu primeste daemon in constructor."""
    t = threading.Thread(target=tinta, name=nume, args=args)
    t.daemon = True
    return t


def _popen_fara_iesiri(cmd, **kw):
    """Popen cu iesirile (si intrarea, daca nu e data) spre /dev/null; pe 2.7 fara subprocess.DEVNULL."""
    nul = _fisier_nul()
    try:
        for k in ('stdin', 'stdout', 'stderr'):
            kw.setdefault(k, nul)
        return subprocess.Popen(cmd, close_fds=_INCHIDE_FD, **kw)
    finally:
        if hasattr(nul, 'close'):
            nul.close()

ASTEPTARE_SERVICII_S = 6.0
TERMEN_8001_S = 90.0               # streamserverul acordeaza tunerul si poate roti antena
CAP_CLIENT = 4 * 1024 * 1024       # ~0,8 s la 40 Mbit/s
MAX_PLP = 2
BLOC = 65536
STAT_BINAR = '/tmp/hdst2mi-stat.json'
PSI_BINAR = '/tmp/hdst2mi-psi.ts'
SESIUNI_8001 = '/tmp/hds-8001-sesiuni'   # acelasi fisier ca in comun/sesiuni8001.py
CITIRE_FISIER_MAX = 64 * 1024
REPORNIRI_MAX = 5                  # repornirile binarului intr-o fereastra de REPORNIRI_FEREASTRA_S
REPORNIRI_FEREASTRA_S = 600.0
# Defectul 10b: binarul isi citeste la pornire randurile din -c (fereastra 4/120 s ramane si peste reporniri), dar pauza
# de dupa conexiunile care nu au fost sesiuni (400, ocupat, inchidere inainte de antet) se pierde la repornire. De aceea
# pauza dintre reporniri creste si ea: 2, 4, 8, 16, 32, 60 s, si revine la 2 s doar cand /stat arata date adevarate.
PAUZA_REPORNIRE_S = 2.0
PAUZA_REPORNIRE_MAX_S = 60.0
CONEXIUNI_FEREASTRA = 4            # -R: cel mult atatea conexiuni 8001 in 120 s (dat explicit, nu implicitul binarului)
_SIGKILL = getattr(signal, 'SIGKILL', 9)
_ARH = {'armv7l': 'armv7', 'armv7': 'armv7', 'armv6l': 'armv7', 'aarch64': 'aarch64', 'arm64': 'aarch64',
        'mips': 'mipsel', 'mipsel': 'mipsel', 'x86_64': 'x86_64', 'amd64': 'x86_64'}


class Jurnal(object):
    PLAFON = 64 * 1024              # REGULA 2: stderr ajunge intr-un fisier din /tmp (RAM); peste plafon se tace

    def __init__(self):
        self._ultim = {}
        self.scris = 0

    def __call__(self, text):
        if self.scris >= self.PLAFON:
            return
        acum = _monoton()
        cheie = text[:40]
        if acum - self._ultim.get(cheie, -99) < 10:
            return
        if len(self._ultim) > 200:
            self._ultim.clear()
        self._ultim[cheie] = acum
        try:
            linie = '%s releu_t2: %s\n' % (time.strftime('%H:%M:%S'), text[:300])
            self.scris += len(linie)
            sys.stderr.write(linie)
            sys.stderr.flush()
        except Exception:
            pass


def curata_id(feed_id):
    """La fel ca buchete._curata_id: asa se construieste URL-ul in plugin."""
    return ''.join(ch for ch in str(feed_id or '') if ch.isalnum() or ch in '_-.')[:64]


def gaseste_binarul(cerut=None):
    if cerut:
        return cerut if os.path.exists(cerut) else None
    arh = _ARH.get(platform.machine().lower(), platform.machine().lower())
    for nume in ('t2mi_decap.%s' % arh, 't2mi_decap'):
        cale = os.path.join(RADACINA, 'bin', nume)
        if os.path.isfile(cale):
            if not os.access(cale, os.X_OK):
                try:
                    os.chmod(cale, 0o755)
                except OSError:
                    continue
            return cale
    return None


# ---------------------------------------------------------------- PSI din fluxul scos
_T32 = []
for _i in range(256):
    _c = _i << 24
    for _ in range(8):
        _c = ((_c << 1) ^ 0x04C11DB7) & 0xFFFFFFFF if _c & 0x80000000 else (_c << 1) & 0xFFFFFFFF
    _T32.append(_c)


def crc32_mpeg(d):
    c = 0xFFFFFFFF
    t = _T32
    for b in d:
        c = ((c << 8) & 0xFFFFFFFF) ^ t[(c >> 24) ^ b]
    return c


from text_dvb import text_dvb      # noqa: E402  (comun/text_dvb.py, acelasi cod ca in detector)


class Psi(object):
    """PAT (PID 0) si SDT actual (PID 0x11, table_id 0x42) din pachete TS de 188 aliniate. Pachetele cu PID-urile
    cautate se gasesc cu bytes.find (in C), nu pachet cu pachet."""
    _TIPARE = (b'\x47\x40\x00', b'\x47\x00\x00', b'\x47\x40\x11', b'\x47\x00\x11')

    def __init__(self):
        self.pat = None              # (tsid, {program: pid_pmt})
        self.sdt = {}                # sid -> {'nume', 'furnizor', 'tip'}
        self.onid = None
        self.tsid_sdt = None
        self._sectiuni_sdt = {}      # section_number -> octeti (pentru completitudine)
        self._ultima_sdt = None
        self._buc = {0: None, 0x11: None}
        self._rest = b''
        self.rele = 0

    def complet(self):
        if self.pat is None or not self.pat[1]:
            return False
        if self._ultima_sdt is None or len(self._sectiuni_sdt) <= self._ultima_sdt:
            return False
        return all(p in self.sdt for p in self.pat[1])

    def adauga(self, bloc):
        if _PY2 and type(bloc) is not bytearray:
            bloc = bytearray(bloc)       # pe 2.7 os.read da str: p[1] ar fi un sir si PID-ul ar iesi gresit, tacut
        # citirile din pipe nu cad pe 188: restul se lipeste in fata urmatorului bloc
        if self._rest:
            bloc = self._rest + bloc
        n = len(bloc) // 188 * 188
        self._rest = bloc[n:]
        gasite = []
        for t in self._TIPARE:
            i = bloc.find(t)
            while i >= 0:
                if i % 188 == 0 and i + 188 <= n:
                    gasite.append(i)
                i = bloc.find(t, i + 1)
        if not gasite:
            return
        gasite.sort()
        for i in gasite:
            self._pachet(bloc[i:i + 188])

    def _pachet(self, p):
        pid = ((p[1] & 0x1F) << 8) | p[2]
        afc = (p[3] >> 4) & 3
        o = 4
        if afc & 2:
            o = 5 + p[4]
        if not afc & 1 or o >= 188:
            return
        d = p[o:]
        if p[1] & 0x40:
            ptr = d[0]
            rest = d[1:1 + ptr]
            if self._buc[pid] is not None:
                self._buc[pid] += rest
                self._sectiune(pid)
            self._buc[pid] = bytearray(d[1 + ptr:])
            self._sectiune(pid)
        elif self._buc[pid] is not None:
            self._buc[pid] += d
            self._sectiune(pid)

    def _sectiune(self, pid):
        b = self._buc[pid]
        while b is not None and len(b) >= 3:
            if b[0] == 0xFF:
                self._buc[pid] = None
                return
            lung = 3 + (((b[1] & 0x0F) << 8) | b[2])
            if lung > 1024 + 3 or lung < 12:
                self._buc[pid] = None
                self.rele += 1
                return
            if len(b) < lung:
                return
            s = _B(b[:lung])
            del b[:lung]
            if crc32_mpeg(s) != 0:
                self.rele += 1
                continue
            if pid == 0 and s[0] == 0x00:
                self._pat(s)
            elif pid == 0x11 and s[0] == 0x42:
                self._sdt(s)

    def _pat(self, s):
        tsid = (s[3] << 8) | s[4]
        prog = {}
        for i in range(8, len(s) - 4 - 3, 4):
            nr = (s[i] << 8) | s[i + 1]
            if nr:
                prog[nr] = ((s[i + 2] & 0x1F) << 8) | s[i + 3]
        self.pat = (tsid, prog)

    def _sdt(self, s):
        self.tsid_sdt = (s[3] << 8) | s[4]
        self.onid = (s[8] << 8) | s[9]
        self._sectiuni_sdt[s[6]] = True
        self._ultima_sdt = s[7]
        i, sf = 11, len(s) - 4
        while i + 5 <= sf:
            sid = (s[i] << 8) | s[i + 1]
            dll = ((s[i + 3] & 0x0F) << 8) | s[i + 4]
            d = s[i + 5:min(i + 5 + dll, sf)]
            i += 5 + dll
            j = 0
            while j + 2 <= len(d):
                tag, ln = d[j], d[j + 1]
                v = d[j + 2:j + 2 + ln]
                j += 2 + ln
                if tag == 0x48 and len(v) >= 2:
                    lp = v[1]
                    k = 2 + lp
                    ls = v[k] if k < len(v) else 0
                    self.sdt[sid] = {'tip': v[0], 'furnizor': text_dvb(v[2:2 + lp]), 'nume': text_dvb(v[k + 1:k + 1 + ls])}

    def servicii(self):
        rez = []
        prog = self.pat[1] if self.pat else {}
        tsid = self.pat[0] if self.pat else self.tsid_sdt
        for sid in sorted(set(prog) | set(self.sdt)):
            info = self.sdt.get(sid, {})
            rez.append({'sid': sid, 'nume': info.get('nume') or '', 'furnizor': info.get('furnizor') or '',
                        'tip': info.get('tip') or 1, 'tsid': tsid or 0, 'onid': self.onid or 0, 'pmt': prog.get(sid)})
        return rez


# ---------------------------------------------------------------- decapsulatoare
def ts_in_pid(feed):
    """Feed-ul poarta un TS intreg direct in payload-ul PID-ului, fara T2-MI (felul abertis: fluxurile de distributie
    spaniole de pe 30W). Binarul primeste -A, rezerva Python foloseste t2mi.TsInPid."""
    return str((feed or {}).get('fel') or '') == 'abertis'


class DecapBinar(object):
    """t2mi_decap ca proces: stdin TS (sau T2-MI brut cu -r), stdout TS 188. Un fir citeste stdout."""
    fel = 'binar'

    def __init__(self, releu, binar, plp, forma, stdin=None):
        self.releu = releu
        self.plp = plp
        self.intrat = self.iesit = self.aruncat = 0
        cmd = [binar] if not binar.endswith('.py') else [sys.executable, binar]
        if ts_in_pid(releu.feed):
            cmd += ['-A', '-p', str(releu.pid)]       # TS intreg in payload-ul PID-ului: fara PLP, -r si -n
        else:
            cmd += ['-p', str(releu.pid), '-l', str(plp)]
            if forma == 'sarcina':
                cmd.append('-r')
            if releu.feed.get('nule'):
                cmd.append('-n')
        self.p = _popen_fara_iesiri(cmd, stdin=stdin if stdin is not None else subprocess.PIPE, stdout=subprocess.PIPE,
                                    bufsize=0)
        self._in = self.p.stdin.fileno() if self.p.stdin is not None else None
        if self._in is not None and sys.platform != 'win32':
            try:
                import fcntl
                fcntl.fcntl(self._in, 1031, 1024 * 1024)   # F_SETPIPE_SZ: 1 MB intre releu si binar, nu mai mult
            except (ImportError, OSError):
                pass
            try:
                os.set_blocking(self._in, False)       # un binar blocat pierde blocuri, nu opreste sursa
            except AttributeError:                     # Python 2.7: acelasi lucru prin fcntl
                try:
                    import fcntl
                    fcntl.fcntl(self._in, fcntl.F_SETFL, fcntl.fcntl(self._in, fcntl.F_GETFL) | os.O_NONBLOCK)
                except (ImportError, OSError):
                    pass
            except OSError:
                pass
        self.psi = None
        self._fir = _fir(self._citeste, 'decap-%d' % plp)
        self._fir.start()

    def scrie(self, bloc):
        if self._in is None:
            return
        mv = memoryview(bloc)
        termen = None
        try:
            while mv:
                try:
                    n = _scrie_fd(self._in, mv)
                    mv = mv[n:]
                except BlockingIOError:
                    acum = _monoton()
                    if termen is None:
                        termen = acum + 0.2               # o sacadare scurta a binarului se asteapta
                    elif acum >= termen:
                        self.aruncat += len(mv)
                        return
                    select.select([], [self._in], [], termen - acum)
            self.intrat += len(bloc)
        except (BrokenPipeError, OSError, ValueError):
            self._in = None

    def _citeste(self):
        fd = self.p.stdout.fileno()
        publica = self.releu.server.publica
        cheie = 't2:%d' % self.plp
        try:
            while True:
                b = os.read(fd, BLOC)
                if not b:
                    break
                self.iesit += len(b)
                psi = self.psi
                if psi is not None:
                    psi.adauga(b)
                publica(cheie, b)
        except (OSError, ValueError):
            pass

    def viu(self):
        return self.p.poll() is None

    def opreste(self):
        try:
            if self.p.stdin is not None:
                self.p.stdin.close()
        except OSError:
            pass
        self._in = None
        try:
            self.p.terminate()
            _asteapta_proces(self.p, 1.0)
        except Exception:
            try:
                self.p.kill()
                _asteapta_proces(self.p, 1.0)
            except Exception:
                pass
        try:
            self.p.stdout.close()
        except Exception:
            pass
        self._fir.join(1.0)


class DecapPython(object):
    """Rezerva: motor/t2mi.py in firul de date. Corect, dar lent; nu tine 40 Mbit/s pe receptor."""
    fel = 'python'

    def __init__(self, releu, plp, forma):
        import t2mi
        self.releu = releu
        self.plp = plp
        if ts_in_pid(releu.feed):
            self.d = t2mi.TsInPid(releu.pid)
            self.ad = self.d.adauga
        else:
            self.d = t2mi.Decapsulator(releu.pid, plp, nule=bool(releu.feed.get('nule')))
            self.ad = self.d.adauga_sarcina if forma == 'sarcina' else self.d.adauga
        self.cheie = 't2:%d' % plp
        self.intrat = self.iesit = self.aruncat = 0
        self.psi = None

    def scrie(self, bloc):
        self.intrat += len(bloc)
        out = self.ad(bloc)
        if out:
            self.iesit += len(out)
            psi = self.psi
            if psi is not None:
                psi.adauga(out)
            self.releu.server.publica(self.cheie, out)

    def viu(self):
        return True

    def opreste(self):
        pass


class DemuxTsFisier(object):
    """Sursa falsa pentru probe: un fisier TS in bucla, in blocuri de 65536, la debitul dat."""
    cale = None
    kbit = 8000.0

    def __init__(self, adapter=0, demux=0):
        self.f = open(DemuxTsFisier.cale, 'rb')
        self.t0 = _monoton()
        self.trimis = 0
        self.rata = DemuxTsFisier.kbit * 1000 / 8

    def buffer(self, marime):
        pass

    def filtru_sectiuni(self, pid, flags=4):
        pass

    def filtru_pes(self, pid, output=1, pes_type=20, flags=4):
        pass

    def citeste(self, timeout, marime=65536):
        if self.f is None:
            raise OSError(9, 'inchis')
        voie = (_monoton() - self.t0) * self.rata
        if self.trimis > voie:
            time.sleep(min(timeout, (self.trimis - voie) / self.rata))
            return None
        b = self.f.read(BLOC)
        if len(b) < BLOC:
            self.f.seek(0)
            if not b:
                b = self.f.read(BLOC)
                if not b:
                    raise EOFError('fisier gol')
        self.trimis += len(b)
        return b

    def inchide(self):
        f, self.f = self.f, None
        if f is not None:
            f.close()


# ---------------------------------------------------------------- modul binar: ajutoare
def citeste_mic(cale, maxim=CITIRE_FISIER_MAX):
    try:
        with open(cale, 'rb') as f:
            return f.read(maxim)
    except (IOError, OSError):
        return None


def cpu_proces(pid):
    """Secundele de procesor (utime + stime) ale unui proces, din /proc/<pid>/stat; None daca nu se poate."""
    try:
        with open('/proc/%d/stat' % pid, 'rb') as f:
            camp = f.read(2048).rsplit(b')', 1)[1].split()
        return (int(camp[11]) + int(camp[12])) / float(os.sysconf('SC_CLK_TCK'))
    except (IOError, OSError, ValueError, IndexError, AttributeError):
        return None


def rss_proces_kb(pid):
    try:
        with open('/proc/%d/statm' % pid, 'rb') as f:
            return int(f.read(256).split()[1]) * (os.sysconf('SC_PAGE_SIZE') // 1024)
    except (IOError, OSError, ValueError, IndexError, AttributeError):
        return None


def _intreg(v, implicit=None):
    try:
        return int(v)
    except (TypeError, ValueError):
        return implicit


class Scurgator(threading.Thread):
    """Client scurt spre binar cat se asteapta /servicii fara player (modul "invata"): binarul se conecteaza la 8001
    doar cand are un client. Citeste mereu in acelasi buffer (recv_into) si nu tine nimic."""

    def __init__(self, port, cale, termen):
        threading.Thread.__init__(self, name='servicii')
        self.daemon = True
        self.port, self.cale = port, cale
        self.pana_la = _monoton() + termen
        self.oprire = threading.Event()

    def prelungeste(self, termen):
        self.pana_la = max(self.pana_la, _monoton() + termen)

    def run(self):
        s = None
        try:
            s = socket.create_connection(('127.0.0.1', self.port), 2.0)
            s.sendall(('GET %s HTTP/1.0\r\nUser-Agent: hdsatelit\r\n\r\n' % self.cale).encode('ascii'))
            s.settimeout(0.5)
            buf = bytearray(262144)
            while not self.oprire.is_set() and _monoton() < self.pana_la:
                try:
                    if not s.recv_into(buf):
                        break
                except socket.timeout:
                    continue
        except (OSError, ValueError):
            pass
        finally:
            if s is not None:
                try:
                    s.close()
                except OSError:
                    pass


# ---------------------------------------------------------------- releul
class ReleuT2(object):
    def __init__(self, feed, arg, jurnal):
        self.feed = feed
        self.arg = arg
        self.jurnal = jurnal
        self.feed_id = curata_id(feed.get('id'))
        self.pid = int(feed.get('pid') or 0)
        self.server = None
        self.binar = gaseste_binarul(arg.binar)
        self.plp_dorite = frozenset()      # citit de firul de date
        self.decap = {}                    # plp -> Decap (doar firul de date le schimba)
        self.psi = {}                      # plp -> Psi cerut de /servicii
        self.chei_active = set()
        self.viata = {}
        self._fir = None
        self._fir_vechi = None
        self._oprire = None
        self.stare_sursa = surse.stare_noua()
        self.forma = None
        self.porniri = self.opriri = self.erori = 0
        self.ultima_eroare = ''
        self._debit = (_monoton(), 0, 0.0)
        self.Dispozitiv = DemuxTsFisier if arg.sursa_falsa else None
        if arg.sursa_falsa:
            DemuxTsFisier.cale = arg.sursa_falsa
            DemuxTsFisier.kbit = arg.debit_fals
        # modul binar (stabilit in main, dupa porturi)
        self.mod_binar = False
        self.port_fluxuri = None
        self.port_control = None
        self.proc = None
        self.cale_stat = arg.fisier_stat or feed.get('fisier_stat') or STAT_BINAR
        self.cale_psi = arg.fisier_psi or feed.get('fisier_psi') or PSI_BINAR
        self.cale_sesiuni = arg.fisier_sesiuni or feed.get('fisier_sesiuni') or SESIUNI_8001
        self.plp_binar = 0
        self.porniri_binar = 0
        self.iesiri_binar = 0
        self._reporniri = []
        self._iesit_la = -1e9
        self._reporniri_fara_date = 0      # reporniri ale binarului fara date intre ele: pauza creste (10b)
        self._stat_ultim = {}              # ultimul /stat al binarului viu (antet_200 cand binarul e omorat)
        self._stat_citit_la = -1e9
        self._octeti_vazuti = None
        self.randuri_releu = 0             # randuri „t2mi_decap" scrise de releu in -c (binar omorat dupa antet 200)
        self._binar_oprit = False
        self._binar_blocat = False
        self._scurgator = None
        self._debit_binar = (_monoton(), None, 0.0)
        self._verificat_la = 0.0
        self._folosit_la = _monoton()

    # ------------------------------------------------------------ HTTP
    def handler(self, server, client, cale):
        parti = [p for p in cale.split('/') if p]
        if parti == ['stare']:
            return H.json_raspuns(self.stare_binar() if self.mod_binar else self.stare())
        if len(parti) not in (3, 4) or parti[0] != 't2' or (len(parti) == 4 and parti[3] != 'servicii'):
            return H.Raspuns(404, 'cale necunoscuta')
        if parti[1] != self.feed_id:
            return H.Raspuns(404, 'feed necunoscut')
        try:
            plp = int(parti[2].split('.', 1)[0])
            if not 0 <= plp <= 255:
                raise ValueError
        except ValueError:
            return H.Raspuns(404, 'PLP gresit')
        if self.mod_binar:
            if len(parti) == 3:
                return H.Raspuns(404, 'fluxul se cere pe portul %s' % self.port_fluxuri)
            return self._servicii_binar(plp)
        cheie = 't2:%d' % plp
        cu_clienti = set(k for k in self.server.chei_necesare() if k.startswith('t2:'))
        if cheie not in cu_clienti and len(cu_clienti) >= MAX_PLP:
            return H.Raspuns(503, 'prea multe PLP-uri deodata')
        if self.binar is None and not self._are_rezerva():
            return H.Raspuns(501, 'lipseste bin/t2mi_decap si motor/t2mi.py')
        if len(parti) == 3:
            return H.Flux(cheie, 'video/mp2t', self.arg.cap_client * 1024)
        psi = self.psi.get(plp)
        if psi is None or (psi.complet() and self._fir is None):
            psi = self.psi[plp] = Psi()

        def servicii_gata(expirat):
            if psi.complet() or expirat:
                return H.json_raspuns({'feed': self.feed_id, 'plp': plp, 'complet': psi.complet(),
                                       'tsid': psi.pat[0] if psi.pat else None, 'onid': psi.onid,
                                       'servicii': psi.servicii()})
            return None
        return servicii_gata(False) or H.Asteapta(servicii_gata, self.arg.asteptare_servicii, (cheie,))

    def _are_rezerva(self):
        try:
            import t2mi
            return t2mi is not None
        except Exception:
            return False

    def stare(self):
        s = self.server
        st = dict(self.stare_sursa)
        st.pop('marimi', None)
        dec = {}
        for plp, d in list(self.decap.items()):
            x = {'fel': d.fel, 'intrat': d.intrat, 'iesit': d.iesit, 'aruncat': d.aruncat, 'viu': d.viu()}
            if d.fel == 'python':
                x['stare'] = dict((k, v) for k, v in d.d.stare.items() if not isinstance(v, dict))
                x['plp_uri'] = sorted(d.d.plp_uri) if isinstance(d.d.plp_uri, dict) else None
            dec[str(plp)] = x
        return {'releu': 't2', 'feed': self.feed_id, 'pid': self.pid, 'binar': self.binar, 'forma': self.forma,
                'drum': self.drum(), 'mod': 'rezerva', 'port_fluxuri': self.port_fluxuri, 'port_control': self.port_control,
                'astept_8001': bool(st.get('http_astept')),
                'sursa_activa': self._fir is not None, 'porniri': self.porniri, 'opriri': self.opriri,
                'debit_kbit': round(self._debit[2], 1), 'octeti': st.get('octeti', 0), 'sursa': st,
                'decapsulatoare': dec,
                'clienti': len(s.clienti) if s else 0,
                'abonati': dict((k, len(v)) for k, v in s.abonati.items()) if s else {},
                'http': dict(s.contoare) if s else {}, 'http_cai': dict(getattr(s, 'cereri_pe_cale', {})) if s else {}, 'erori': self.erori, 'ultima_eroare': self.ultima_eroare,
                'cpu_s': round(_ceas_procesor(), 3), 'rss_kb': H.rss_kb(), 'fire': threading.active_count()}

    # ------------------------------------------------------------ modul binar
    def mod_binar_posibil(self):
        """Binarul serveste singur fluxul: binar C adevarat, drumul 8001, nu sursa falsa, referinta purtatorului stiuta."""
        return (self.binar is not None and not self.binar.endswith('.py') and self.Dispozitiv is None
                and sys.platform != 'win32' and self.drum() == 'http8001' and bool(surse.ref_purtator(self.feed)))

    def comanda_binar(self):
        f = self.feed
        plp = _intreg(f.get('plp'))
        self.plp_binar = plp if plp is not None and 0 <= plp <= 255 else 0
        ref = str(surse.ref_purtator(f)).lstrip('/')
        gazda = str(f.get('gazda_8001') or '127.0.0.1')
        port_8001 = _intreg(f.get('port_8001'), 8001) or 8001
        termen = float(f.get('termen_8001') or TERMEN_8001_S)
        cmd = [self.binar, '-p', str(self.pid), '-u', str(self.port_fluxuri),
               '-a', '/t2/%s/%d' % (self.feed_id, self.plp_binar),
               '-h', 'http://%s:%d/%s' % (gazda, port_8001, ref),
               '-I', str(max(0, int(math.ceil(self.arg.inactiv)))), '-w', str(max(1, int(math.ceil(termen)))),
               '-R', str(CONEXIUNI_FEREASTRA),
               # -c: mereu acelasi fisier, la orice fel de pornire; releul nu il sterge si nu il goleste niciodata
               # (binarul citeste la pornire randurile lui din ultimele 120 s: asa fereastra trece peste reporniri)
               '-j', self.cale_stat, '-P', self.cale_psi, '-c', self.cale_sesiuni]
        if ts_in_pid(f):
            cmd.append('-A')           # TS intreg in payload-ul PID-ului (fara T2-MI): fara -l si -n
            return cmd
        if plp is not None:
            cmd += ['-l', str(self.plp_binar)]
        if f.get('nule'):
            cmd.append('-n')
        return cmd

    def porneste_binarul(self, asteapta_s=0.0):
        """Din firul principal. Fisierul -j apare dupa ce binarul asculta: asa se stie ca portul e al lui."""
        # fisierele ramase de la alt feed nu au voie sa raspunda la /stare sau /servicii
        for cale in (self.cale_stat, self.cale_psi):          # doar acestea doua; -c (sesiunile) ramane
            try:
                os.remove(cale)
            except OSError:
                pass
        self._stat_ultim = {}
        self._octeti_vazuti = None
        self.porniri_binar += 1
        try:
            self.proc = _popen_fara_iesiri(self.comanda_binar())
        except (OSError, ValueError) as e:
            self.proc = None
            self._iesit_la = _monoton()
            self.erori += 1
            self.ultima_eroare = 'binarul nu porneste: %s' % e
            self.jurnal(self.ultima_eroare)
            return False
        termen = _monoton() + asteapta_s
        while _monoton() < termen:
            if os.path.exists(self.cale_stat) or self.proc.poll() is not None:
                break
            time.sleep(0.02)
        return True

    def opreste_binarul(self):
        self._binar_oprit = True
        s, self._scurgator = self._scurgator, None
        if s is not None:
            s.oprire.set()
        p, self.proc = self.proc, None
        if p is None:
            return
        try:
            if p.poll() is None:
                sb, _ = self._stat_binar()
                antet_200 = bool((sb or self._stat_ultim).get('antet_200'))
                p.terminate()                  # SIGTERM: binarul scrie singur randul sesiunii 200 fara date in -c
                try:
                    _asteapta_proces(p, 2.0)
                except _TimeoutExpired:
                    p.kill()
                    _asteapta_proces(p, 2.0)
                    if antet_200:
                        self._noteaza_sesiunea_binarului('binarul omorat (SIGKILL) dupa antet 200')
        except Exception:
            pass

    def _noteaza_sesiunea_binarului(self, motiv):
        """Binarul omorat cu SIGKILL nu mai apuca sa scrie randul sesiunii in -c: il scrie releul, cu acelasi nume
        („t2mi_decap"), ca binarul urmator sa il ia in fereastra (formatul din comun/sesiuni8001.noteaza)."""
        try:
            import sesiuni8001
            if sesiuni8001.noteaza('t2mi_decap', cale=self.cale_sesiuni):
                self.randuri_releu += 1
                self.jurnal('rand in %s: %s' % (self.cale_sesiuni, motiv))
        except Exception:
            pass

    def _pauza_repornire(self):
        """Secundele de asteptat de la iesirea binarului pana la repornire: 2, 4, 8, 16, 32, apoi 60."""
        return min(PAUZA_REPORNIRE_MAX_S, PAUZA_REPORNIRE_S * 2 ** min(self._reporniri_fara_date, 16))

    def _urmareste_stat(self, acum):
        """Cel mult o data pe secunda, cat binarul traieste si pauza nu e la inceput: /stat. Date adevarate (octeti_intrare
        a crescut si iesite > 0) pun pauza de repornire inapoi la inceput. Cu pauza la inceput nu e nimic de resetat, deci
        nu se citeste (procesor: 60 de citiri pe minut in mersul normal); antet_200 se ia la iesire din fisierul -j."""
        if self._reporniri_fara_date == 0 or acum - self._stat_citit_la < 1.0:
            return
        self._stat_citit_la = acum
        sb, _ = self._stat_binar()
        if not sb:
            return
        self._stat_ultim = sb
        octeti = _intreg(sb.get('octeti_intrare'), 0)
        if self._octeti_vazuti is not None and octeti > self._octeti_vazuti and _intreg(sb.get('iesite'), 0) > 0:
            self._reporniri_fara_date = 0
        self._octeti_vazuti = octeti

    def _supravegheaza(self, acum):
        p = self.proc
        if p is not None:
            cod = p.poll()                     # culege procesul iesit (fara zombi)
            if cod is None:
                self._urmareste_stat(acum)
                return
            self.proc = None
            self.iesiri_binar += 1
            self.erori += 1
            self._iesit_la = acum
            self.ultima_eroare = 'binarul a iesit cu codul %s' % cod
            self.jurnal(self.ultima_eroare)
            # fisierul -j ramane pe disc dupa moartea binarului (se sterge doar la pornirea urmatoare): ultimul lui /stat
            if cod == -_SIGKILL and (self._stat_binar()[0] or self._stat_ultim).get('antet_200'):
                self._noteaza_sesiunea_binarului('binarul a murit cu SIGKILL dupa antet 200')
        if self._binar_oprit or acum - self._iesit_la < self._pauza_repornire():
            return
        self._reporniri = [t for t in self._reporniri if acum - t < REPORNIRI_FEREASTRA_S]
        if len(self._reporniri) >= REPORNIRI_MAX:
            if not self._binar_blocat:
                self._binar_blocat = True
                self.erori += 1
                self.ultima_eroare = 'binarul a iesit de %d ori in %d minute; astept' % (
                    REPORNIRI_MAX + 1, REPORNIRI_FEREASTRA_S // 60)
                self.jurnal(self.ultima_eroare)
            return
        self._binar_blocat = False
        self._reporniri.append(acum)
        self._reporniri_fara_date += 1
        self.porneste_binarul()

    def _stat_binar(self):
        date = citeste_mic(self.cale_stat)
        if not date:
            return {}, None
        try:
            sb = json.loads(date.decode('utf-8'))
        except ValueError:
            return {}, None
        if not isinstance(sb, dict):
            return {}, None
        try:
            varsta = round(max(0.0, time.time() - os.stat(self.cale_stat).st_mtime), 1)
        except OSError:
            varsta = None
        return sb, varsta

    def _are_asteptari(self):
        s = self.server
        return s is not None and any(c.stare == 'asteapta' for c in s.clienti.values())

    def _asigura_scurgator(self, sb):
        termen = self.arg.asteptare_servicii + 1.0
        s = self._scurgator
        if s is not None and s.is_alive():
            s.prelungeste(termen)
            return
        if sb.get('clienti'):
            return                             # playerul e deja conectat: binarul are sursa pornita
        self._scurgator = Scurgator(self.port_fluxuri, '/t2/%s/%d' % (self.feed_id, self.plp_binar), termen)
        self._scurgator.start()

    def _servicii_binar(self, plp):
        if plp != self.plp_binar:
            return H.Raspuns(404, 'PLP-ul %d nu e servit (binarul serveste PLP %d)' % (plp, self.plp_binar))
        sb, _ = self._stat_binar()
        self._asigura_scurgator(sb)
        stare = {'psi': Psi(), 'la': -1.0}

        def servicii_gata(expirat):
            acum = _monoton()
            if acum - stare['la'] >= H.PAS_S or expirat:
                stare['la'] = acum
                psi = Psi()
                viu = self.proc is not None and self.proc.poll() is None
                date = citeste_mic(self.cale_psi) if viu else None     # binar oprit: fisierul nu e de incredere
                if date:
                    psi.adauga(date)
                stare['psi'] = psi
            psi = stare['psi']
            if psi.complet() or expirat:
                return H.json_raspuns({'feed': self.feed_id, 'plp': plp, 'complet': psi.complet(),
                                       'tsid': psi.pat[0] if psi.pat else None, 'onid': psi.onid,
                                       'servicii': psi.servicii()})
            return None
        return servicii_gata(False) or H.Asteapta(servicii_gata, self.arg.asteptare_servicii, ())

    def stare_binar(self):
        acum = _monoton()
        sb, varsta = self._stat_binar()
        octeti = _intreg(sb.get('octeti_intrare'), 0)
        t0, o0, debit = self._debit_binar
        if o0 is None or octeti < o0:
            self._debit_binar = (acum, octeti, 0.0)
        elif acum - t0 >= 1.0:
            debit = (octeti - o0) * 8 / 1000.0 / (acum - t0)
            self._debit_binar = (acum, octeti, debit)
        p = self.proc
        viu = p is not None and p.poll() is None
        pid = p.pid if p is not None else None
        hs = sb.get('http_stare')
        s = self.server
        return {'releu': 't2', 'feed': self.feed_id, 'pid': self.pid, 'binar': self.binar, 'forma': 'ts188',
                'drum': 'http8001', 'mod': 'binar', 'port_fluxuri': self.port_fluxuri, 'port_control': self.port_control,
                'astept_8001': hs in ('conectare', 'astept_date', 'pauza', 'limita'),
                'sursa_activa': bool(hs) and hs != 'asteapta_client',
                'debit_kbit': round(debit, 1), 'octeti': octeti,
                'sursa': {'http_stare': hs, 'http_conectari': sb.get('conectari'), 'http_ocupat': sb.get('ocupat_400'),
                          'http_ultima_eroare': sb.get('eroare_ultima'), 'octeti': octeti},
                'decapsulatoare': {str(self.plp_binar): {
                    'fel': 'binar', 'intrat': octeti, 'iesit': _intreg(sb.get('iesite'), 0) * 188,
                    'aruncat': _intreg(sb.get('aruncate'), 0) * 188, 'viu': viu}},
                'clienti': _intreg(sb.get('clienti'), 0), 'clienti_aruncati': sb.get('clienti_aruncati'),
                'sesiuni_8001': sb.get('sesiuni_8001'),
                # campurile noi ale binarului (defectul 10): pluginul poate renunta mai devreme cand binarul e in limita
                'pauza_ramasa_ms': sb.get('pauza_ramasa_ms'), 'conexiuni_fereastra': sb.get('conexiuni_fereastra'),
                'sesiuni_fereastra': sb.get('sesiuni_fereastra'), 'pauza_idx': sb.get('pauza_idx'),
                'antet_200': sb.get('antet_200'),
                'pauza_repornire_s': self._pauza_repornire(), 'reporniri_fara_date': self._reporniri_fara_date,
                'randuri_sesiuni_releu': self.randuri_releu,
                'erori': self.erori, 'ultima_eroare': self.ultima_eroare or sb.get('eroare_ultima') or '',
                'porniri_binar': self.porniri_binar, 'iesiri_binar': self.iesiri_binar, 'pid_binar': pid,
                'cpu_s': round(_ceas_procesor(), 3), 'rss_kb': H.rss_kb(),
                'cpu_binar_s': cpu_proces(pid) if viu else None, 'rss_binar_kb': rss_proces_kb(pid) if viu else None,
                'stat_binar': sb, 'stat_varsta_s': varsta,
                'http': dict(s.contoare) if s else {}, 'http_cai': dict(getattr(s, 'cereri_pe_cale', {})) if s else {}, 'fire': threading.active_count()}

    def _tic_binar(self, acum):
        self._supravegheaza(acum)
        s = self._scurgator
        if s is not None and (not s.is_alive() or not self._are_asteptari()):
            s.oprire.set()
            self._scurgator = None
        if self.arg.iesi_fara_clienti and acum - self._verificat_la >= 1.0:
            self._verificat_la = acum
            sb, _ = self._stat_binar()
            if sb.get('clienti') or self._are_asteptari():
                self._folosit_la = acum
            elif acum - self._folosit_la >= self.arg.inactiv:
                self.server.opreste(0)

    def la_tic(self, acum):
        if self.mod_binar:
            return self._tic_binar(acum)
        necesare = self.server.chei_necesare()
        noi = set(k for k in necesare if k.startswith('t2:') and k not in self.chei_active)
        if noi:
            # loc pentru PLP-ul cerut: PLP-urile pornite dar fara clienti se opresc acum, nu dupa --inactiv
            libere = [k for k in self.chei_active if k.startswith('t2:') and k not in necesare]
            while libere and len(self.chei_active) + len(noi) > MAX_PLP:
                k = libere.pop()
                self.chei_active.discard(k)
                self.viata.get('ultim', {}).pop(k, None)
        for plp, psi in list(self.psi.items()):
            d = self.decap.get(plp)
            if d is not None and d.psi is not psi and not psi.complet():
                d.psi = psi
            elif d is not None and d.psi is not None and d.psi.complet():
                d.psi = None                       # gata: nu mai cautam PSI in flux
        H.ciclu_viata(self.server, self.chei_active, self._porneste_cheie, self._opreste_cheie,
                      self.arg.inactiv, self.arg.iesi_fara_clienti, self.viata)
        # PLP-urile raman decapsulate si in cele --inactiv secunde de dupa plecarea clientului (zap inapoi rapid)
        dorite = frozenset(int(k[3:]) for k in self.chei_active if k.startswith('t2:'))
        if dorite != self.plp_dorite:
            self.plp_dorite = dorite
        t0, o0, _ = self._debit
        if acum - t0 >= 2.0:
            o = self.stare_sursa.get('octeti', 0)
            self._debit = (acum, o, max(0.0, (o - o0) * 8 / 1000 / (acum - t0)))

    def _porneste_cheie(self, k):
        if self._fir is None:
            self._porneste_sursa()

    def _opreste_cheie(self, k):
        if not (self.chei_active - {k}):
            self._opreste_sursa()
            self.plp_dorite = frozenset()

    # ------------------------------------------------------------ sursa
    def _porneste_sursa(self):
        if self._fir_vechi is not None and self._fir_vechi.is_alive():
            self._fir_vechi.join(2.0)
        self._oprire = threading.Event()
        self.porniri += 1
        self._fir = _fir(self._fir_date, 'date-t2', (self._oprire,))
        self._fir.start()

    def _opreste_sursa(self):
        if self._fir is None:
            return
        self._oprire.set()
        self._fir_vechi = self._fir
        self._fir = None
        self.opriri += 1

    def _fa_decap(self, plp, forma, fd=None):
        if self.binar:
            return DecapBinar(self, self.binar, plp, forma, stdin=fd)
        return DecapPython(self, plp, forma)

    def _sincronizeaza(self, forma, fd=None):
        dorite = self.plp_dorite
        for plp in [p for p in self.decap if p not in dorite]:
            self.decap.pop(plp).opreste()
        for plp in dorite:
            d = self.decap.get(plp)
            if d is not None and not d.viu():
                self.decap.pop(plp).opreste()
                self.erori += 1
                self.ultima_eroare = 'decapsulatorul PLP %d a iesit' % plp
                d = None
            if d is None:
                self.decap[plp] = self._fa_decap(plp, forma, fd)

    def _fir_date(self, oprire):
        try:
            while not oprire.is_set():
                try:
                    if self.feed.get('direct') and self.binar and self.Dispozitiv is None:
                        self._direct(oprire)
                    else:
                        self._prin_python(oprire)
                    if not oprire.is_set():
                        raise EOFError('sursa s-a terminat')
                except Exception as e:
                    if oprire.is_set():
                        break
                    self.erori += 1
                    self.ultima_eroare = '%s: %s' % (type(e).__name__, e)
                    self.jurnal('sursa: %s' % self.ultima_eroare)
                    for d in list(self.decap.values()):
                        d.opreste()
                    self.decap = {}
                    oprire.wait(1.0)
        finally:
            for d in list(self.decap.values()):
                d.opreste()
            self.decap = {}

    def _prin_python(self, oprire):
        f = self.feed
        st = surse.stare_noua()
        self.stare_sursa = st
        forma_ceruta = f.get('forma') or 'auto'
        drum = self.drum()
        ref = surse.ref_purtator(f) if drum == 'http8001' else f.get('ref')
        if drum == 'http8001' and not ref:
            raise ValueError('feed-ul nu are referinta purtatorului (ref_8001 sau purtator: sid, tsid, onid, ns)')
        st['ref'] = ref
        src = surse.pachete_ts(self.pid, drum, int(f.get('adapter') or 0), int(f.get('demux') or 0),
                               ref=ref, fifo=f.get('fifo'), forma=forma_ceruta, oprire=oprire, stare=st,
                               Dispozitiv=self.Dispozitiv, impacheteaza=False,
                               gazda_8001=str(f.get('gazda_8001') or '127.0.0.1'), port_8001=int(f.get('port_8001') or 8001),
                               termen_8001=float(f.get('termen_8001') or TERMEN_8001_S))
        try:
            dorite_vazute = None
            for bloc in src:
                if oprire.is_set():
                    return
                if self.plp_dorite is not dorite_vazute:
                    dorite_vazute = self.plp_dorite
                    self.forma = st['forma']
                    self._sincronizeaza(st['forma'] or 'ts188')
                for d in tuple(self.decap.values()):
                    d.scrie(bloc)
        finally:
            src.close()

    def drum(self):
        """Implicit portul 8001 pe serviciul purtator (singurul drum T2-MI fara pierderi dovedit pe receptor);
        sursa falsa din probe inlocuieste demux-ul, deci merge pe 'tap'."""
        if self.feed.get('drum_ts'):
            return str(self.feed['drum_ts'])
        return 'tap' if self.Dispozitiv is not None else 'http8001'

    def _direct(self, oprire):
        """Binarul citeste fd-ul demux-ului; Python doar tine filtrul si asteapta oprirea."""
        f = self.feed
        dev = surse.Demux(int(f.get('adapter') or 0), int(f.get('demux') or 0))
        try:
            dev.buffer(surse.BUFFER_DEMUX)            # REGULA 1 din surse.py: cel mult 1 MB
            dev.filtru_pes(self.pid, surse.DMX_OUT_TAP)
            self.forma = f.get('forma') or 'ts188'
            self.stare_sursa = surse.stare_noua()
            self.stare_sursa['sursa'] = 'direct fd demux pid 0x%04X' % self.pid
            dorite_vazute = None
            while not oprire.is_set():
                if self.plp_dorite is not dorite_vazute:
                    dorite_vazute = self.plp_dorite
                    self._sincronizeaza(self.forma, fd=dev.fd)
                oprire.wait(0.25)
        finally:
            for d in list(self.decap.values()):
                d.opreste()
            self.decap = {}
            dev.inchide()


def citeste_feed(cale):
    with open(cale, 'rb') as f:
        date = json.loads(f.read(1024 * 1024).decode('utf-8'))
    if isinstance(date, dict) and isinstance(date.get('feeduri'), list):
        t2 = [x for x in date['feeduri'] if x.get('tip', 't2') == 't2']
        if not t2:
            raise ValueError('niciun feed T2 in fisier')
        baza = dict((k, v) for k, v in date.items() if k != 'feeduri')
        baza.update(t2[0])
        date = baza
    if not isinstance(date, dict) or not date.get('id'):
        raise ValueError('feed fara id')
    return date


def main(argv=None):
    H.muta_erorile()
    arg = H.citeste_argumente(sys.argv[1:] if argv is None else argv, {
        '--port': (int, None), '--port-control': (int, None), '--gazda': (str, '127.0.0.1'), '--inactiv': (float, 10.0),
        '--binar': (str, None), '--asteptare-servicii': (float, ASTEPTARE_SERVICII_S),
        '--cap-client': (int, CAP_CLIENT // 1024), '--sursa-falsa': (str, None), '--debit-fals': (float, 8000.0),
        '--fisier-stat': (str, None), '--fisier-psi': (str, None), '--fisier-sesiuni': (str, None)},
        ('--iesi-fara-clienti', '--fara-binar'), ('feed',), 'Releul DVB-T2 din satelit (hdsatelit.com)')
    jurnal = Jurnal()
    try:
        if hasattr(os, 'nice') and os.nice(0) < 10:
            os.nice(10 - os.nice(0))
    except OSError:
        pass
    feed = citeste_feed(arg.feed)
    port = arg.port if arg.port is not None else int(feed.get('http_port') or 8889)
    port_control = arg.port_control if arg.port_control is not None else _intreg(feed.get('port_control'))
    if not port_control or port_control == port:
        port_control = port + 1
    releu = ReleuT2(feed, arg, jurnal)
    if arg.fara_binar:
        releu.binar = None
    releu.port_fluxuri = port
    releu.port_control = port_control
    releu.mod_binar = releu.mod_binar_posibil()
    if releu.mod_binar:
        # Python doar pe portul de control; fluxul il serveste binarul pe portul fluxurilor
        server = H.Server(releu.handler, releu.la_tic, port=port_control, gazda=arg.gazda, coada_max=1024 * 1024,
                          jurnal=jurnal)
        releu.server = server
        releu.porneste_binarul(asteapta_s=2.0)
        descriere = 'binar:%s' % releu.binar
    else:
        try:
            server = H.Server(releu.handler, releu.la_tic, port=port, gazda=arg.gazda, coada_max=16 * 1024 * 1024,
                              jurnal=jurnal, porturi_extra=(port_control,))
        except (OSError, socket.error) as e:
            # rezerva: fara portul de control merge si asa (acelasi handler raspunde pe portul fluxurilor)
            jurnal('portul de control %d: %s' % (port_control, e))
            server = H.Server(releu.handler, releu.la_tic, port=port, gazda=arg.gazda, coada_max=16 * 1024 * 1024,
                              jurnal=jurnal)
        releu.server = server
        releu.port_fluxuri = server.port
        releu.port_control = server.porturi_extra[0] if server.porturi_extra else None
        descriere = releu.binar or 't2mi.py'

    def la_semnal(nr, cadru):
        server.opreste(0)
    for nume in ('SIGTERM', 'SIGINT'):
        try:
            signal.signal(getattr(signal, nume), la_semnal)
        except (AttributeError, ValueError, OSError):
            pass
    try:
        sys.stdout.write('ASCULT %s %s %s\n' % (releu.port_fluxuri, releu.port_control, descriere))
        sys.stdout.flush()
    except Exception:
        pass
    try:
        return server.ruleaza()
    finally:
        releu.opreste_binarul()
        releu._opreste_sursa()
        if releu._fir_vechi is not None:
            releu._fir_vechi.join(2.0)


if __name__ == '__main__':
    sys.exit(main())
