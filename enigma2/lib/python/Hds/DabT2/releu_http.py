# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Nucleul HTTP comun al releelor (releu_dab.py pe 8898, releu_t2.py pe 8889). Facut de hdsatelit.com.
Ruleaza DOAR in procesul separat al releului.

Un singur fir pentru toti clientii (selectors, socluri neblocante) si un fir de date al aplicatiei care
publica bucati cu publica(cheie, date). Nu exista fir per client. Fiecare client are o coada de iesire cu
marime fixa: cine nu citeste destul de repede e deconectat (nu se aduna memorie). Coada dintre firul de date
si bucla are si ea o limita in octeti: peste ea bucatile se arunca si se numara.

Aplicatia da:
  handler(server, client, cale) -> Raspuns | Flux | Asteapta
  la_tic(acum)                  -> chemat din bucla de cel putin 4 ori pe secunda (porniri/opriri de surse)
Merge pe Python 3 si pe Python 2.7 (acolo selectors lipseste: acelasi contract, pe poll sau select, mai jos).
"""
from __future__ import division

import collections
import json
import os
import socket
import sys
import threading
import time

if sys.version_info[0] < 3:                           # Python 2.7: aceleasi nume ca pe Python 3, din compat.py
    try:
        from compat import (monoton as _monoton, primeste as _primeste, trimite as _trimite, accepta as _accepta,
                            pereche_socluri as _pereche, BlockingIOError, InterruptedError)
    except ImportError:
        from .compat import (monoton as _monoton, primeste as _primeste, trimite as _trimite, accepta as _accepta,
                             pereche_socluri as _pereche, BlockingIOError, InterruptedError)
    OSError = EnvironmentError                        # noqa: A001  (pe 2.7 IOError si socket.error nu sunt OSError)
    _PY2 = True
else:
    _monoton = time.monotonic
    _primeste = socket.socket.recv
    _trimite = socket.socket.send
    _accepta = socket.socket.accept
    _pereche = socket.socketpair
    _PY2 = False

try:
    import selectors
except ImportError:                                   # Python 2.7: doar ce foloseste Server, pe poll (Linux) sau select
    import errno
    import math
    import select as _select

    class _Cheie(object):
        __slots__ = ('fileobj', 'fd', 'events', 'data')

        def __init__(self, fileobj, fd, events, data):
            self.fileobj, self.fd, self.events, self.data = fileobj, fd, events, data

    class _Selector(object):
        """register, unregister, modify, select, close: la fel ca selectors.DefaultSelector."""

        def __init__(self):
            self._chei = {}
            self._poll = _select.poll() if hasattr(_select, 'poll') else None

        def _gaseste(self, f):
            try:
                fd = f if isinstance(f, int) else f.fileno()
                if fd in self._chei:
                    return fd
            except (EnvironmentError, ValueError):
                pass
            for fd, k in self._chei.items():               # soclul poate fi inchis deja: se cauta dupa obiect
                if k.fileobj is f:
                    return fd
            raise KeyError(f)

        @staticmethod
        def _masca(ev):
            return (_select.POLLIN if ev & 1 else 0) | (_select.POLLOUT if ev & 2 else 0)

        def register(self, f, ev, data=None):
            fd = f if isinstance(f, int) else f.fileno()
            if fd in self._chei:
                raise KeyError('deja inregistrat: %r' % (f,))
            k = self._chei[fd] = _Cheie(f, fd, ev, data)
            if self._poll is not None:
                self._poll.register(fd, self._masca(ev))
            return k

        def unregister(self, f):
            fd = self._gaseste(f)
            k = self._chei.pop(fd)
            if self._poll is not None:
                try:
                    self._poll.unregister(fd)
                except (KeyError, EnvironmentError, ValueError):
                    pass
            return k

        def modify(self, f, ev, data=None):
            fd = self._gaseste(f)
            k = self._chei[fd]
            k.events, k.data = ev, data
            if self._poll is not None:
                self._poll.modify(fd, self._masca(ev))
            return k

        def select(self, timeout=None):
            rez = []
            try:
                if self._poll is not None:
                    ms = None if timeout is None else max(0, int(math.ceil(timeout * 1000)))
                    for fd, m in self._poll.poll(ms):
                        k = self._chei.get(fd)
                        # ca in selectors: HUP/ERR trezesc si citirea si scrierea
                        ev = ((1 if m & ~_select.POLLOUT else 0) | (2 if m & ~_select.POLLIN else 0)) & (k.events if k else 0)
                        if ev:
                            rez.append((k, ev))
                    return rez
                r = [fd for fd, k in self._chei.items() if k.events & 1]
                w = [fd for fd, k in self._chei.items() if k.events & 2]
                if not r and not w:
                    if timeout:
                        time.sleep(timeout)
                    return rez
                rr, ww, xx = _select.select(r, w, w, timeout)
            except (_select.error, EnvironmentError) as e:
                if (e.args[0] if e.args else None) == errno.EINTR:
                    return rez
                raise
            rr, ww = set(rr), set(ww) | set(xx)
            for fd in rr | ww:
                k = self._chei.get(fd)
                ev = ((1 if fd in rr else 0) | (2 if fd in ww else 0)) & (k.events if k else 0)
                if ev:
                    rez.append((k, ev))
            return rez

        def close(self):
            self._chei.clear()
            self._poll = None

    class selectors(object):                          # noqa: N801  (acelasi nume ca modulul de pe Python 3)
        EVENT_READ = 1
        EVENT_WRITE = 2
        DefaultSelector = _Selector

CERERE_MAX = 8192
TERMEN_CERERE_S = 5.0
PAS_S = 0.25


class Raspuns(object):
    __slots__ = ('cod', 'tip', 'corp')

    def __init__(self, cod, corp=b'', tip='text/plain; charset=utf-8'):
        self.cod = cod
        self.tip = tip
        if _PY2 and not isinstance(corp, bytes):
            corp = corp if isinstance(corp, unicode) else unicode(corp)     # noqa: F821
        self.corp = corp if isinstance(corp, bytes) else str(corp).encode('utf-8') if not _PY2 else corp.encode('utf-8')


def json_raspuns(obiect, cod=200):
    if _PY2:
        # pe 2.7 json cu ensure_ascii=False amesteca str si unicode (UnicodeDecodeError la primul nume cu diacritice);
        # cu \\u JSON-ul e acelasi pentru orice client
        return Raspuns(cod, json.dumps(obiect, separators=(',', ':')), 'application/json; charset=utf-8')
    return Raspuns(cod, json.dumps(obiect, ensure_ascii=False, separators=(',', ':')).encode('utf-8'),
                   'application/json; charset=utf-8')


class Flux(object):
    """Raspuns fara lungime: antet apoi tot ce se publica pe cheie, pana pleaca clientul."""
    __slots__ = ('cheie', 'tip', 'cap')

    def __init__(self, cheie, tip, cap=512 * 1024):
        self.cheie = cheie
        self.tip = tip
        self.cap = cap


class Asteapta(object):
    """Raspuns amanat: fn(expirat) -> Raspuns | Flux | None, verificat la fiecare tic si la trezire.
    chei = sursele de care are nevoie cat asteapta (aplicatia le porneste)."""
    __slots__ = ('fn', 'termen', 'chei')

    def __init__(self, fn, secunde, chei=()):
        self.fn = fn
        self.termen = _monoton() + secunde
        self.chei = tuple(chei)


_MOTIVE = {200: 'OK', 400: 'Bad Request', 404: 'Not Found', 405: 'Method Not Allowed', 500: 'Internal Server Error',
           501: 'Not Implemented', 503: 'Service Unavailable', 504: 'Gateway Timeout'}


class Client(object):
    __slots__ = ('sock', 'intrare', 'iesire', 'stare', 'termen', 'cheie', 'cap', 'asteptare', 'scriere', 'nr', 'tinut',
                 'cereri')

    def __init__(self, sock, nr):
        self.sock = sock
        self.intrare = bytearray()
        self.iesire = bytearray()
        self.stare = 'cerere'          # cerere | asteapta | flux | final | tinut (raspuns trimis, conexiunea ramane)
        self.termen = _monoton() + TERMEN_CERERE_S
        self.cheie = None
        self.cap = 0
        self.asteptare = None
        self.scriere = False
        self.nr = nr
        self.tinut = False             # clientul a cerut conexiune tinuta (HTTP/1.1 fara close, sau keep-alive)
        self.cereri = 0


TERMEN_TINUT_S = 30.0                  # o conexiune tinuta fara cerere noua se inchide dupa atat
CERERI_TINUT_MAX = 1000                # dupa atatea cereri pe aceeasi conexiune se inchide (clientul redeschide)


_WIN_MEM = []


def _win_mem():
    """Tipul si functia pentru Windows, facute o singura data (ctypes tine minte tipurile pentru totdeauna)."""
    if not _WIN_MEM:
        import ctypes
        from ctypes import wintypes

        class PMC(ctypes.Structure):
            _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD),
                        ('PeakWorkingSetSize', ctypes.c_size_t), ('WorkingSetSize', ctypes.c_size_t),
                        ('QuotaPeakPagedPoolUsage', ctypes.c_size_t), ('QuotaPagedPoolUsage', ctypes.c_size_t),
                        ('QuotaPeakNonPagedPoolUsage', ctypes.c_size_t), ('QuotaNonPagedPoolUsage', ctypes.c_size_t),
                        ('PagefileUsage', ctypes.c_size_t), ('PeakPagefileUsage', ctypes.c_size_t)]
        k = ctypes.WinDLL('kernel32')
        k.GetCurrentProcess.restype = wintypes.HANDLE
        k.K32GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
        k.K32GetProcessMemoryInfo.restype = wintypes.BOOL
        _WIN_MEM.extend((PMC, k, ctypes))
    return _WIN_MEM


def rss_kb():
    """Memoria rezidenta a procesului, in KB (Linux din /proc/self/statm, Windows prin kernel32)."""
    try:
        with open('/proc/self/statm', 'rb') as f:
            return int(f.read().split()[1]) * (os.sysconf('SC_PAGE_SIZE') // 1024)
    except (OSError, ValueError, AttributeError, IndexError):
        pass
    if sys.platform == 'win32':
        try:
            PMC, k, ctypes = _win_mem()
            pmc = PMC()
            pmc.cb = ctypes.sizeof(PMC)
            if not k.K32GetProcessMemoryInfo(k.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb):
                return -1
            return pmc.WorkingSetSize // 1024
        except Exception:
            return -1
    return -1


class Server(object):
    def __init__(self, handler, la_tic=None, port=8898, gazda='127.0.0.1', max_clienti=32, coada_max=8 * 1024 * 1024,
                 jurnal=None, porturi_extra=()):
        """porturi_extra: alte porturi pe care se asculta cu acelasi handler (de ex. portul de control al releului T2
        cand fluxurile le serveste binarul). self.porturi_extra = porturile obtinute (0 = ales de sistem)."""
        self.handler = handler
        self.la_tic = la_tic
        self.max_clienti = max_clienti
        self.coada_max = coada_max
        self.jurnal = jurnal or (lambda text: None)
        self.sel = selectors.DefaultSelector()
        self.asc = None
        self.ascultatori = []
        self.porturi_extra = []
        for i, p in enumerate([port] + [x for x in porturi_extra if x is not None]):
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                if sys.platform != 'win32':
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind((gazda, p))
                s.listen(64)             # 20+ clienti deodata: pe Windows o coada plina amana conectarea cu secunde
                s.setblocking(False)
            except Exception:
                s.close()
                for x in self.ascultatori:
                    x.close()
                raise
            self.ascultatori.append(s)
            if i == 0:
                self.asc = s
                self.port = s.getsockname()[1]
            else:
                self.porturi_extra.append(s.getsockname()[1])
            self.sel.register(s, selectors.EVENT_READ, ('asculta', s))
        self._trezire_r, self._trezire_w = _pereche()
        self._trezire_r.setblocking(False)
        self._trezire_w.setblocking(False)
        self.sel.register(self._trezire_r, selectors.EVENT_READ, 'trezire')
        self._trezit = False
        self._coada = collections.deque()      # (cheie, date) de la firul de date
        self._coada_octeti = 0
        self._lacat = threading.Lock()
        self.clienti = {}                      # sock -> Client
        self.abonati = {}                      # cheie -> set(Client)
        self.gata = False
        self.cod_iesire = 0
        self.nr = 0
        self.contoare = {'conexiuni': 0, 'respinse_plin': 0, 'lenti_aruncati': 0, 'coada_aruncate': 0,
                         'cereri_rele': 0, 'exceptii_handler': 0, 'octeti_trimisi': 0, 'cereri': 0, 'cereri_tinute': 0,
                         'fluxuri': 0}
        self.cereri_pe_cale = {}               # prima parte a caii -> numar (diagnostic: cine cere des)

    # ------------------------------------------------------------ din firul de date
    def publica(self, cheie, date):
        """Poate fi chemat din orice fir. Nu blocheaza."""
        n = len(date)
        with self._lacat:
            if self._coada_octeti + n > self.coada_max:
                self.contoare['coada_aruncate'] += 1
                return False
            self._coada_octeti += n
            self._coada.append((cheie, date))
        self.trezeste()
        return True

    def trezeste(self):
        if not self._trezit:
            self._trezit = True
            try:
                _trimite(self._trezire_w, b'x')
            except (BlockingIOError, OSError):
                pass

    # ------------------------------------------------------------ interogari
    def chei_necesare(self):
        """cheie -> numar de clienti care o folosesc (fluxuri + asteptari)."""
        rez = {}
        for cheie, s in self.abonati.items():
            if s:
                rez[cheie] = len(s)
        for c in self.clienti.values():
            if c.stare == 'asteapta' and c.asteptare is not None:
                for k in c.asteptare.chei:
                    rez[k] = rez.get(k, 0) + 1
        return rez

    def are_abonati(self, cheie):
        return bool(self.abonati.get(cheie))

    # ------------------------------------------------------------ bucla
    def ruleaza(self):
        urmator_tic = 0.0
        while not self.gata:
            try:
                evenimente = self.sel.select(PAS_S)
            except (OSError, ValueError) as e:
                self.jurnal('select: %s' % e)
                evenimente = []
            for cheie_sel, masca in evenimente:
                d = cheie_sel.data
                if isinstance(d, tuple):
                    self._accepta(d[1])
                elif d == 'trezire':
                    self._goleste_trezirea()
                else:
                    if masca & selectors.EVENT_READ:
                        self._citeste(d)
                    if masca & selectors.EVENT_WRITE and d.sock in self.clienti:
                        self._scrie(d)
            self._goleste_coada()
            acum = _monoton()
            if evenimente or acum >= urmator_tic:
                self._verifica_asteptari(acum)
            if acum >= urmator_tic:
                urmator_tic = acum + PAS_S
                self._termene(acum)
                if self.la_tic is not None:
                    try:
                        self.la_tic(acum)
                    except Exception as e:
                        self.jurnal('la_tic: %r' % (e,))
        self.inchide()
        return self.cod_iesire

    def opreste(self, cod=0):
        self.cod_iesire = cod
        self.gata = True
        self.trezeste()

    def inchide(self):
        for c in list(self.clienti.values()):
            self._arunca(c)
        for s in tuple(self.ascultatori) + (self._trezire_r, self._trezire_w):
            try:
                self.sel.unregister(s)
            except (KeyError, ValueError, OSError):
                pass
            try:
                s.close()
            except OSError:
                pass
        try:
            self.sel.close()
        except OSError:
            pass

    # ------------------------------------------------------------ interne
    def _goleste_trezirea(self):
        self._trezit = False
        try:
            while _primeste(self._trezire_r, 4096):
                pass
        except (BlockingIOError, OSError):
            pass

    def _accepta(self, asc=None):
        asc = asc if asc is not None else self.asc
        for _ in range(64):
            try:
                s, _ = _accepta(asc)
            except (BlockingIOError, InterruptedError):
                return
            except OSError as e:
                self.jurnal('accept: %s' % e)
                return
            if len(self.clienti) >= self.max_clienti:
                self.contoare['respinse_plin'] += 1
                try:
                    s.send(b'HTTP/1.0 503 Service Unavailable\r\nConnection: close\r\n\r\n')
                except OSError:
                    pass
                s.close()
                continue
            s.setblocking(False)
            try:
                s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            except OSError:
                pass
            self.nr += 1
            c = Client(s, self.nr)
            self.clienti[s] = c
            self.contoare['conexiuni'] += 1
            self.sel.register(s, selectors.EVENT_READ, c)

    def _citeste(self, c):
        try:
            b = _primeste(c.sock, 4096)
        except (BlockingIOError, InterruptedError):
            return
        except OSError:
            self._arunca(c)
            return
        if not b:
            self._arunca(c)
            return
        if c.stare in ('tinut', 'asteapta') and c.tinut:
            # conexiune tinuta: urmatoarea cerere poate veni inainte sa plece raspunsul; se pastreaza (cu limita)
            if len(c.intrare) + len(b) <= CERERE_MAX:
                c.intrare += b
            return
        if c.stare != 'cerere':
            return                                          # dupa cerere nu ne mai intereseaza ce trimite
        c.intrare += b
        self._citeste_din_intrare(c)

    def _citeste_din_intrare(self, c):
        i = c.intrare.find(b'\r\n\r\n')
        if i < 0:
            if len(c.intrare) > CERERE_MAX:
                self.contoare['cereri_rele'] += 1
                self._raspunde(c, Raspuns(400, 'cerere prea mare'))
            return
        antet = bytes(c.intrare[:i]).decode('latin-1', 'replace')
        # ce vine dupa antet (o cerere urmatoare trimisa deodata) ramane pentru pasul urmator
        rest = c.intrare[i + 4:]
        c.intrare = bytearray()
        randuri = antet.split('\r\n')
        linie = randuri[0].split()
        if len(linie) < 2:
            self.contoare['cereri_rele'] += 1
            c.tinut = False
            self._raspunde(c, Raspuns(400, 'cerere rea'))
            return
        c.tinut = _vrea_tinut(linie, randuri[1:]) and c.cereri < CERERI_TINUT_MAX
        c.cereri += 1
        self.contoare['cereri'] += 1
        if c.cereri > 1:
            self.contoare['cereri_tinute'] += 1
        if linie[0] not in ('GET', 'HEAD'):
            self._raspunde(c, Raspuns(405, 'doar GET'))
            return
        cale = linie[1].split('?', 1)[0]
        prima = cale.strip('/').split('/', 1)[0][:16]
        if prima in self.cereri_pe_cale or len(self.cereri_pe_cale) < 16:
            self.cereri_pe_cale[prima] = self.cereri_pe_cale.get(prima, 0) + 1
        if rest and c.tinut:
            c.intrare = bytearray(rest[:CERERE_MAX])
        try:
            r = self.handler(self, c, cale)
        except Exception as e:
            self.contoare['exceptii_handler'] += 1
            self.jurnal('handler %s: %r' % (cale, e))
            r = Raspuns(500, 'eroare interna')
        self._aplica(c, r)

    def _aplica(self, c, r):
        if r is None:
            return
        if isinstance(r, Asteapta):
            c.stare = 'asteapta'
            c.asteptare = r
            return
        c.asteptare = None
        if isinstance(r, Flux):
            c.stare = 'flux'
            c.tinut = False
            c.cheie = r.cheie
            c.cap = r.cap
            self.contoare['fluxuri'] += 1
            self.abonati.setdefault(r.cheie, set()).add(c)
            antet = ('HTTP/1.0 200 OK\r\nContent-Type: %s\r\nCache-Control: no-cache\r\nConnection: close\r\n\r\n'
                     % r.tip).encode('ascii')
            self._pune(c, antet)
            return
        self._raspunde(c, r)

    def _raspunde(self, c, r):
        if c.tinut:
            antet = ('HTTP/1.1 %d %s\r\nContent-Type: %s\r\nContent-Length: %d\r\nCache-Control: no-cache\r\n'
                     'Connection: keep-alive\r\n\r\n' % (r.cod, _MOTIVE.get(r.cod, 'OK'), r.tip, len(r.corp))
                     ).encode('ascii')
            c.stare = 'tinut'
        else:
            antet = ('HTTP/1.0 %d %s\r\nContent-Type: %s\r\nContent-Length: %d\r\nCache-Control: no-cache\r\n'
                     'Connection: close\r\n\r\n' % (r.cod, _MOTIVE.get(r.cod, 'OK'), r.tip, len(r.corp))).encode('ascii')
            c.stare = 'final'
        self._pune(c, antet + r.corp)

    def _pune(self, c, date):
        if c.cap and len(c.iesire) + len(date) > c.cap:
            self.contoare['lenti_aruncati'] += 1
            self._arunca(c)
            return
        c.iesire += date
        self._scrie(c)

    def _scrie(self, c):
        if c.iesire:
            try:
                n = _trimite(c.sock, c.iesire)
            except (BlockingIOError, InterruptedError):
                n = 0
            except OSError:
                self._arunca(c)
                return
            if n:
                del c.iesire[:n]
                self.contoare['octeti_trimisi'] += n
        if c.iesire:
            if not c.scriere:
                c.scriere = True
                self.sel.modify(c.sock, selectors.EVENT_READ | selectors.EVENT_WRITE, c)
        else:
            if c.scriere:
                c.scriere = False
                self.sel.modify(c.sock, selectors.EVENT_READ, c)
            if c.stare == 'final':
                self._arunca(c)
            elif c.stare == 'tinut' and c.sock in self.clienti:
                # raspunsul a plecat: conexiunea asteapta urmatoarea cerere (cel mult TERMEN_TINUT_S)
                c.stare = 'cerere'
                c.asteptare = None
                c.termen = _monoton() + TERMEN_TINUT_S
                if c.intrare and b'\r\n\r\n' in c.intrare:
                    self._citeste_din_intrare(c)

    def _goleste_coada(self):
        if not self._coada:
            return
        with self._lacat:
            bucati = self._coada
            self._coada = collections.deque()
            self._coada_octeti = 0
        abonati = self.abonati
        for cheie, date in bucati:
            s = abonati.get(cheie)
            if not s:
                continue
            for c in tuple(s):
                self._pune(c, date)

    def _verifica_asteptari(self, acum):
        for c in [x for x in self.clienti.values() if x.stare == 'asteapta']:
            a = c.asteptare
            try:
                r = a.fn(acum >= a.termen)
            except Exception as e:
                self.contoare['exceptii_handler'] += 1
                self.jurnal('asteptare: %r' % (e,))
                r = Raspuns(500, 'eroare interna')
            if r is None and acum >= a.termen:
                r = Raspuns(504, 'fara date')
            if r is not None and c.sock in self.clienti:
                self._aplica(c, r)

    def _termene(self, acum):
        for c in [x for x in self.clienti.values() if x.stare == 'cerere' and acum > x.termen]:
            self._arunca(c)

    def _arunca(self, c):
        if self.clienti.pop(c.sock, None) is None:
            return
        if c.cheie is not None:
            s = self.abonati.get(c.cheie)
            if s is not None:
                s.discard(c)
                if not s:
                    del self.abonati[c.cheie]
        try:
            self.sel.unregister(c.sock)
        except (KeyError, ValueError, OSError):
            pass
        try:
            c.sock.close()
        except OSError:
            pass
        c.iesire = bytearray()
        c.asteptare = None


def _vrea_tinut(linie, randuri_antet):
    """HTTP/1.1 tine conexiunea daca nu se cere close; HTTP/1.0 doar cu Connection: keep-alive."""
    conexiune = ''
    for r in randuri_antet:
        k, _, v = r.partition(':')
        if k.strip().lower() == 'connection':
            conexiune = v.strip().lower()
    if 'close' in conexiune:
        return False
    if len(linie) >= 3 and linie[2].upper() == 'HTTP/1.1':
        return True
    return 'keep-alive' in conexiune


class Argumente(object):
    pass


def muta_erorile():
    """Pornit din enigma2 cu eConsoleAppContainer: tevile stdout/stderr ale containerului TREBUIE sa ramana deschise.
    Daca ieșirea standard se inchide (de ex. `>/dev/null` in comanda), enigma2 vede sfarsitul fluxului, crede ca
    procesul s-a terminat si face waitpid BLOCANT in firul principal: interfata ingheata cat traieste releul
    (dovedit pe Viper 4K V20). De aceea comanda nu are redirectari, iar aici mutam doar obiectele Python
    sys.stdout/sys.stderr (descriptorii 1 si 2 raman legati la tevi, nescrisi). Calea vine din HDS_ERORI."""
    cale = os.environ.get('HDS_ERORI')
    if not cale:
        return
    try:
        sys.stdout = open(os.devnull, 'w')
    except (IOError, OSError):
        pass
    try:
        sys.stderr = open(cale, 'w')
    except (IOError, OSError):
        try:
            sys.stderr = open(os.devnull, 'w')
        except (IOError, OSError):
            pass


def citeste_argumente(argv, optiuni, steaguri=(), pozitionale=('feed',), descriere=''):
    """Linia de comanda fara argparse (argparse aduce re si gettext: memorie in plus pe receptor).
    optiuni: {'--nume': (tip, implicit)}; steaguri: ('--nume', ...). Numele devin atribute cu _ in loc de -."""
    a = Argumente()
    for k, (_, v) in optiuni.items():
        setattr(a, k[2:].replace('-', '_'), v)
    for k in steaguri:
        setattr(a, k[2:].replace('-', '_'), False)
    poz = []
    i = 0
    while i < len(argv):
        x = argv[i]
        if x in ('-h', '--help'):
            sys.stdout.write('%s\n  argumente: %s\n  optiuni: %s %s\n' % (
                descriere, ' '.join(pozitionale), ' '.join('%s N' % k for k in optiuni), ' '.join(steaguri)))
            raise SystemExit(0)
        if x in steaguri:
            setattr(a, x[2:].replace('-', '_'), True)
        elif x.split('=', 1)[0] in optiuni:
            nume, _, val = x.partition('=')
            if not _:
                i += 1
                if i >= len(argv):
                    raise SystemExit('lipseste valoarea pentru %s' % nume)
                val = argv[i]
            tip = optiuni[nume][0]
            try:
                setattr(a, nume[2:].replace('-', '_'), tip(val))
            except ValueError:
                raise SystemExit('valoare gresita pentru %s: %s' % (nume, val))
        elif x.startswith('--'):
            raise SystemExit('optiune necunoscuta: %s' % x)
        else:
            poz.append(x)
        i += 1
    if len(poz) != len(pozitionale):
        raise SystemExit('se asteapta: %s' % ' '.join(pozitionale))
    for k, v in zip(pozitionale, poz):
        setattr(a, k, v)
    return a


def ciclu_viata(server, chei_active, porneste, opreste, inactiv_s, iesi_fara_clienti, stare):
    """Porneste ce se cere, opreste ce nu mai are clienti de inactiv_s secunde, iese cand nu mai e nimic.
    chei_active: set cu cheile pornite (modificat aici). stare: dict cu 'ultim' {cheie: moment} si
    'folosit' (ultimul moment cu vreun client; la pornire = momentul pornirii)."""
    acum = _monoton()
    necesare = server.chei_necesare()
    ultim = stare.setdefault('ultim', {})
    stare.setdefault('folosit', acum)
    if necesare:
        stare['folosit'] = acum
    for k in necesare:
        ultim[k] = acum
        if k not in chei_active:
            porneste(k)
            chei_active.add(k)
    for k in list(chei_active):
        if k not in necesare and acum - ultim.get(k, acum) >= inactiv_s:
            opreste(k)
            chei_active.discard(k)
            ultim.pop(k, None)
    if iesi_fara_clienti and not necesare and not chei_active and acum - stare['folosit'] >= inactiv_s:
        server.opreste(0)
