# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""De unde vin datele pentru releele HdsDab si HdsT2mi. Facut de hdsatelit.com.
Ruleaza DOAR in procesul separat al releului, niciodata in enigma2.

  sectiuni(pid, adapter=0, demux=0)       -> iterator de sectiuni intregi (filtru de sectiuni sau TAP)
  udp_din_mpe(sectiuni_iter, ip, port)    -> iterator de sarcini UDP din datagram_section (EN 301 192)
  pachete_ts(pid, fel='auto')             -> iterator de blocuri de pachete TS de 188, aliniate
      fel: 'tap' (DMX_SET_PES_FILTER output=1 pe demux), 'dvr' (output=2 + dvr0),
           'http8001' (http://127.0.0.1:8001/<ref>), 'fifo' (inregistrare in FIFO), 'auto' (= 'tap')
      DOVEDIT pe receptor: T2-MI fara pierderi vine DOAR prin 'http8001' pe serviciul purtator (ref_purtator);
      TAP pierde ~35%, sectiunile taie fluxul, TS_TAP/dvr dau 0.

Fapte dovedite pe HiSilicon 3798mv200:
  - DMX_SET_FILTER fara masca de table_id, flags 4: merge, un read() = o sectiune.
  - DMX_SET_PES_FILTER output=1 (TAP) pe un PID MPE: driverul reasambleaza, un read() = o sectiune intreaga.
  - output=2 si output=3: 0 octeti. Portul 8001 cu tunerul tinut brut: 200 si apoi „400 Bad Request" in corp.
  - Ce da TAP pe un PID T2-MI nu e inca stiut: pachete_ts detecteaza forma la pornire (stare['forma']):
    'ts188' (0x47 la fiecare 188 octeti) sau 'sarcina' (unitati fara antete TS, impachetate aici la loc in TS).

Pe calculator dispozitivele nu exista: clasele Demux/CititorFd se pot inlocui cu surse false (vezi probe).
REGULI DE MEMORIE (DOVEDITE pe receptor, obligatorii):
  1. DMX_SET_BUFFER_SIZE cel mult 1 MB. Probe cu 8-32 MB au lasat decodorul video HiSilicon fara memorie
     („VDEC_Chan_AllocMem no memory"): niciun canal nu mai avea imagine, a trebuit repornire completa.
     Se cere 1 MB; daca driverul refuza, ramane marimea implicita (nu se incearca alta).
  2. Nimic mare in /tmp: e RAM si concureaza cu decodorul. Releele nu scriu fisiere de date; jurnalul pe stderr
     are plafon; drumul 'fifo' primeste doar un FIFO adevarat (un fisier obisnuit in /tmp ar umple memoria).
Merge pe Python 3 si pe Python 2.7 (imagini vechi): pe 2.7 citirile ies ca bytearray, ca indexul sa dea numere."""
from __future__ import division

import errno
import os
import select
import socket
import struct
import sys
import time

if sys.version_info[0] < 3:                           # Python 2.7: aceleasi nume ca pe Python 3, din compat.py
    try:
        from compat import (monoton as _monoton, citeste_fd as _citeste_fd, primeste as _primeste,
                            BlockingIOError, InterruptedError)
    except ImportError:
        from .compat import (monoton as _monoton, citeste_fd as _citeste_fd, primeste as _primeste,
                             BlockingIOError, InterruptedError)
    OSError = EnvironmentError                        # noqa: A001  (pe 2.7 IOError si socket.error nu sunt OSError)
    _TEXT = basestring                                # noqa: F821  (JSON da unicode pe 2.7)
    _lipeste = bytearray().join                       # b''.join nu primeste bytearray pe 2.7
else:
    _monoton = time.monotonic
    _citeste_fd = os.read
    _primeste = socket.socket.recv
    _TEXT = str
    _lipeste = b''.join

DMX_STOP = 0x6f2a
DMX_SET_FILTER = 0x403c6f2b
DMX_SET_PES_FILTER = 0x40146f2c
DMX_SET_BUFFER_SIZE = 0x6f2d
DMX_IN_FRONTEND = 0
DMX_OUT_DECODER, DMX_OUT_TAP, DMX_OUT_TS_TAP, DMX_OUT_TSDEMUX_TAP = 0, 1, 2, 3
DMX_PES_OTHER = 20
DMX_IMMEDIATE_START = 4

_FILTRU_SCT = struct.Struct('=H2x16s16s16sII')    # dmx_sct_filter_params, 60 octeti
_FILTRU_PES = struct.Struct('=H2xIIII')           # dmx_pes_filter_params, 20 octeti
_ZERO16 = b'\0' * 16
CITIRE = 65536                                    # un read() pe TAP intoarce o unitate intreaga: nu se citeste mic
BUFFER_DEMUX_MAX = 1024 * 1024                    # REGULA 1: niciodata peste 1 MB (decodorul video ramane fara memorie)
BUFFER_DEMUX = BUFFER_DEMUX_MAX
SOCLU_8001 = 1024 * 1024                          # tampon de primire pentru 8001 (memorie de nucleu, tot RAM)
_EOVERFLOW = getattr(errno, 'EOVERFLOW', 75)
_REPETA = (errno.EAGAIN, errno.EINTR, getattr(errno, 'EWOULDBLOCK', errno.EAGAIN))


def stare_noua():
    return {'citiri': 0, 'octeti': 0, 'depasiri': 0, 'goale': 0, 'erori': 0, 'sectiuni': 0, 'sectiuni_rele': 0,
            'udp': 0, 'udp_altele': 0, 'pachete_ts': 0, 'resincronizari': 0, 'forma': None, 'marimi': [],
            'pornit': time.time()}


# ---------------------------------------------------------------- dispozitive (doar pe receptor)
class Demux(object):
    """/dev/dvb/adapterA/demuxD. Singurul loc cu ioctl."""

    def __init__(self, adapter=0, demux=0):
        import fcntl                                  # lenes: nu exista pe Windows
        self._ioctl = fcntl.ioctl
        cale = '/dev/dvb/adapter%d/demux%d' % (adapter, demux)
        try:
            self.fd = os.open(cale, os.O_RDWR | os.O_NONBLOCK)
        except OSError:
            self.fd = os.open(cale, os.O_RDONLY | os.O_NONBLOCK)

    def buffer(self, marime=BUFFER_DEMUX):
        """REGULA 1: se cere cel mult 1 MB; refuzat -> ramane implicitul, fara alta incercare.
        Intoarce marimea ceruta si acceptata, sau 0 daca a ramas implicitul."""
        marime = min(int(marime), BUFFER_DEMUX_MAX)
        try:
            self._ioctl(self.fd, DMX_SET_BUFFER_SIZE, marime)
            return marime
        except OSError:
            return 0

    def filtru_sectiuni(self, pid, flags=DMX_IMMEDIATE_START):
        # fara masca de table_id: pe HiSilicon masca 0x3E nu lasa nimic sa treaca
        self._ioctl(self.fd, DMX_SET_FILTER, _FILTRU_SCT.pack(pid, _ZERO16, _ZERO16, _ZERO16, 0, flags))

    def filtru_pes(self, pid, output=DMX_OUT_TAP, pes_type=DMX_PES_OTHER, flags=DMX_IMMEDIATE_START):
        self._ioctl(self.fd, DMX_SET_PES_FILTER, _FILTRU_PES.pack(pid, DMX_IN_FRONTEND, output, pes_type, flags))

    def citeste(self, timeout, marime=CITIRE):
        try:                                          # fd neblocant: intai read, select doar cand e gol
            return _citeste_fd(self.fd, marime)
        except BlockingIOError:
            pass
        r, _, _ = select.select([self.fd], [], [], timeout)
        if not r:
            return None
        return os.read(self.fd, marime)

    def inchide(self):
        fd, self.fd = self.fd, -1
        if fd < 0:
            return
        try:
            self._ioctl(fd, DMX_STOP)
        except OSError:
            pass
        try:
            os.close(fd)
        except OSError:
            pass


class CititorFd(object):
    """Dispozitiv de caractere sau FIFO (dvr0, inregistrare), neblocant, cu select. REGULA 2: un fisier obisnuit
    se refuza (o inregistrare intr-un fisier din /tmp ar umple RAM-ul decodorului)."""

    def __init__(self, cale):
        import stat
        try:
            mod = os.stat(cale).st_mode
        except OSError:
            mod = None
        if mod is not None and not (stat.S_ISFIFO(mod) or stat.S_ISCHR(mod)):
            raise ValueError('%s nu e FIFO sau dispozitiv: nu se citesc/scriu fisiere mari in /tmp' % cale)
        self.fd = os.open(cale, os.O_RDONLY | getattr(os, 'O_NONBLOCK', 0))

    def citeste(self, timeout, marime=CITIRE):
        try:
            b = _citeste_fd(self.fd, marime)
            if b:
                return b
        except BlockingIOError:
            pass
        r, _, _ = select.select([self.fd], [], [], timeout)
        if not r:
            return None
        return os.read(self.fd, marime)

    def inchide(self):
        fd, self.fd = self.fd, -1
        if fd >= 0:
            try:
                os.close(fd)
            except OSError:
                pass


class TunerOcupat(OSError):
    """enigma2 a raspuns 200 si apoi HTTP/1.x 400 in corp: nu poate porni serviciul (tuner ocupat)."""


class CititorHttp(object):
    """Flux TS din serverul de stream al enigma2 (portul 8001). Streamserverul acordeaza singur tunerul (si
    roteste antena), deci primele date pot veni tarziu: se asteapta pana la termen_date secunde. Antetul HTTP se
    sare; daca in corp vine alt raspuns HTTP se ridica TunerOcupat. Soclul e neblocant: intai recv, select doar
    cand nu sunt date."""

    def __init__(self, url_cale, gazda='127.0.0.1', port=8001, timeout=5.0, termen_date=90.0, la_sesiune=None):
        # la_sesiune(): chemat o data, cand enigma2 a pornit o sesiune (200 fara eroare in corp, sau 200 si inchidere
        # fara date: si atunci driverul poate fi pierdut deja zona de 4 MB). Vezi comun/sesiuni8001.py.
        self._la_sesiune = la_sesiune
        self.sesiune = False
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            try:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, SOCLU_8001)
            except OSError:
                pass
            s.settimeout(timeout)
            s.connect((gazda, port))
            s.sendall(('GET /%s HTTP/1.0\r\nHost: %s\r\nUser-Agent: hdsatelit\r\n\r\n'
                       % (url_cale.lstrip('/'), gazda)).encode('ascii'))
            s.setblocking(False)
        except Exception:
            s.close()
            raise
        self.s = s
        self._antet = bytearray()
        self._corp = None                 # primii octeti din corp, pana se vede ca nu e alt raspuns HTTP
        self._inceput = True
        self._termen = _monoton() + termen_date
        self.fd = s.fileno()

    def _ocupat(self):
        return TunerOcupat(errno.EBUSY, 'serviciul nu porneste: %s'
                           % bytes(self._corp[:40]).decode('latin-1', 'replace').strip())

    def _noteaza_sesiunea(self):
        if self.sesiune:
            return
        self.sesiune = True
        if self._la_sesiune is not None:
            try:
                self._la_sesiune()
            except Exception:
                pass

    def citeste(self, timeout, marime=CITIRE):
        s = self.s
        if s is None:
            raise OSError(errno.EBADF, 'inchis')
        try:
            b = _primeste(s, marime)
        except (BlockingIOError, InterruptedError):
            if self._inceput and _monoton() > self._termen:
                raise OSError(errno.ETIMEDOUT, 'portul 8001 nu a dat date in termen')
            r, _, _ = select.select([s], [], [], timeout)
            if not r:
                return None
            try:
                b = _primeste(s, marime)
            except (BlockingIOError, InterruptedError):
                return None
        if not b:
            if self._inceput and self._corp is not None and self._corp[:7] == b'HTTP/1.':
                raise self._ocupat()
            if self._corp is not None or not self._inceput:
                self._noteaza_sesiunea()                  # 200 si apoi inchidere: se numara (cazul prudent)
            raise EOFError('serverul a inchis fluxul')
        if not self._inceput:
            return b
        if self._corp is None:
            self._antet += b
            i = self._antet.find(b'\r\n\r\n')
            if i < 0:
                if len(self._antet) > 16384:
                    raise OSError(errno.EPROTO, 'antet HTTP prea lung')
                return None
            linie = bytes(self._antet[:self._antet.find(b'\r\n')])
            if b' 200' not in linie:
                raise OSError(errno.EPROTO, 'raspuns HTTP: %s' % linie[:60].decode('latin-1', 'replace'))
            self._corp = bytearray(self._antet[i + 4:])
            self._antet = None
        else:
            self._corp += b
        if len(self._corp) < 12:
            return None
        if self._corp[:7] == b'HTTP/1.' and b' 200' not in self._corp[:16]:
            raise self._ocupat()
        self._inceput = False
        self._noteaza_sesiunea()
        rest = bytes(self._corp)
        self._corp = None
        return rest

    def inchide(self):
        s, self.s = self.s, None
        if s is not None:
            try:
                s.close()
            except OSError:
                pass


def ref_purtator(feed):
    """Referinta serviciului purtator pentru portul 8001: feed['ref_8001'] sau feed['ref'] daca exista, altfel
    1:0:1:SID:TSID:ONID:NS:0:0:0: din feed['purtator'] (sau din campurile sid/tsid/onid/ns ale feed-ului).
    Numerele: intregi, sau text hex cu 0x."""
    for k in ('ref_8001', 'ref'):
        if feed.get(k):
            return str(feed[k])
    p = feed.get('purtator') if isinstance(feed.get('purtator'), dict) else feed

    def nr(v):
        if isinstance(v, _TEXT):
            v = v.strip()
            return int(v, 16) if v.lower().startswith('0x') else int(v)
        return int(v)
    try:
        sid, tsid, onid, ns = (nr(p[k]) for k in ('sid', 'tsid', 'onid', 'ns'))
    except (KeyError, TypeError, ValueError):
        return None
    return '1:0:1:%X:%X:%X:%X:0:0:0:' % (sid, tsid, onid, ns)


SESIUNI_8001_FEREASTRA = 4          # cel mult atatea sesiuni 8001 noi...
FEREASTRA_8001_S = 120.0            # ...in atatea secunde (fiecare sesiune pierde ~4 MB vmalloc in driverul HiSilicon)
PAUZA_8001_MAX_S = 30.0
DATE_BUNE_RESET_S = 60.0            # dupa atatea secunde de date bune pauza revine la cea de pornire


class LimitaSesiuni(object):
    """Pauze crescatoare intre reconectari si cel mult `maxim` sesiuni pe fereastra glisanta. Ceasul se poate da (probe)."""

    def __init__(self, pauza=3.0, maxim=SESIUNI_8001_FEREASTRA, fereastra=FEREASTRA_8001_S, pauza_max=PAUZA_8001_MAX_S,
                 ceas=None):
        self.pauza_start = max(0.0, float(pauza))
        self.pauza = self.pauza_start
        self.maxim = maxim
        self.fereastra = fereastra
        self.pauza_max = pauza_max
        self.ceas = ceas or _monoton
        self.sesiuni = []

    def sesiune(self):
        acum = self.ceas()
        self.sesiuni = [t for t in self.sesiuni if acum - t < self.fereastra] + [acum]

    def date_bune(self, de_cand_s):
        if de_cand_s >= DATE_BUNE_RESET_S:
            self.pauza = self.pauza_start

    def urmatoarea_pauza(self):
        """Secundele de asteptat inainte de urmatoarea incercare (creste pauza pentru data viitoare)."""
        acum = self.ceas()
        self.sesiuni = [t for t in self.sesiuni if acum - t < self.fereastra]
        p = self.pauza
        self.pauza = min(self.pauza_max, max(self.pauza_start, self.pauza * 2 or 1.0))
        if len(self.sesiuni) >= self.maxim:
            p = max(p, self.sesiuni[0] + self.fereastra - acum)
        return p


_LIMITE = {}


def _noteaza_sesiune_8001(stare, cine):
    stare['sesiuni_8001'] = stare.get('sesiuni_8001', 0) + 1
    try:
        try:
            from . import sesiuni8001
        except (ImportError, ValueError, SystemError):
            import sesiuni8001
        sesiuni8001.noteaza(cine)
    except Exception:
        pass


def _gen_http(ref, oprire, stare, gazda, port, termen_date, pauza, CititorFlux, cine='releu'):
    """Citiri din 8001 cu reconectare: tuner ocupat (400 in corp), refuz, termen depasit sau flux inchis ->
    pauza si din nou, pana la oprire. Consumatorul (decapsulatorul) ramane pornit intre incercari.
    Fiecare sesiune 8001 pierde memorie in driver: pauzele cresc (pauza, 2x, ... pana la 30 s) si se deschid cel mult
    SESIUNI_8001_FEREASTRA sesiuni pe FEREASTRA_8001_S; sesiunile se numara in /tmp/hds-8001-sesiuni."""
    # o limita pe proces si pe serviciu: supravietuieste redeschiderii sursei de catre releu
    cheie = (gazda, port, ref)
    limita = _LIMITE.get(cheie)
    if limita is None:
        if len(_LIMITE) > 16:
            _LIMITE.clear()
        limita = _LIMITE[cheie] = LimitaSesiuni(pauza)

    def asteapta():
        p = limita.urmatoarea_pauza()
        stare['http_pauza_s'] = round(p, 1)
        if oprire is None:
            time.sleep(p)
            return False
        return oprire.wait(p)

    def la_sesiune():
        limita.sesiune()
        _noteaza_sesiune_8001(stare, cine)
    while oprire is None or not oprire.is_set():
        stare['http_incercari'] = stare.get('http_incercari', 0) + 1
        stare['http_astept'] = True
        try:
            if CititorFlux is None:
                dev = CititorHttp(ref, gazda=gazda, port=port, termen_date=termen_date, la_sesiune=la_sesiune)
            else:
                dev = CititorFlux(ref)
                if getattr(dev, 'sesiune_la_conectare', False):
                    la_sesiune()
        except OSError as e:
            stare['http_ultima_eroare'] = '%s: %s' % (type(e).__name__, e)
            if asteapta():
                return
            continue
        date_de_la = None
        try:
            for b in _citiri(dev, oprire, stare):
                if stare['http_astept']:
                    stare['http_astept'] = False
                    stare['http_conectari'] = stare.get('http_conectari', 0) + 1
                    date_de_la = _monoton()
                yield b
            return                                        # oprire
        except TunerOcupat as e:
            stare['http_ocupat'] = stare.get('http_ocupat', 0) + 1
            stare['http_ultima_eroare'] = str(e)
        except (OSError, EOFError) as e:
            stare['http_ultima_eroare'] = '%s: %s' % (type(e).__name__, e)
        if date_de_la is not None:
            limita.date_bune(_monoton() - date_de_la)
        if asteapta():
            return


# ---------------------------------------------------------------- bucla de citire comuna
def _citiri(dev, oprire, stare, timeout=0.5, marime=CITIRE):
    """Citiri dintr-un dispozitiv pana la oprire. EOVERFLOW numarat, EAGAIN/EINTR ignorate."""
    cit = dev.citeste
    try:
        while oprire is None or not oprire.is_set():
            try:
                b = cit(timeout, marime)
            except OSError as e:
                if e.errno == _EOVERFLOW:
                    stare['depasiri'] += 1
                    continue
                if e.errno in _REPETA:
                    continue
                raise
            if b is None:
                continue
            if not b:
                stare['goale'] += 1
                if stare['goale'] % 64 == 0:
                    time.sleep(0.01)                  # nu se invarte pe loc daca driverul da 0 octeti
                continue
            stare['citiri'] += 1
            stare['octeti'] += len(b)
            yield b
    finally:
        dev.inchide()


class _Sursa(object):
    """Iterator cu stare si oprire; oprirea inchide dispozitivul la urmatoarea iesire din select (<= 0,5 s)."""

    def __init__(self, gen, stare, oprire, dev=None):
        self._gen = gen
        self.stare = stare
        self.oprire = oprire
        self.dev = dev

    def __iter__(self):
        return self

    def __next__(self):
        return next(self._gen)

    next = __next__                                   # protocolul de iterator de pe Python 2.7

    def opreste(self):
        if self.oprire is not None:
            self.oprire.set()

    def close(self):
        self._gen.close()


class _Oprire(object):
    """Ca threading.Event, fara fir (setat din alt fir, citit in bucla)."""
    __slots__ = ('_v',)

    def __init__(self):
        self._v = False

    def set(self):
        self._v = True

    def is_set(self):
        return self._v

    def wait(self, secunde):
        capat = _monoton() + secunde
        while not self._v and _monoton() < capat:
            time.sleep(0.05)
        return self._v


# ---------------------------------------------------------------- sectiuni
def imparte_sectiuni(bloc, stare):
    """O citire -> sectiuni intregi. De obicei o citire e exact o sectiune (drumul rapid)."""
    n = len(bloc)
    if n >= 3:
        lung = 3 + (((bloc[1] & 0x0F) << 8) | bloc[2])
        if lung == n:
            stare['sectiuni'] += 1
            yield bloc
            return
    o = 0
    while o + 3 <= n:
        if bloc[o] == 0xFF:                              # umplutura dupa ultima sectiune
            return
        lung = 3 + (((bloc[o + 1] & 0x0F) << 8) | bloc[o + 2])
        if o + lung > n:
            stare['sectiuni_rele'] += 1
            return
        stare['sectiuni'] += 1
        yield bloc[o:o + lung]
        o += lung


def _gen_sectiuni(citiri, stare):
    # drumul rapid (o citire = o sectiune) fara generator nou pe fiecare citire
    for b in citiri:
        n = len(b)
        if n >= 3 and 3 + (((b[1] & 0x0F) << 8) | b[2]) == n:
            stare['sectiuni'] += 1
            yield b
        else:
            for s in imparte_sectiuni(b, stare):        # fara `yield from`: fisierul se compileaza si pe 2.7
                yield s


def sectiuni(pid, adapter=0, demux=0, cale='filtru', oprire=None, stare=None, Dispozitiv=None):
    """Sectiuni intregi de pe un PID. cale 'filtru' (DMX_SET_FILTER, dovedit) sau 'tap' (PES output=1, dovedit)."""
    stare = stare if stare is not None else stare_noua()
    oprire = oprire if oprire is not None else _Oprire()
    dev = (Dispozitiv or Demux)(adapter, demux)
    try:
        stare['buffer_demux'] = dev.buffer(BUFFER_DEMUX)
        if cale == 'tap':
            dev.filtru_pes(pid, DMX_OUT_TAP)
        else:
            dev.filtru_sectiuni(pid)
    except Exception:
        dev.inchide()
        raise
    stare['sursa'] = 'sectiuni-%s pid 0x%04X' % (cale, pid)
    return _Sursa(_gen_sectiuni(_citiri(dev, oprire, stare), stare), stare, oprire, dev)


# ---------------------------------------------------------------- MPE -> UDP
_IPV4 = struct.Struct('>BxHxxHBB2x4s4s')             # ver/ihl, total, flags+frag, ttl, proto, sursa, dest
_IPV4_UDP = struct.Struct('>B5xHxB6x4s2xHH')         # ver/ihl, flags+frag, proto, dest; UDP (fara optiuni IP): port dest, lungime
_UDP = struct.Struct('>2xHH')                        # port dest, lungime
_LLC_IPV4 = b'\xaa\xaa\x03\x00\x00\x00\x08\x00'


def udp_din_mpe(sectiuni_iter, ip, port, stare=None):
    """datagram_section (table_id 0x3E) -> sarcina UDP pentru ip:port (ip '' sau None = orice, port 0 = orice).
    Fara CRC32 in Python (scump); EDI are CRC propriu pe PF si AF. Fragmentele IP nu se reasambleaza."""
    stare = stare if stare is not None else stare_noua()
    dest = socket.inet_aton(ip) if ip else None
    port = int(port or 0)
    un_ipv4 = _IPV4_UDP.unpack_from
    un_udp = _UDP.unpack_from
    for s in sectiuni_iter:
        n = len(s)
        if n < 12 + 28 + 4 or s[0] != 0x3E:
            stare['udp_altele'] += 1
            continue
        capat = 3 + (((s[1] & 0x0F) << 8) | s[2]) - 4    # fara CRC32/suma de control la coada
        if capat > n - 4:
            stare['sectiuni_rele'] += 1
            continue
        o = 12
        if s[5] & 2:                                     # LLC/SNAP
            if s[12:20] != _LLC_IPV4:
                stare['udp_altele'] += 1
                continue
            o = 20
        if capat - o < 28:
            stare['udp_altele'] += 1
            continue
        # antetul IPv4 fara optiuni si cel UDP dintr-o singura citire (capat - o >= 28, deci octetii exista)
        verihl, frag, proto, dst, pd, ulen = un_ipv4(s, o)
        if verihl != 0x45:
            ihl = (verihl & 0x0F) * 4
            if verihl >> 4 != 4 or ihl < 20:
                stare['udp_altele'] += 1
                continue
        else:
            ihl = 20
        if proto != 17 or (frag & 0x3FFF) or (dest is not None and dst != dest):
            stare['udp_altele'] += 1
            continue
        u = o + ihl
        if ihl != 20:
            if u + 8 > capat:
                stare['sectiuni_rele'] += 1
                continue
            pd, ulen = un_udp(s, u)
        if port and pd != port:
            stare['udp_altele'] += 1
            continue
        if ulen < 8 or u + ulen > capat:
            # 10E 11220,9 V (Salisbury): encapsulatorul scrie section_length cu 2 octeti mai mic, deci datagrama
            # intra peste locul CRC-ului. Datagrama intreaga e totusi in sectiune; EDI isi verifica singur CRC-urile.
            if ulen >= 8 and u + ulen <= n:
                stare['udp_sectiune_scurta'] = stare.get('udp_sectiune_scurta', 0) + 1
            else:
                stare['sectiuni_rele'] += 1
                continue
        stare['udp'] += 1
        yield s[u + 8:u + ulen]


# ---------------------------------------------------------------- TS
_SYNC = {}


def _sincron(k):
    s = _SYNC.get(k)
    if s is None:
        s = _SYNC[k] = b'\x47' * k
    return s


def aliniaza_188(blocuri, stare):
    """Blocuri oarecare -> blocuri de pachete de 188 intregi, cu 0x47 la fiecare 188. Verificarea sincronului se
    face cu o felie din 188 in 188 (in C), nu pachet cu pachet."""
    rest = b''
    for b in blocuri:
        if rest:
            b = rest + b
            rest = b''
        n = len(b)
        o = 0
        while True:
            if n - o < 188:
                rest = b[o:]
                break
            if b[o] != 0x47 or (n - o >= 376 and b[o + 188] != 0x47):
                i = _gaseste_sincron(b, o + 1)
                stare['resincronizari'] += 1
                if i < 0:
                    rest = b[max(o, n - 375):]
                    break
                o = i
                continue
            k = (n - o) // 188
            bloc = b[o:o + k * 188] if (o or k * 188 != n) else b
            felii = bloc[::188]
            if felii != _sincron(k):
                j = _prima_diferenta(felii)
                if j > 0:
                    stare['pachete_ts'] += j
                    yield bloc[:j * 188]
                o += j * 188 + 1
                i = _gaseste_sincron(b, o)
                stare['resincronizari'] += 1
                if i < 0:
                    rest = b[max(o, n - 375):]
                    break
                o = i
                continue
            stare['pachete_ts'] += k
            yield bloc
            o += k * 188


def _prima_diferenta(felii):
    for j, x in enumerate(felii):
        if x != 0x47:
            return j
    return len(felii)


def _gaseste_sincron(b, de_la):
    n = len(b)
    i = b.find(b'\x47', de_la)
    while 0 <= i:
        if i + 376 < n:
            if b[i + 188] == 0x47 and b[i + 376] == 0x47:
                return i
        elif i + 188 < n:
            if b[i + 188] == 0x47:
                return i
        else:
            return i                                     # prea putin ca sa se verifice: se incearca aici
        i = b.find(b'\x47', i + 1)
    return -1


def este_ts188(b):
    n = len(b)
    return n >= 188 and n % 188 == 0 and b[::188] == _sincron(n // 188)


def ts_din_sarcini(unitati, pid, stare):
    """Unitati fara antete TS (asa cum le poate da TAP-ul) -> pachete TS pe PID, fiecare unitate cu PUSI si
    pointer_field 0, restul pachetului umplut cu 0xFF (ISO 13818-1)."""
    cc = 0
    p1 = 0x40 | ((pid >> 8) & 0x1F)
    p2 = pid & 0xFF
    for u in unitati:
        out = bytearray()
        o = 0
        n = len(u)
        prima = True
        while o < n:
            if prima:
                bucata = u[o:o + 183]
                out.extend((0x47, p1, p2, 0x10 | cc, 0))      # pe 2.7 bytes(tuplu) ar da textul tuplului
            else:
                bucata = u[o:o + 184]
                out.extend((0x47, p1 & 0x1F, p2, 0x10 | cc))
            out += bucata
            loc = (183 if prima else 184) - len(bucata)
            if loc:
                out += b'\xff' * loc
            o += len(bucata)
            cc = (cc + 1) & 0x0F
            prima = False
        if out:
            stare['pachete_ts'] += len(out) // 188
            yield bytes(out)


def _gen_ts(citiri, pid, stare, forma, impacheteaza=True):
    """Detectia formei la pornire: primele citiri spun daca vin pachete de 188 sau unitati fara antete."""
    it = iter(citiri)
    primele = []
    if forma == 'auto':
        for b in it:
            primele.append(b)
            if len(stare['marimi']) < 20:
                stare['marimi'].append(len(b))
            if len(primele) >= 4 or sum(len(x) for x in primele) >= 4 * 188:
                break
        if not primele:
            return
        lipit = _lipeste(primele)
        i = _gaseste_sincron(lipit, 0) if lipit[:1] != b'\x47' else 0
        ts = (0 <= i < 188 and len(lipit) - i >= 376 and lipit[i + 188] == 0x47 and lipit[i + 376] == 0x47)
        forma = 'ts188' if ts else 'sarcina'
    stare['forma'] = forma

    def tot():
        for b in primele:
            yield b
        for b in it:
            yield b
    if forma == 'ts188':
        blocuri = aliniaza_188(tot(), stare)
    elif impacheteaza:
        blocuri = ts_din_sarcini(tot(), pid, stare)
    else:
        blocuri = tot()                                  # unitati brute (t2mi_decap -r, eti.SarciniTS)
    try:
        for b in blocuri:
            yield b
    finally:
        blocuri.close()                                  # ca `yield from`: oprirea inchide imediat si sursa de dedesubt


def pachete_ts(pid, fel='auto', adapter=0, demux=0, ref=None, fifo=None, forma='auto', output_tap=DMX_OUT_TAP,
               oprire=None, stare=None, Dispozitiv=None, CititorFisier=None, CititorFlux=None, impacheteaza=True,
               gazda_8001='127.0.0.1', port_8001=8001, termen_8001=90.0, pauza_8001=3.0, cine='releu'):
    """Blocuri de pachete TS de 188 aliniate. Pentru 'tap' forma se detecteaza (stare['forma']).
    impacheteaza=False: in forma 'sarcina' unitatile vin brute (consumatorul stie sa le ia asa).
    'fifo' si 'http8001' dau tot transponderul/serviciul: filtrarea pe PID o face consumatorul (t2mi_decap -p).
    'http8001' se reconecteaza singur (tuner ocupat, antena in rotire, flux oprit) pana la oprire."""
    stare = stare if stare is not None else stare_noua()
    oprire = oprire if oprire is not None else _Oprire()
    if fel == 'auto':
        fel = 'tap'
    dev = None
    try:
        if fel == 'tap':
            dev = (Dispozitiv or Demux)(adapter, demux)
            stare['buffer_demux'] = dev.buffer(BUFFER_DEMUX)
            dev.filtru_pes(pid, output_tap)
            gen = _gen_ts(_citiri(dev, oprire, stare), pid, stare, forma, impacheteaza)
        elif fel == 'dvr':
            dev = (Dispozitiv or Demux)(adapter, demux)
            stare['buffer_demux'] = dev.buffer(BUFFER_DEMUX)
            dev.filtru_pes(pid, DMX_OUT_TS_TAP)
            try:
                dvr = (CititorFisier or CititorFd)('/dev/dvb/adapter%d/dvr%d' % (adapter, demux))
            except Exception:
                dev.inchide()
                raise
            gen = _gen_dvr(dev, dvr, oprire, stare)
        elif fel == 'http8001':
            if not ref:
                raise ValueError('http8001 cere ref (referinta serviciului)')
            gen = _gen_ts(_gen_http(ref, oprire, stare, gazda_8001, port_8001, termen_8001, pauza_8001, CititorFlux, cine),
                          pid, stare, 'ts188')
        elif fel == 'fifo':
            if not fifo:
                raise ValueError('fifo cere calea')
            dev = (CititorFisier or CititorFd)(fifo)
            gen = _gen_ts(_citiri(dev, oprire, stare), pid, stare, 'ts188')
        else:
            raise ValueError('fel necunoscut: %r' % (fel,))
    except Exception:
        if dev is not None:
            dev.inchide()
        raise
    stare['sursa'] = 'ts-%s pid 0x%04X' % (fel, pid)
    return _Sursa(gen, stare, oprire, dev)


def _gen_dvr(demux, dvr, oprire, stare):
    blocuri = aliniaza_188(_citiri(dvr, oprire, stare), stare)
    try:
        for b in blocuri:
            yield b
    finally:
        blocuri.close()                                  # intai dvr (ca la `yield from`), apoi demux
        stare['forma'] = stare['forma'] or 'ts188'
        demux.inchide()


# ---------------------------------------------------------------- Python 2.7
if sys.version_info[0] < 3:
    # Pe 2.7 os.read si recv dau str, iar str[i] e un sir de 1 caracter: `b[o] != 0x47` ar fi mereu adevarat, fara
    # nicio eroare. Citirile se fac bytearray o singura data, la iesirea din dispozitiv (o copie pe citire, nu pe
    # octet); functiile care pot primi date si din alta parte le primesc la fel. Pe Python 3 nimic de aici nu exista.
    def _ca_bytearray(blocuri):
        for b in blocuri:
            yield b if type(b) is bytearray else bytearray(b)

    _citiri_3, _udp_din_mpe_3, _aliniaza_188_3, _imparte_sectiuni_3 = _citiri, udp_din_mpe, aliniaza_188, imparte_sectiuni

    def _citiri(dev, oprire, stare, timeout=0.5, marime=CITIRE):
        return _ca_bytearray(_citiri_3(dev, oprire, stare, timeout, marime))

    def udp_din_mpe(sectiuni_iter, ip, port, stare=None):
        return _udp_din_mpe_3(_ca_bytearray(sectiuni_iter), ip, port, stare)

    def aliniaza_188(blocuri, stare):
        return _aliniaza_188_3(_ca_bytearray(blocuri), stare)

    def imparte_sectiuni(bloc, stare):
        return _imparte_sectiuni_3(bloc if type(bloc) is bytearray else bytearray(bloc), stare)
