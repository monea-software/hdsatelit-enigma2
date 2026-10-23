# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Serverul local de flux al imaginii, pe 127.0.0.1:8001, pentru releele DAB+ si DVB-T2. Facut de hdsatelit.com.

Releele (t2/motor/releu_t2.py cu binarul t2mi_decap, dab/motor/releu_dab.py prin surse.CititorHttp) cer fluxul
serviciului purtator la http://127.0.0.1:8001/<referinta>, ca la streamserverul altor imagini. Baza imaginii nu are
streamserver; acest modul il inlocuieste, numai pe 127.0.0.1 (nimic deschis in retea), numai in imagine (pornit din
imagine.porneste; pluginul pentru alte imagini nu il foloseste):
  - GET /1:0:<tip>:<sid>:<tsid>:<onid>:<ns>:0:0:0: -> „HTTP/1.0 200 OK", apoi TS-ul serviciului, cat sta clientul;
  - tunerul il ia o inregistrare enigma2 facuta direct cu eServiceCenter.record (alocarea obisnuita a canalului, cu
    rotirea antenei; aceeasi citire a demux-ului ca la inregistrarile obisnuite, lib/dvb/demux.cpp eDVBTSRecorder),
    nu prin Navigation: nu apare in lista inregistrarilor, nu cheama extensiile de inregistrare;
  - inregistrarea scrie intr-o teava a procesului enigma2 (calea /proc/self/fd/N a capatului de scriere), nu intr-un
    fisier: nimic in /tmp. doRecord sterge intai calea (pe /proc nu se poate, deci nu se intampla nimic) si o
    deschide pentru scriere (se deschide teava). Fisierele de langa inregistrare (.meta, .sc, .ap, .cuts) nu se pot
    face langa o cale din /proc: enigma2 le sare (prepare intoarce -255 numai pentru .meta, inregistrarea merge);
  - un fir pe sesiune muta datele din teava in soclu; firul principal porneste si opreste inregistrarea (enigma2 se
    atinge numai din bucla principala; trezirea vine printr-o teava de trezire cu eSocketNotifier, nu prin twisted);
  - serviciul nu porneste (tuner ocupat, acord cazut, referinta necunoscuta): „HTTP/1.0 400 Bad Request" in corp,
    dupa antetul 200, apoi inchidere (asa asteapta surse.CititorHttp si t2mi_decap; TunerOcupat, reincercare).
Cel mult SESIUNI_MAX sesiuni deodata; numai referinte DVB de serviciu (fara cai de fisier, fara alte cereri).
"""
import collections
import errno
import os
import re
import select
import socket
import threading
import time

from . import compat, jurnal

# duratele si termenele sesiunilor pe ceasul monoton; ora de perete numai la inceputul inregistrarii enigma2
_monoton = compat.monoton

ET = '8001'
GAZDA = '127.0.0.1'
PORT = 8001
SESIUNI_MAX = 2
TERMEN_CERERE_S = 5.0        # cat asteapta firul sesiunii randul GET
TERMEN_PORNIRE_S = 15.0      # cat asteapta firul sesiunii ca firul principal sa porneasca inregistrarea
TERMEN_GOLIRE_S = 5.0        # dupa plecarea clientului teava se goleste pana se opreste inregistrarea
TERMEN_TRIMITERE_S = 5      # o trimitere in soclu asteapta cel mult atat (SO_SNDTIMEO), ca firul sa nu stea agatat
TERMEN_FARA_CITIRE_S = 30.0  # un client care nu mai citeste atata timp e lasat: inregistrarea se opreste, tunerul e liber
CEAS_MS = 1000               # verificarea erorilor inregistrarilor, numai cat exista sesiuni
SECUNDE_FARA_DATE = 10       # o sesiune fara niciun octet atata timp lasa in jurnal starea acordului (o data)
F_SETPIPE_SZ = 1031          # fcntl: marimea tevii (Linux)
TEAVA_OCTETI = 1024 * 1024   # se cere; daca nucleul refuza ramane marimea implicita
BLOC = 256 * 1024
_SPLICE = getattr(os, 'splice', None)

REF_BUNA = re.compile(r'^1:0:[0-9A-Fa-f]{1,4}:[0-9A-Fa-f]{1,4}:[0-9A-Fa-f]{1,4}:[0-9A-Fa-f]{1,4}:'
                      r'[0-9A-Fa-f]{1,8}:0:0:0:$')
ANTET_200 = b'HTTP/1.0 200 OK\r\nConnection: Close\r\nContent-Type: video/mpeg\r\nServer: HDSatelit\r\n\r\n'
RASPUNS_400 = b'HTTP/1.0 400 Bad Request\r\nConnection: Close\r\n\r\n'


def ref_din_cerere(date):
    """Cererea HTTP (octeti, cel putin primul rand) -> referinta DVB, sau None: alt verb, alta cale, cale de fisier,
    caractere straine. Codarea %3A a doua puncte se primeste."""
    try:
        rand = bytes(date).split(b'\r\n', 1)[0].decode('ascii')
    except (UnicodeDecodeError, ValueError):
        return None
    parti = rand.split(' ')
    if len(parti) != 3 or parti[0] != 'GET' or not parti[2].startswith('HTTP/1.') or not parti[1].startswith('/'):
        return None
    ref = parti[1][1:].replace('%3A', ':').replace('%3a', ':')
    return ref if REF_BUNA.match(ref) else None


def cale_teava(fd):
    """Calea prin care inregistrarea deschide capatul de scriere al tevii (in acelasi proces)."""
    return '/proc/self/fd/%d' % fd


class Sesiune(object):
    """Un client. Firul sesiunii: cererea, antetul, mutarea datelor, golirea la sfarsit. Firul principal: rec, w."""

    def __init__(self, server, conn, adresa=None):
        self.server = server
        self.conn = conn
        self.adresa = adresa
        self.ref = None
        self.rec = None                      # numai firul principal
        self.r = None                        # capatul de citire: il inchide firul sesiunii
        self.w = None                        # capatul de scriere: il inchide firul principal, dupa rec.stop()
        self.pornita = threading.Event()     # firul principal a raspuns la pornire (bine sau cu eroare)
        self.oprita = threading.Event()      # firul principal a oprit inregistrarea si a inchis w
        self.eroare = None                   # text: de ce nu merge (pus de firul principal)
        self.octeti = 0
        self.inceput = _monoton()
        self.notat_fara_date = False
        self.fir = threading.Thread(target=self._lucreaza, name='hds8001')
        self.fir.daemon = True

    # ------------------------------------------------------------ firul sesiunii
    def _citeste_cererea(self):
        self.conn.settimeout(TERMEN_CERERE_S)
        date = bytearray()
        while b'\r\n\r\n' not in date and len(date) < 4096:
            b = self.conn.recv(4096)
            if not b:
                break
            date += b
        return ref_din_cerere(date)

    def _trimite(self, date):
        try:
            self.conn.sendall(date)
            return True
        except (OSError, socket.error):
            return False

    def _muta(self):
        """Din teava in soclu, cat sta clientul si cat merge inregistrarea. -> motivul opririi (text)."""
        conn, r = self.conn, self.r
        conn.setblocking(True)
        conn.settimeout(None)
        _termen_trimitere(conn, TERMEN_TRIMITERE_S)
        fd_conn = conn.fileno()
        blocat_din = None            # de cand nu mai pleaca nimic spre client (soclul plin)
        while True:
            if self.server.oprit:
                return 'serverul se opreste'
            if self.eroare and not self.octeti:
                self._trimite(RASPUNS_400)
                return self.eroare
            if self.eroare:
                return self.eroare
            try:
                gata, _, _ = select.select([r, fd_conn], [], [], 1.0)
            except (OSError, select.error) as e:
                if getattr(e, 'errno', None) == errno.EINTR:
                    continue
                return 'select: %s' % e
            if fd_conn in gata:
                try:
                    b = conn.recv(4096)
                except (OSError, socket.error):
                    b = b''
                if not b:
                    return 'clientul a inchis'
            if r in gata:
                try:
                    if _SPLICE is not None:
                        n = _SPLICE(r, fd_conn, BLOC)
                    else:
                        b = os.read(r, BLOC)
                        n = len(b)
                        if n:
                            conn.sendall(b)
                except (OSError, socket.error) as e:
                    if getattr(e, 'errno', None) == errno.EINTR:
                        continue
                    if getattr(e, 'errno', None) in (errno.EAGAIN, errno.EWOULDBLOCK) or isinstance(e, socket.timeout):
                        # soclul a stat plin TERMEN_TRIMITERE_S: clientul nu citeste; dupa TERMEN_FARA_CITIRE_S e lasat
                        blocat_din = blocat_din or _monoton()
                        if _monoton() - blocat_din >= TERMEN_FARA_CITIRE_S:
                            return 'clientul nu mai citeste de %d s' % TERMEN_FARA_CITIRE_S
                        continue
                    return 'clientul nu mai primeste (%s)' % (getattr(e, 'strerror', None) or e)
                if not n:
                    return 'inregistrarea a inchis teava'
                blocat_din = None
                self.octeti += n

    def _goleste(self):
        """Clientul a plecat: teava se citeste in gol pana opreste firul principal inregistrarea (scrierea ei nu
        ramane blocata pe o teava plina)."""
        termen = _monoton() + TERMEN_GOLIRE_S
        while not self.oprita.is_set() and _monoton() < termen:
            try:
                gata, _, _ = select.select([self.r], [], [], 0.2)
                if gata and not os.read(self.r, BLOC):
                    break
            except (OSError, select.error):
                break

    def _lucreaza(self):
        motiv = 'cerere straina'
        try:
            try:
                self.ref = self._citeste_cererea()
            except (OSError, socket.error):
                self.ref = None
            if not self.ref:
                self._trimite(RASPUNS_400)
                return
            self.server.cere('porneste', self)
            if not self.pornita.wait(TERMEN_PORNIRE_S):
                self.eroare = self.eroare or 'pornirea nu a raspuns in termen'
            if self.eroare:
                motiv = self.eroare
                self._trimite(ANTET_200 + RASPUNS_400)
                return
            if not self._trimite(ANTET_200):
                motiv = 'clientul a plecat inainte de antet'
                return
            motiv = self._muta()
        except Exception as e:
            motiv = 'eroare: %s' % e
        finally:
            if self.pornita.is_set() and not self.oprita.is_set():
                self.server.cere('opreste', self)
                if self.r is not None:
                    self._goleste()
            for f in (self.conn.close, self._inchide_r):
                try:
                    f()
                except Exception:
                    pass
            self.server.cere('gata', self, motiv)

    def _inchide_r(self):
        r, self.r = self.r, None
        if r is not None:
            os.close(r)


class Server(object):
    """Soclul de ascultare si sesiunile. Tot ce atinge enigma2 ruleaza in firul principal (porneste, _trezit, _ceas)."""

    def __init__(self, gazda=GAZDA, port=PORT, sesiuni_max=SESIUNI_MAX):
        self.gazda, self.port, self.sesiuni_max = gazda, port, sesiuni_max
        self.sock = None
        self.sesiuni = []
        self.oprit = False
        self._coada = collections.deque()
        self._lacat = threading.Lock()
        self._trezire = None                 # (r, w)
        self._notificatori = []
        self._maniere = []
        self._ceas = None
        self.pornite = 0
        self.refuzate = 0
        # pe cheia purtatorului: sesiunile refuzate la rand de la ultima pornire buna (tuner ocupat, acord cazut).
        # Controlorii DVB-T2 / DAB+ le citesc cat asteapta primele date (refuzuri), ca sa spuna pe loc de ce nu merge.
        self._refuzuri = {}

    # ------------------------------------------------------------ firul principal
    def porneste(self):
        """Leaga 127.0.0.1:8001 si pune notificatorii. -> True daca asculta. Nu arunca."""
        try:
            from enigma import eSocketNotifier, eTimer
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((self.gazda, self.port))
            s.listen(4)
            s.setblocking(False)
            r, w = os.pipe()
            for fd in (r, w):
                _neblocant(fd)
            self.sock, self._trezire = s, (r, w)
            for fd, fn in ((s.fileno(), self._accepta), (r, self._trezit)):
                n = eSocketNotifier(fd, 1)
                self._maniere.append(compat.conecteaza(n.callback, fn))
                self._notificatori.append(n)
            self._ceas = eTimer()
            self._maniere.append(compat.conecteaza_timer(self._ceas, self._verifica))
            jurnal.noteaza(ET, 'serverul local de flux asculta pe %s:%d' % (self.gazda, self.port))
            return True
        except Exception as e:
            jurnal.noteaza(ET, 'serverul local de flux nu porneste: %s' % e)
            self.opreste()
            return False

    def opreste(self):
        """La iesirea enigma2: sesiunile se opresc, soclul se inchide. Nu arunca."""
        self.oprit = True
        for ses in list(self.sesiuni):
            self._opreste_inregistrarea(ses)
        compat.deconecteaza_toate(self._maniere)
        self._notificatori = []
        if self._ceas is not None:
            try:
                self._ceas.stop()
            except Exception:
                pass
            self._ceas = None
        for obiect in (self.sock,):
            try:
                if obiect is not None:
                    obiect.close()
            except Exception:
                pass
        self.sock = None
        if self._trezire:
            for fd in self._trezire:
                try:
                    os.close(fd)
                except OSError:
                    pass
            self._trezire = None

    def _accepta(self, _ce=None):
        while self.sock is not None:
            try:
                conn, adresa = self.sock.accept()
            except (OSError, socket.error):
                return
            if adresa and adresa[0] != '127.0.0.1':
                conn.close()
                continue
            ses = Sesiune(self, conn, adresa)
            if len(self.sesiuni) >= self.sesiuni_max:
                ses.eroare = 'prea multe sesiuni (%d)' % len(self.sesiuni)
                ses.pornita.set()
                self.refuzate += 1
            self.sesiuni.append(ses)
            ses.fir.start()

    def cere(self, ce, ses, *rest):
        """Din orice fir: munca pentru firul principal ('porneste', 'opreste', 'gata'), cu trezirea buclei."""
        with self._lacat:
            self._coada.append((ce, ses, rest))
        try:
            if self._trezire:
                os.write(self._trezire[1], b'.')
        except OSError:
            pass

    def _trezit(self, _ce=None):
        try:
            while os.read(self._trezire[0], 512):
                pass
        except (OSError, TypeError):
            pass
        while True:
            with self._lacat:
                if not self._coada:
                    break
                ce, ses, rest = self._coada.popleft()
            try:
                if ce == 'porneste':
                    self._porneste_inregistrarea(ses)
                elif ce == 'opreste':
                    self._opreste_inregistrarea(ses)
                elif ce == 'gata':
                    self._opreste_inregistrarea(ses)
                    if ses in self.sesiuni:
                        self.sesiuni.remove(ses)
                    jurnal.noteaza(ET, 'sesiune incheiata %s: %s, %d octeti in %d s' % (
                        ses.ref or '-', rest[0] if rest else '-', ses.octeti, int(_monoton() - ses.inceput)))
            except Exception:
                jurnal.eroare(ET, ce)
        self._porneste_ceasul()

    def _porneste_ceasul(self):
        if self._ceas is None:
            return
        if any(s.rec is not None for s in self.sesiuni):
            self._ceas.start(CEAS_MS, True)
        else:
            self._ceas.stop()

    def _porneste_inregistrarea(self, ses):
        if ses.pornita.is_set():             # refuzata la acceptare (prea multe sesiuni)
            return
        try:
            from enigma import eServiceCenter, eServiceReference
            r, w = os.pipe()
            ses.r, ses.w = r, w
            try:
                import fcntl
                fcntl.fcntl(w, F_SETPIPE_SZ, TEAVA_OCTETI)
            except Exception:
                pass
            rec = eServiceCenter.getInstance().record(eServiceReference(ses.ref))
            if rec is None:
                ses.eroare = 'serviciul nu se poate inregistra (referinta necunoscuta)'
                return
            ses.rec = rec
            # releele cedeaza tunerul la zap (extensia de zap din pornire.py opreste sesiunile 8001 inainte de
            # alocare): marcata asa (lib/dvb/hdscedare.h), inregistrarea nu mai face gri in lista de canale
            # canalele pe care televizorul le poate porni; cu un enigma2 fara functie, nimic
            cedeaza = getattr(rec, 'setYieldsToZap', None)
            if cedeaza is not None:
                try:
                    cedeaza(True)
                except Exception:
                    jurnal.eroare(ET, 'cedarea la zap')
            # -255: numai fisierul .meta nu se poate face langa /proc/self/fd/N; inregistrarea e pregatita
            rez = rec.prepare(cale_teava(w), int(time.time()), -1, -1, 'HDSatelit 8001', '', '')
            if rez not in (0, -255):
                ses.eroare = 'acordul nu porneste (%d)' % rez
                return
            rez = rec.start()
            if rez:
                ses.eroare = 'inregistrarea nu porneste (%d)' % rez
                return
            eroare = _eroare_rec(rec)
            if eroare:
                ses.eroare = 'tunerul nu se poate folosi (%d)' % eroare
                return
            self.pornite += 1
            self._refuzuri.pop(_cheie_ref(ses.ref), None)
            jurnal.noteaza(ET, 'sesiune pornita %s' % ses.ref)
        except Exception as e:
            ses.eroare = 'eroare la pornire: %s' % e
        finally:
            if ses.eroare:
                cheie = _cheie_ref(ses.ref)
                self._refuzuri[cheie] = self._refuzuri.get(cheie, 0) + 1
                jurnal.noteaza(ET, 'sesiune refuzata %s: %s' % (ses.ref, ses.eroare))
                self._opreste_inregistrarea(ses)
            ses.pornita.set()

    def _opreste_inregistrarea(self, ses):
        rec, ses.rec = ses.rec, None
        if rec is not None:
            try:
                rec.stop()
            except Exception:
                jurnal.eroare(ET, 'oprirea inregistrarii')
        w, ses.w = ses.w, None
        if w is not None:
            try:
                os.close(w)
            except OSError:
                pass
        if not ses.pornita.is_set():
            ses.eroare = ses.eroare or 'oprit'
            ses.pornita.set()
        ses.oprita.set()
        if ses.r is not None and not ses.fir.is_alive():
            ses._inchide_r()

    def _verifica(self):
        """Ceasul (firul principal): o inregistrare cazuta (acord pierdut, tuner luat) inchide sesiunea ei."""
        for ses in list(self.sesiuni):
            if ses.rec is not None and not ses.eroare:
                eroare = _eroare_rec(ses.rec)
                if eroare:
                    ses.eroare = 'inregistrarea a cazut (%d)' % eroare
                elif not ses.octeti and not ses.notat_fara_date and _monoton() - ses.inceput > SECUNDE_FARA_DATE:
                    ses.notat_fara_date = True
                    jurnal.noteaza(ET, 'sesiune fara date dupa %d s %s: tuner %s' % (
                        SECUNDE_FARA_DATE, ses.ref, _stare_tuner(ses.rec)))
        self._porneste_ceasul()

    def deschise(self, ref=None):
        """Firul principal. Cate sesiuni inca tin sau pot lua tunerul (inregistrarea neoprita, inclusiv cele care abia
        pornesc). Cu `ref` (referinta purtatorului) numai sesiunile acelui serviciu, comparate pe cheie: fara nume, fara
        ':' la sfarsit, litere mari = mici. Dupa ce clientul pleaca, inregistrarea se opreste abia cand bucla principala
        prelucreaza trezirea; pana atunci sesiunea se numara aici."""
        cheie = _cheie_ref(ref) if ref else None
        return sum(1 for s in self.sesiuni if not s.oprita.is_set() and (cheie is None or _cheie_ref(s.ref) == cheie))

    def opreste_sesiunile(self, ref):
        """Firul principal. Opreste pe loc inregistrarile sesiunilor de pe purtatorul `ref` (aceeasi cheie ca la
        deschise): tunerul e liber cand se intoarce functia, fara sa se astepte trezirea buclei. Firul sesiunii vede
        teava inchisa si incheie sesiunea singur. -> cate sesiuni s-au oprit."""
        cheie = _cheie_ref(ref)
        if not cheie:
            return 0
        n = 0
        for ses in list(self.sesiuni):
            if not ses.oprita.is_set() and _cheie_ref(ses.ref) == cheie:
                self._opreste_inregistrarea(ses)
                n += 1
        if n:
            self._porneste_ceasul()
        return n

    def refuzuri(self, ref):
        """Firul principal. Cate sesiuni ale purtatorului `ref` au fost refuzate la rand (inregistrarea nu a pornit:
        tuner ocupat, acord cazut) de la ultima pornire buna. 0 dupa o pornire buna sau pentru un purtator necerut."""
        return self._refuzuri.get(_cheie_ref(ref), 0) if ref else 0

    def uita_refuzurile(self, ref):
        """Firul principal. Un zap nou pe purtator incepe numaratoarea de la zero."""
        if ref:
            self._refuzuri.pop(_cheie_ref(ref), None)

    def stare(self):
        return {'asculta': self.sock is not None, 'sesiuni': len(self.sesiuni), 'pornite': self.pornite,
                'refuzate': self.refuzate,
                'detalii': [{'ref': s.ref, 'octeti': s.octeti, 'secunde': int(_monoton() - s.inceput),
                             'eroare': s.eroare} for s in self.sesiuni]}


def _cheie_ref(ref):
    """Referinta DVB ca cheie de comparatie: primele 10 campuri, litere mici, fara ':' la sfarsit."""
    return ':'.join(str(ref or '').split(':')[:10]).rstrip(':').lower()


def _eroare_rec(rec):
    try:
        e = rec.getError()
    except Exception:
        return 0
    if isinstance(e, (tuple, list)):
        e = e[-1] if e else 0
    try:
        return int(e or 0)
    except (TypeError, ValueError):
        return 0


def _stare_tuner(rec):
    """Starea acordului inregistrarii, pentru jurnal: tuner_state din enigma2 (LOCKED, TUNING, FAILED...)."""
    try:
        fi = rec.frontendInfo()
        d = fi.getFrontendStatus() if fi is not None else None
        text = '%s, blocat %s' % (d.get('tuner_state'), d.get('tuner_locked')) if isinstance(d, dict) else '?'
    except Exception as e:
        text = 'necunoscut (%s)' % e
    try:
        # PID-urile pe care inregistrarea le-a cerut demux-ului si demux-ul ei (eDVBServiceRecord::getStreamingData)
        s = rec.stream()
        date = s.getStreamingData() if s is not None else None
        if isinstance(date, dict):
            text += '; program %s' % str(sorted(date.items()))[:300]
        else:
            text += '; program %r (neacordat sau fara PID-uri)' % (date,)
    except Exception as e:
        text += '; pid-uri necunoscute (%s)' % e
    return text


def _termen_trimitere(conn, secunde):
    """SO_SNDTIMEO pe soclu: o trimitere (si splice spre soclu) care nu poate pune nimic atata timp se intoarce cu
    EAGAIN in loc sa astepte la nesfarsit; soclul ramane blocant pentru restul."""
    import struct
    eroare = None
    # struct timeval: doua numere de 64 de biti (Linux pe 64 de biti si receptorul armv7, unde SO_SNDTIMEO e varianta
    # cu timp pe 64 de biti), sau doua long (sistemele pe 32 de biti cu varianta veche)
    for forma in ('qq', 'll'):
        try:
            conn.setsockopt(socket.SOL_SOCKET, socket.SO_SNDTIMEO, struct.pack(forma, int(secunde), 0))
            return True
        except (OSError, socket.error, AttributeError, ValueError, struct.error) as e:
            eroare = e
    jurnal.noteaza(ET, 'SO_SNDTIMEO: %s' % eroare)
    return False


def _neblocant(fd):
    import fcntl
    fl = fcntl.fcntl(fd, fcntl.F_GETFL)
    fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)


_server = []


def porneste():
    """Din imagine.porneste (firul principal). O singura data pe proces. -> serverul sau None."""
    if _server:
        return _server[0]
    s = Server()
    if s.porneste():
        _server.append(s)
        return s
    return None


def opreste():
    while _server:
        _server.pop().opreste()


def obtine():
    return _server[0] if _server else None


def sesiuni_deschise(ref=None):
    """Firul principal. Sesiunile serverului local care inca tin sau pot lua tunerul (Server.deschise), sau None daca
    serverul nu ruleaza. Asa afla controlorii DAB+ / DVB-T2 cand s-a eliberat tunerul dupa plecarea releului."""
    s = obtine()
    return s.deschise(ref) if s is not None else None


def opreste_sesiunile(ref):
    """Firul principal. Sesiunile de pe purtatorul `ref` se opresc pe loc (Server.opreste_sesiunile). -> numarul lor,
    0 daca serverul nu ruleaza."""
    s = obtine()
    return s.opreste_sesiunile(ref) if s is not None else 0


def refuzuri(ref):
    """Firul principal. Sesiunile purtatorului `ref` refuzate la rand (Server.refuzuri), sau None daca serverul nu
    ruleaza (alte imagini: acolo streamserverul nu spune asa ceva)."""
    s = obtine()
    return s.refuzuri(ref) if s is not None else None


def uita_refuzurile(ref):
    s = obtine()
    if s is not None:
        s.uita_refuzurile(ref)
