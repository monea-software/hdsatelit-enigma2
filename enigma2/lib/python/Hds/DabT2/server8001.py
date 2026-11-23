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
Cel mult SESIUNI_MAX sesiuni ale clientilor din retea deodata si SESIUNI_LOCALE_MAX ale releelor receptorului (0.7.8:
pana atunci un singur plafon pentru toate); numai referinte DVB de serviciu (fara cai de fisier, fara alte cereri).

0.7.7, INTAIETATEA TELEVIZORULUI: o sesiune ceruta din retea (VLC, telefonul, alt receptor care foloseste acest receptor ca
tuner de rezerva, Components/HdsTunerRezerva.py) tine tunerul ca o inregistrare; la zap, enigma2 nu o opreste (marcajul
setYieldsToZap ajuta numai lista de canale). Extensia de zap la_zap (pusa de porneste) face ca televizorul sa castige:
cand canalul cerut de televizor nu are tuner liber, sesiunile din retea de pe alt transponder, al aceluiasi fel de
tuner (satelit / cablu si terestru), se opresc pe rand, cea mai noua intai, pana cand televizorul are tuner; un rand in
jurnal pentru fiecare. Clientul primeste sfarsitul obisnuit al fluxului (soclul inchis dupa ultimii octeti), nu un
raspuns de eroare. Sesiunile de pe receptor (releele DAB+ / DVB-T2, releul modulului de acces) nu se ating aici: pe ele
le opreste extensia releelor, iar transmisia din browser are drumul ei (Components/HdsTransmisie.py).

0.7.8, PLECAREA DE PE UN RELEU DE PE RECEPTOR: un canal din buchet cu adresa releului scrisa direct
(http://127.0.0.1:<port>/<referinta>, nu din lista Stream Relay a imaginii) nu trece prin extensia releului, deci nimeni
nu oprea sesiunea prin care releul isi lua canalul de aici: ea mai tinea tunerul ~3 s dupa zap, iar cu un singur tuner
canalul urmator, de pe alt transponder, ramanea negru (allocate Channel: res -6). La zap, la_zap (cu serviciul de dinainte,
nav.hdsRefDinainteDeZap) si la_grup opresc intai, pe loc, sesiunile de pe receptor ale canalului vechi, cand canalul cerut e
pe alt transponder si nu are tuner (Server.lasa_releul_vechi); abia apoi vine intaietatea fata de clientii din retea.

0.7.7, INTAIETATEA INREGISTRARILOR: la fel pentru o inregistrare adevarata (temporizatorul, inregistrarea pe loc), prin
extensia de inregistrare la_inregistrare (pusa de porneste la COADA extensiilor de inregistrare, deci dupa releele DAB+ /
DVB-T2, care isi dau tunerul oricarei inregistrari, si dupa transmisia din browser si transcodare, puse la inceput).
Extensia ruleaza in Navigation.recordService, inainte de pnav.recordService; tunerul se aloca abia la prepare, imediat
dupa, cand sesiunile oprite l-au lasat deja. Deosebirea fata de zap: televizorul inca ruleaza, deci o sesiune de pe
transponderul lui imparte tunerul cu el, iar oprirea ei nu elibereaza nimic: ramane. Verificarile (simulate:
TimerSanityCheck, importul ghidului, fereastra temporizatorului) nu opresc nimic. Temporizatoarele de zap trec prin la_zap.

0.7.7, GRUPURILE DE ALTERNATIVE: la un grup, Navigation (si temporizatorul) alege intai alternativa care are tuner; cand
niciuna n-are (toate tinute de sesiuni din retea), zap-ul si inregistrarea se opreau inainte de la_zap / la_inregistrare.
Extensia la_grup (Navigation.grupFaraTuner, pusa de porneste) face aceeasi cedare pe toate alternativele DVB ale grupului
(felul de tuner al oricareia, nu de pe transponderul vreuneia), cea mai noua intai, pana cand o alternativa are tuner; la
o inregistrare raman sesiunile de pe transponderul televizorului, ca mai sus.

0.7.8, CLIENTII PENTRU TEME SI PLUGINURI: clienti_din_retea si opreste_clientul dau ce dau la OE-Alliance
eStreamServer.getConnectedClients / stopStreamClient / stopStream; enigma.eStreamServer (HdsEnigmaCompat.py) le citeste
la chemare. Cererile primesc si subserviciile (campurile 8-9 ale referintei nenule), ca la OE-Alliance.
"""
import collections
import errno
import gc
import os
import re
import select
import socket
import sys
import threading
import time

from . import compat, jurnal

# duratele si termenele sesiunilor pe ceasul monoton; ora de perete numai la inceputul inregistrarii enigma2
_monoton = compat.monoton

ET = '8001'
GAZDA = '127.0.0.1'
# 0.7.0: cu setarea "Fluxuri pentru alte aparate din reteaua de acasa" pornita serverul asculta pe toate interfetele,
# dar primeste numai adresele private (adresa_permisa); oprita, numai 127.0.0.1, ca pana acum
GAZDA_RETEA = '0.0.0.0'
PORT = 8001
SESIUNI_MAX = 2              # clientii din retea (VLC, Kodi, telefonul, alt receptor) deodata
# 0.7.8: releele receptorului (Stream Relay pentru televizor, DAB+, DVB-T2), cerute de la 127.0.0.1 sau de la adresa
# receptorului (_de_pe_receptor), au plafonul lor: doi clienti din retea nu mai lasa televizorul fara releu
SESIUNI_LOCALE_MAX = 6
TERMEN_CERERE_S = 5.0        # cat asteapta firul sesiunii randul GET
TERMEN_PORNIRE_S = 15.0      # cat asteapta firul sesiunii ca firul principal sa porneasca inregistrarea
TERMEN_GOLIRE_S = 5.0        # dupa plecarea clientului teava se goleste pana se opreste inregistrarea
TERMEN_TRIMITERE_S = 5      # o trimitere in soclu asteapta cel mult atat (SO_SNDTIMEO), ca firul sa nu stea agatat
TERMEN_FARA_CITIRE_S = 30.0  # un client care nu mai citeste atata timp e lasat: inregistrarea se opreste, tunerul e liber
CEAS_MS = 1000               # verificarea erorilor inregistrarilor, numai cat exista sesiuni
SECUNDE_FARA_DATE = 10       # o sesiune fara niciun octet atata timp lasa in jurnal starea acordului (o data)
# 0.7.5: canalul fara semnal. Releul modulului de acces (Stream Relay) cere canalul din nou la ~4 s dupa fiecare sesiune
# fara date, iar fiecare pornire de inregistrare scrie ~40 de randuri in jurnalul interfetei (start recording,
# HdsPazaDemux): 2 MB in ~50 de minute, deci inceputul penei se pierdea din jurnal. Dupa GOALE_LIBERE sesiuni pornite
# bine si incheiate fara date (sub PRAG_DATE_OCTETI), pe acelasi canal, inregistrarea urmatoare porneste abia dupa o
# pauza crescatoare (PAUZE_GOL_S); o cerere venita in pauza primeste pe loc raspunsul de refuz, fara inregistrare si fara
# rand in jurnal (un singur rand la inceputul fiecarei pauze). O sesiune cu date, uita_refuzurile (zap nou) sau
# fara_pauza (readucerea antenei, care vrea acordul pe loc) pornesc iar fara asteptare.
GOALE_LIBERE = 2
PAUZE_GOL_S = (5, 10, 20, 30, 60)
PRAG_DATE_OCTETI = 188 * 1000
CERERE_RECENTA_S = 90        # clientul canalului fara date "inca cere" daca a cerut in ultimele atatea secunde
EROARE_PAUZA = 'pauza dupa sesiuni fara date'
# sfarsitul unei sesiuni din retea oprite ca receptorul sa-si ia tunerul (in jurnal, ca motivul sesiunii incheiate)
MOTIV_TV = 'televizorul receptorului a luat tunerul'
MOTIV_INREGISTRARE = 'o inregistrare a receptorului a luat tunerul'
MOTIV_OPRIT = 'oprit de pe receptor (eStreamServer.stopStreamClient / stopStream)'
F_SETPIPE_SZ = 1031          # fcntl: marimea tevii (Linux)
TEAVA_OCTETI = 1024 * 1024   # se cere; daca nucleul refuza ramane marimea implicita
BLOC = 256 * 1024
_SPLICE = getattr(os, 'splice', None)

# 0.7.7: si fara doua puncte la coada ("...:0:0:0"), cum cer receptoarele OE-Alliance care folosesc acest receptor ca
# tuner de rezerva (Components/HdsTunerRezerva.py); ref_din_cerere le pune inapoi, deci restul vede aceeasi referinta.
# 0.7.8: campurile 8-9 (serviciul parinte al unui subserviciu) pot fi nenule, ca la streamserverul OE-Alliance
REF_BUNA = re.compile(r'^1:0:[0-9A-Fa-f]{1,4}:[0-9A-Fa-f]{1,4}:[0-9A-Fa-f]{1,4}:[0-9A-Fa-f]{1,4}:'
                      r'[0-9A-Fa-f]{1,8}:[0-9A-Fa-f]{1,4}:[0-9A-Fa-f]{1,4}:0:?$')
ANTET_200 = b'HTTP/1.0 200 OK\r\nConnection: Close\r\nContent-Type: video/mpeg\r\nServer: HDSatelit\r\n\r\n'
RASPUNS_400 = b'HTTP/1.0 400 Bad Request\r\nConnection: Close\r\n\r\n'


def ref_din_cerere(date):
    """Cererea HTTP (octeti, cel putin primul rand) -> referinta DVB, sau None: alt verb, alta cale, cale de fisier,
    caractere straine. Codarea %3A a doua puncte se primeste. Releele de flux termina randurile numai cu \\n, deci se
    primesc ambele feluri. 0.7.8: si subserviciile (campurile 8-9 nenule, REF_BUNA)."""
    try:
        rand = bytes(date).split(b'\n', 1)[0].rstrip(b'\r').decode('ascii')
    except (UnicodeDecodeError, ValueError):
        return None
    parti = rand.split(' ')
    if len(parti) != 3 or parti[0] != 'GET' or not parti[2].startswith('HTTP/1.') or not parti[1].startswith('/'):
        return None
    ref = parti[1][1:].replace('%3A', ':').replace('%3a', ':')
    if not REF_BUNA.match(ref):
        return None
    return ref if ref.endswith(':') else ref + ':'


def adresa_privata(ip):
    """0.7.0: True pentru o adresa IPv4 din reteaua de acasa (10.x.x.x, 172.16-31.x.x, 192.168.x.x; din si
    169.254.x.x, legatura directa fara DHCP)."""
    try:
        a = [int(x) for x in str(ip).split('.')]
    except ValueError:
        return False
    if len(a) != 4 or not all(0 <= x <= 255 for x in a):
        return False
    return (a[0] == 10 or (a[0] == 172 and 16 <= a[1] <= 31) or (a[0] == 192 and a[1] == 168)
            or (a[0] == 169 and a[1] == 254))


def adresa_permisa(ip, retea):
    """Cine poate cere un flux: 127.0.0.1 mereu; cu setarea "Fluxuri pentru alte aparate din reteaua de acasa"
    pornita si adresele private; din internet niciodata."""
    return ip == GAZDA or (bool(retea) and adresa_privata(ip))


def retea_pornita():
    """Setarea config.misc.hds_fluxuri_retea_acasa (Components/UsageConfig.py, pornita din fabrica din 0.7.4); fara
    ea (probele de pe PC, alt cod) sau la orice eroare: oprita."""
    try:
        import sys
        return bool(sys.modules['Components.config'].config.misc.hds_fluxuri_retea_acasa.value)
    except Exception:
        return False


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
        self.pornita_bine = False            # numai firul principal: inregistrarea a pornit (pentru pauza canalelor fara date)
        self.in_pauza = False                # numai firul principal: cererea a venit in pauza, fara inregistrare
        self.tuner = None                    # (tuner_number, orbital_position) citite la pornire, sau None
        self.cedata = False                  # firul principal: oprita ca televizorul sa ia tunerul (cedeaza_televizorului)
        self.motiv_cedare = MOTIV_TV         # sau MOTIV_INREGISTRARE (cedeaza_inregistrarii): sfarsitul sesiunii cedate
        self.locala = None                   # 0.7.8: ceruta de pe receptor (_de_pe_receptor, tinut minte la prima citire)
        self.fir = threading.Thread(target=self._lucreaza, name='hds8001')
        self.fir.daemon = True

    # ------------------------------------------------------------ firul sesiunii
    def _citeste_cererea(self):
        self.conn.settimeout(TERMEN_CERERE_S)
        date = bytearray()
        while b'\r\n\r\n' not in date and b'\n\n' not in date and len(date) < 4096:
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
                    return self.motiv_cedare if self.cedata else 'inregistrarea a inchis teava'
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
        self.retea = gazda == GAZDA_RETEA    # 0.7.0: se primesc si adresele private (adresa_permisa)
        self._ascultare = None               # (notificatorul, manierul) soclului de ascultare: schimba_reteaua
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
        # pe cheia canalului: sesiunile pornite bine si incheiate fara date, la rand ({'n', 'la', 'cerere', 'tuner'})
        self._goale = {}

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
            self._ascultare = (self._notificatori[0], self._maniere[0])
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

    def schimba_reteaua(self, pornita):
        """0.7.0, firul principal, la schimbarea setarii retelei de acasa: soclul de ascultare se leaga din nou
        (GAZDA_RETEA pornita, GAZDA oprita); oprita, sesiunile cerute din retea se opresc. Sesiunile de pe 127.0.0.1
        raman. Daca noua legare nu merge, se revine la cea de dinainte. -> True daca serverul asculta. Nu arunca."""
        pornita = bool(pornita)
        self.retea = pornita
        if not pornita:
            for ses in list(self.sesiuni):
                if ses.adresa and ses.adresa[0] != GAZDA:
                    self._opreste_inregistrarea(ses)
        gazda = GAZDA_RETEA if pornita else GAZDA
        if self.sock is None or gazda == self.gazda:
            return self.sock is not None
        vechea = self.gazda
        self._inchide_ascultarea()
        if self._asculta(gazda):
            jurnal.noteaza(ET, 'serverul local de flux asculta acum pe %s:%d' % (gazda, self.port))
            return True
        jurnal.noteaza(ET, 'serverul local de flux nu poate asculta pe %s:%d; ramane pe %s' % (gazda, self.port, vechea))
        self.retea = vechea == GAZDA_RETEA
        return self._asculta(vechea)

    def _inchide_ascultarea(self):
        if self._ascultare is not None:
            n, manier = self._ascultare
            self._ascultare = None
            compat.deconecteaza(manier)
            if manier in self._maniere:
                self._maniere.remove(manier)
            if n in self._notificatori:
                self._notificatori.remove(n)
        if self.sock is not None:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None

    def _asculta(self, gazda):
        s = None
        try:
            from enigma import eSocketNotifier
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((gazda, self.port))
            s.listen(4)
            s.setblocking(False)
            n = eSocketNotifier(s.fileno(), 1)
            manier = compat.conecteaza(n.callback, self._accepta)
        except Exception as e:
            jurnal.noteaza(ET, 'legarea pe %s:%d: %s' % (gazda, self.port, e))
            if s is not None:
                try:
                    s.close()
                except Exception:
                    pass
            return False
        self.sock, self.gazda = s, gazda
        self._maniere.append(manier)
        self._notificatori.append(n)
        self._ascultare = (n, manier)
        return True

    def _accepta(self, _ce=None):
        while self.sock is not None:
            try:
                conn, adresa = self.sock.accept()
            except (OSError, socket.error):
                return
            if adresa and not adresa_permisa(adresa[0], self.retea):
                conn.close()
                continue
            ses = Sesiune(self, conn, adresa)
            # 0.7.8: plafonul clientilor din retea nu se umple cu releele receptorului si nici invers
            locala = _de_pe_receptor(ses)
            la_fel = sum(1 for s in self.sesiuni if _de_pe_receptor(s) == locala)
            if la_fel >= (SESIUNI_LOCALE_MAX if locala else self.sesiuni_max):
                ses.eroare = 'prea multe sesiuni (%d)' % la_fel
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
                    if ses.in_pauza:
                        continue                 # cererea din pauza: nimic in jurnal (randul l-a scris inceputul pauzei)
                    jurnal.noteaza(ET, 'sesiune incheiata %s: %s, %d octeti in %d s' % (
                        ses.ref or '-', rest[0] if rest else '-', ses.octeti, int(_monoton() - ses.inceput)))
                    if not ses.cedata:           # oprita pentru televizor: nu e un canal fara date
                        self._noteaza_capatul(ses)
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
        if self.pauza_ramasa(ses.ref) > 0:
            # canalul a dat numai sesiuni fara date: fara inregistrare pana la capatul pauzei, fara rand in jurnal si fara
            # numarare la refuzuri (controlorii DAB+ / DVB-T2 numara acolo tunerul ocupat)
            self._goale[_cheie_ref(ses.ref)]['cerere'] = _monoton()
            ses.in_pauza = True
            ses.eroare = EROARE_PAUZA
            ses.oprita.set()
            ses.pornita.set()
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
            # Orice cerere (VLC, Kodi, telefonul, browserul prin HdsTransmisie, un releu Stream Relay pus de om) primeste
            # fluxul descifrat de receptor: inregistrarea se inscrie la modulul de acces ca orice flux, iar canalele
            # CSA-ALT (ICAM) le descifreaza nucleul in software (SoftCSA, lib/service/servicedvbrecord.cpp
            # softCsaRecord). Pana la 0.7.4 un canal din lista Stream Relay cerut din retea venea criptat (pentru un
            # releu de pe alt aparat), deci VLC pe 8001 nu vedea canalele Sky din lista; drumul acela e scos.
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
            ses.pornita_bine = True
            ses.tuner = _tuner_rec(rec)
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
                if ses.tuner is None:
                    ses.tuner = _tuner_rec(ses.rec)
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

    def lasa_releul_vechi(self, vechi, cerut, liber):
        """Firul principal, la zap (la_zap, la_grup), cand televizorul pleaca de pe `vechi` (textul serviciului de dinainte).
        Daca `vechi` e un canal redat printr-un releu de pe receptor (ref_releu: calea http://127.0.0.1:<orice port>/<referinta>,
        si cu adresa scrisa direct in buchet, nu numai canalele din lista Stream Relay a imaginii), sesiunea prin care releul
        isi ia canalul de aici mai tine tunerul cateva secunde: releul afla abia acum ca playerul a plecat si isi inchide
        cererea dupa aceea (~3 s, cu un singur tuner), iar canalul cerut ar gasi tunerul ocupat (allocate Channel: res -6,
        ecran negru). `cerut`: textul serviciului cerut (canal DVB sau alt canal prin releu, a carui referinta o cere apoi
        releul) sau lista alternativelor unui grup; `liber()`: True cand televizorul are tuner pentru el. Cand niciunul
        dintre cele cerute nu e pe transponderul canalului vechi si televizorul n-are tuner, sesiunile de pe receptor ale
        canalului vechi se opresc pe loc; daca tunerul tot nu e liber (obiectul inregistrarii tinut de un ciclu de
        referinte), gunoiul se strange o data. Cele din retea raman pentru cedeaza_televizorului. -> cate sesiuni s-au
        oprit."""
        tinta = ref_releu(vechi)
        if not tinta:
            return 0
        cerute = [ref_releu(r) or r for r in (cerut if isinstance(cerut, (list, tuple)) else [cerut])]
        cerute = [r for r in cerute if _ref_dvb_fara_cale(r)]
        if not cerute or any(_acelasi_transponder(tinta, r) for r in cerute):
            return 0
        cheie = _cheie_ref(tinta)
        ale_releului = [ses for ses in self.sesiuni if not ses.oprita.is_set() and _cheie_ref(ses.ref) == cheie
            and _de_pe_receptor(ses)]
        if not ale_releului or liber():
            return 0
        jurnal.noteaza(ET, 'televizorul pleaca de pe %s (prin releul de pe receptor) spre %s si n-are tuner liber: opresc pe '
            'loc %d sesiuni ale releului' % (cheie, ', '.join(_cheie_ref(r) for r in cerute), len(ale_releului)))
        for ses in ale_releului:
            self._opreste_inregistrarea(ses)
        self._porneste_ceasul()
        if not liber():
            # tunerul se elibereaza abia cand se distruge obiectul inregistrarii, nu la rec.stop(); cand il mai tine un ciclu
            # de referinte Python, asta se intampla la strangerea gunoiului, uneori dupa minute (proba ZAP8 pe receptorul de
            # probe SF8008: 33 s si 112 s cu ecran negru): gunoiul se strange acum, o data
            t = _monoton()
            n = gc.collect()
            jurnal.noteaza(ET, 'dupa oprirea releului tunerul era tot ocupat: gunoiul strans (%d obiecte, %d ms), tuner '
                'liber: %s' % (n, int((_monoton() - t) * 1000), 'da' if liber() else 'nu'))
        return len(ale_releului)

    def cedeaza_televizorului(self, ref, liber):
        """Firul principal, la zap (la_zap), dupa oprirea serviciului vechi. `ref`: textul referintei cerute de
        televizor; `liber()`: True cand televizorul are tuner pentru ea (isPlayable). Daca n-are, sesiunile cerute din
        retea (nu de pe receptor) de pe alt transponder, al aceluiasi fel de tuner, se opresc pe rand, cea mai noua
        intai, pana cand liber() spune da; inregistrarea oprita inchide teava, iar firul sesiunii incheie fluxul
        obisnuit (soclul inchis dupa ultimii octeti). `ref` poate fi si lista alternativelor unui grup (la_grup).
        -> cate sesiuni s-au oprit."""
        return self._cedeaza(ref, liber, 'televizorul', MOTIV_TV)

    def cedeaza_inregistrarii(self, ref, liber, tv=None):
        """Firul principal, la o inregistrare adevarata (la_inregistrare, la_grup), inainte ca ea sa ceara tunerul. Ca
        la televizor (`liber()`: isPlayable pentru `ref`), dar televizorul inca ruleaza: sesiunile de pe transponderul
        lui (`tv`, textul referintei redate, sau None) impart tunerul cu el, deci raman. `ref` poate fi si lista
        alternativelor unui grup. -> cate sesiuni s-au oprit."""
        return self._cedeaza(ref, liber, 'o inregistrare', MOTIV_INREGISTRARE, tv)

    def _cedeaza(self, ref, liber, cine, motiv, ramane=None):
        # `ref`: o referinta, sau lista alternativelor unui grup (la_grup): felul de tuner al oricareia, nu de pe
        # transponderul vreuneia (acolo tunerul se imparte, deci oprirea n-ar elibera nimic)
        grup = isinstance(ref, (list, tuple))
        cerute = [r for r in (ref if grup else [ref]) if _ref_dvb_fara_cale(r)]
        if not cerute:
            return 0
        if not _ref_dvb_fara_cale(ramane):
            ramane = None
        feluri = set(_fel_tuner(r) for r in cerute)
        candidati = [ses for ses in self.sesiuni if ses.rec is not None and not ses.oprita.is_set()
            and not _de_pe_receptor(ses) and _fel_tuner(ses.ref) in feluri
            and not any(_acelasi_transponder(ses.ref, r) for r in cerute)
            and not (ramane and _acelasi_transponder(ses.ref, ramane))]
        if not candidati or liber():
            return 0
        if grup:
            text = 'grupul de alternative (%s)' % ', '.join(_cheie_ref(r) for r in cerute)
        else:
            text = _cheie_ref(cerute[0])
        n = 0
        for ses in sorted(candidati, key=lambda x: x.inceput, reverse=True):
            ip = ses.adresa[0] if ses.adresa else '?'
            jurnal.noteaza(ET, '%s cere %s si n-are tuner liber: opresc fluxul %s cerut de %s (%d octeti in %d s)' % (
                cine, text, ses.ref, ip, ses.octeti, int(_monoton() - ses.inceput)))
            ses.cedata = True
            ses.motiv_cedare = motiv
            self._opreste_inregistrarea(ses)
            n += 1
            if liber():
                break
        self._porneste_ceasul()
        return n

    def refuzuri(self, ref):
        """Firul principal. Cate sesiuni ale purtatorului `ref` au fost refuzate la rand (inregistrarea nu a pornit:
        tuner ocupat, acord cazut) de la ultima pornire buna. 0 dupa o pornire buna sau pentru un purtator necerut."""
        return self._refuzuri.get(_cheie_ref(ref), 0) if ref else 0

    def uita_refuzurile(self, ref):
        """Firul principal. Un zap nou pe purtator incepe numaratoarea de la zero (si pauza canalelor fara date)."""
        if ref:
            self._refuzuri.pop(_cheie_ref(ref), None)
            self._goale.pop(_cheie_ref(ref), None)

    # ------------------------------------------------------------ pauza canalelor fara date (0.7.5)
    def pauza_ramasa(self, ref, acum=None):
        """Firul principal. Cate secunde mai tine pauza canalului `ref` (0 = inregistrarea porneste pe loc)."""
        g = self._goale.get(_cheie_ref(ref)) if ref else None
        if not g or g['n'] <= GOALE_LIBERE:
            return 0.0
        pauza = PAUZE_GOL_S[min(g['n'] - GOALE_LIBERE, len(PAUZE_GOL_S)) - 1]
        return max(0.0, g['la'] + pauza - (_monoton() if acum is None else acum))

    def _noteaza_capatul(self, ses):
        """Firul principal, la incheierea unei sesiuni: cu date, pauza canalului se uita; pornita bine si fara date, se
        numara (cu tunerul si satelitul ei, pentru readucerea antenei). Refuzurile nu intra aici."""
        cheie = _cheie_ref(ses.ref)
        if not cheie or not ses.pornita_bine:
            return
        if ses.octeti >= PRAG_DATE_OCTETI:
            if self._goale.pop(cheie, None) is not None:
                jurnal.noteaza(ET, 'canalul %s da iar date: fara pauza' % ses.ref)
            return
        acum = _monoton()
        g = self._goale.setdefault(cheie, {'n': 0, 'la': acum, 'cerere': acum, 'tuner': None})
        g['n'] += 1
        g['la'] = g['cerere'] = acum
        if ses.tuner is not None:
            g['tuner'] = ses.tuner
        if g['n'] > GOALE_LIBERE:
            jurnal.noteaza(ET, 'canalul %s fara date in %d sesiuni la rand: urmatoarea pornire peste %d s' % (
                ses.ref, g['n'], int(round(self.pauza_ramasa(ses.ref, acum)))))

    def fara_pauza(self, ref):
        """Firul principal. Cererea urmatoare a canalului porneste inregistrarea pe loc (numaratoarea ramane: daca nici
        atunci nu vin date, pauza urmatoare e cea lunga). -> True daca era o pauza de sters."""
        g = self._goale.get(_cheie_ref(ref)) if ref else None
        if not g:
            return False
        g['la'] = -1e9
        return True

    def tunere(self, acum=None):
        """Firul principal. Tunerele tinute (sau cerute din nou) de sesiunile serverului: [{'slot', 'orbital', 'blocat',
        'ref', 'in_pauza'}]. Sesiunile pornite: tunerul inregistrarii, citit acum. Canalele fara date pe care clientul
        le cere inca (de cel mult CERERE_RECENTA_S): tunerul ultimei lor sesiuni, fara semnal, chiar daca acum nu e
        nicio inregistrare (pauza sau clipa dintre doua cereri)."""
        acum = _monoton() if acum is None else acum
        lista, vazute = [], set()
        for ses in list(self.sesiuni):
            if ses.rec is None or ses.oprita.is_set():
                continue
            t = _tuner_rec(ses.rec, cu_semnal=True)
            if t is None:
                continue
            vazute.add(_cheie_ref(ses.ref))
            lista.append({'slot': t[0], 'orbital': t[1], 'blocat': t[2], 'ref': ses.ref, 'in_pauza': False})
        for cheie, g in list(self._goale.items()):
            if cheie in vazute or g.get('tuner') is None or acum - g['cerere'] > CERERE_RECENTA_S:
                continue
            lista.append({'slot': g['tuner'][0], 'orbital': g['tuner'][1], 'blocat': False, 'ref': cheie,
                'in_pauza': True})
        return lista

    def stare(self):
        return {'asculta': self.sock is not None, 'sesiuni': len(self.sesiuni), 'pornite': self.pornite,
                'refuzate': self.refuzate,
                'detalii': [{'ref': s.ref, 'octeti': s.octeti, 'secunde': int(_monoton() - s.inceput),
                             'eroare': s.eroare} for s in self.sesiuni]}


def _cheie_ref(ref):
    """Referinta DVB ca cheie de comparatie: primele 10 campuri, litere mici, fara ':' la sfarsit."""
    return ':'.join(str(ref or '').split(':')[:10]).rstrip(':').lower()


def _ref_dvb_fara_cale(ref):
    """Textul unei referinte de canal DVB (tipul 1, cu numarul serviciului, fara cale): ce poate cere un tuner."""
    p = str(ref or '').split(':')
    if len(p) < 10 or p[0] != '1' or (len(p) > 10 and p[10].strip()):
        return False
    try:
        return int(p[1] or '0') & (1 | 2 | 64) == 0 and int(p[3] or '0', 16) != 0
    except ValueError:
        return False


def _acelasi_transponder(a, b):
    """Doua referinte DVB pe acelasi transponder (TSID, ONID, spatiul de nume): tunerul se imparte."""
    pa, pb = str(a or '').split(':'), str(b or '').split(':')
    try:
        return len(pa) > 6 and len(pb) > 6 and all(int(pa[i] or '0', 16) == int(pb[i] or '0', 16) for i in (4, 5, 6))
    except ValueError:
        return False


def _fel_tuner(ref):
    """Felul de tuner al unei referinte, dupa spatiul de nume: 'ct' cablu si terestru (FFFF..., EEEE...; tunerele
    combinate le iau pe amandoua), 'atsc' (DDDD...), altfel 's' (satelit, pozitia orbitala in partea de sus)."""
    try:
        sus = int(str(ref or '').split(':')[6], 16) >> 16
    except (IndexError, ValueError):
        return None
    return 'ct' if sus in (0xFFFF, 0xEEEE) else 'atsc' if sus == 0xDDDD else 's'


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


def _tuner_rec(rec, cu_semnal=False):
    """(tuner_number, orbital_position) al inregistrarii (cu tuner_locked la sfarsit daca cu_semnal), sau None cand nu
    e pe un tuner de satelit sau nu se poate citi."""
    try:
        fi = rec.frontendInfo()
        if fi is None:
            return None
        slot = int((fi.getFrontendData() or {}).get('tuner_number', -1))
        orbital = int((fi.getTransponderData(True) or {}).get('orbital_position', -1))
        if slot < 0 or orbital < 0:
            return None
        if not cu_semnal:
            return slot, orbital
        try:
            d = fi.getFrontendStatus()
        except TypeError:
            d = {}
            fi.getFrontendStatus(d)
        return slot, orbital, bool((d or {}).get('tuner_locked'))
    except Exception:
        return None


def _stare_tuner(rec):
    """Starea acordului inregistrarii, pentru jurnal: tuner_state din enigma2 (LOCKED, TUNING, FAILED...)."""
    try:
        fi = rec.frontendInfo()
        d = fi.getFrontendStatus() if fi is not None else None
        text = '%s, blocat %s' % (d.get('tuner_state'), d.get('tuner_locked')) if isinstance(d, dict) else '?'
    except Exception as e:
        text = 'necunoscut (%s)' % e
    try:
        # programul din PMT si demux-ul inregistrarii (eDVBServiceRecord::getStreamingData). PID-urile tinute minte in
        # lamedb (c:18, PID-ul de date al purtatorilor de pe 30W) nu apar aici, desi inregistrarea le pune in filtru
        # (RECORD: PID tinut minte, in hds-interfata.log): fara acel rand, filtrul are numai ce e aici
        s = rec.stream()
        date = s.getStreamingData() if s is not None else None
        if isinstance(date, dict):
            text += '; program din PMT (fara PID-urile din lamedb) %s' % str(sorted(date.items()))[:300]
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
    s = Server(gazda=GAZDA_RETEA if retea_pornita() else GAZDA)
    if s.porneste():
        _server.append(s)
        _urmareste_reteaua(s)
        _leaga_zap()
        _leaga_inregistrarea()
        _leaga_grupul()
        return s
    return None


def _tuner_liber(sref):
    """Un tuner poate lua `sref` acum (isPlayable, nimic ignorat): la zap serviciul vechi e deja oprit cand se cheama
    extensiile; la o inregistrare televizorul isi tine tunerul (pe acelasi transponder il imparte)."""
    try:
        from enigma import eServiceCenter, eServiceReference
        info = eServiceCenter.getInstance().info(sref)
        return bool(info and info.isPlayable(sref, eServiceReference()))
    except Exception:
        return True                          # nu se poate afla: nimic oprit


def _tuner_liber_text(text):
    """_tuner_liber pentru textul unei referinte DVB (canalul pe care il cere un releu de pe receptor)."""
    try:
        from enigma import eServiceReference
        return _tuner_liber(eServiceReference(text))
    except Exception:
        return True


def _text_serviciu(ref):
    """Textul unei referinte (eServiceReference sau text), sau None."""
    if ref is None:
        return None
    try:
        return ref.toString()
    except Exception:
        return str(ref)


def la_zap(nav, playref, *rest):
    """Navigation.playServiceExtensions: intai sesiunile releului de pe receptor al canalului de pe care pleaca
    televizorul (Server.lasa_releul_vechi, cu nav.hdsRefDinainteDeZap; nu mai au cui da fluxul), apoi intaietatea
    televizorului fata de sesiunile cerute din retea (Server.cedeaza_televizorului). Referinta ramane neschimbata; nicio
    eroare nu opreste zap-ul."""
    s = obtine()
    if s is None or not s.sesiuni or playref is None:
        return playref
    text = playref.toString()
    try:
        tinta = ref_releu(text)
        liber = (lambda: _tuner_liber(playref)) if tinta is None else (lambda: _tuner_liber_text(tinta))
        s.lasa_releul_vechi(_text_serviciu(getattr(nav, 'hdsRefDinainteDeZap', None)), text, liber)
    except Exception:
        jurnal.eroare(ET, 'plecarea de pe releul de pe receptor')
    try:
        s.cedeaza_televizorului(text, lambda: _tuner_liber(playref))
    except Exception:
        jurnal.eroare(ET, 'intaietatea televizorului')
    return playref


def _lista_zap():
    try:
        from Navigation import Navigation
        return Navigation.playServiceExtensions
    except Exception:
        return None


def _leaga_zap(lista=None):
    """La pornirea serverului: la_zap la inceputul extensiilor de zap (inaintea releelor si a tunerului de rezerva)."""
    lista = _lista_zap() if lista is None else lista
    if isinstance(lista, list) and la_zap not in lista:
        lista.insert(0, la_zap)


def _dezleaga_zap(lista=None):
    lista = _lista_zap() if lista is None else lista
    while isinstance(lista, list) and la_zap in lista:
        lista.remove(la_zap)


def _simulata():
    """Cererea de inregistrare e numai o verificare: variabila locala `simulate` a lui Navigation._extensiiInregistrare
    (cadrul care cheama extensia), cautata in cel mult trei cadre deasupra extensiei. Necitita: inregistrare adevarata
    (inregistrarea castiga), ca la releele DAB+ / DVB-T2 (pornire._simulare)."""
    try:
        cadru = sys._getframe(2)             # 0 aceasta functie, 1 la_inregistrare, 2 cine a chemat extensia
        for _pas in range(3):
            if cadru is None:
                break
            if 'simulate' in cadru.f_locals:
                return bool(cadru.f_locals['simulate'])
            cadru = cadru.f_back
    except Exception:
        pass
    return False


def _ref_tv(nav):
    """Textul referintei redate acum de televizor, sau None (oprit, in asteptare, nu se poate afla)."""
    try:
        r = nav.getCurrentlyPlayingServiceReference()
        return r.toString() if r is not None else None
    except Exception:
        return None


def _in_principal():
    try:
        from . import fir
        return fir.in_principal()
    except Exception:
        return True


def la_inregistrare(nav, ref, *rest):
    """Navigation.recordServiceExtensions: intaietatea inregistrarilor adevarate fata de sesiunile cerute din retea
    (Server.cedeaza_inregistrarii). Fara sesiuni (si la fiecare verificare simulate a importului ghidului) se intoarce pe
    loc. Din alt fir decat cel principal enigma2 nu se atinge: cedarea se face in firul principal, cat de curand, iar
    temporizatorul o gaseste la urmatoarea incercare. Referinta ramane neschimbata; nicio eroare nu opreste inregistrarea."""
    s = obtine()
    if s is None or not s.sesiuni or ref is None or _simulata():
        return ref
    try:
        text, tv = ref.toString(), _ref_tv(nav)
        if not _in_principal():
            from . import fir
            jurnal.noteaza(ET, 'o inregistrare din alt fir cere %s: cedez in firul principal' % _cheie_ref(text))
            fir.programeaza(s.cedeaza_inregistrarii, text, lambda: _tuner_liber(ref), tv)
            return ref
        s.cedeaza_inregistrarii(text, lambda: _tuner_liber(ref), tv)
    except Exception:
        jurnal.eroare(ET, 'intaietatea inregistrarii')
    return ref


def _lista_inregistrare():
    try:
        from Navigation import Navigation
        return Navigation.recordServiceExtensions
    except Exception:
        return None


def _leaga_inregistrarea(lista=None):
    """La pornirea serverului: la_inregistrare la COADA extensiilor de inregistrare, dupa releele DAB+ / DVB-T2 (puse
    inainte, la pornirea sesiunii), care isi dau tunerul oricarei inregistrari adevarate."""
    lista = _lista_inregistrare() if lista is None else lista
    if isinstance(lista, list) and la_inregistrare not in lista:
        lista.append(la_inregistrare)


def _dezleaga_inregistrarea(lista=None):
    lista = _lista_inregistrare() if lista is None else lista
    while isinstance(lista, list) and la_inregistrare in lista:
        lista.remove(la_inregistrare)


def _alternative(grup):
    """Textele alternativelor DVB ale grupului `grup` (canalele care cer un tuner), in ordinea grupului; [] daca nu se
    pot afla."""
    try:
        from enigma import eServiceCenter
        lista = eServiceCenter.getInstance().list(grup)
        texte = (lista and lista.getContent('S', True)) or []
    except Exception:
        return []
    return [t for t in texte if _ref_dvb_fara_cale(t)]


def la_grup(nav, grup, liber, inregistrare=False, *rest):
    """Navigation.grupFaraTuner: niciuna dintre alternativele unui grup n-are tuner (Navigation.celMaiBunDinGrup), deci
    zap-ul si inregistrarea nu ajung la la_zap / la_inregistrare. Aceeasi intaietate, pe toate alternativele DVB ale
    grupului: la zap ca la televizor, la o inregistrare adevarata ca la inregistrari (sesiunile de pe transponderul
    televizorului raman); `liber()` (dat de Navigation, aceeasi intrebare ca la alegerea alternativei) spune cand o
    alternativa are tuner. Verificarile simulate nu ajung aici. Nicio eroare nu opreste zap-ul sau inregistrarea."""
    s = obtine()
    if s is None or not s.sesiuni or grup is None:
        return
    try:
        alternative = _alternative(grup)
        if not alternative:
            return
        if not inregistrare:
            # Navigation alege alternativa inainte sa opreasca serviciul vechi: televizorul inca reda canalul releului
            s.lasa_releul_vechi(_ref_tv(nav), alternative, liber)
            s.cedeaza_televizorului(alternative, liber)
            return
        tv = _ref_tv(nav)
        if not _in_principal():
            from . import fir
            jurnal.noteaza(ET, 'o inregistrare din alt fir cere grupul de alternative (%s): cedez in firul principal' % (
                ', '.join(_cheie_ref(r) for r in alternative)))
            fir.programeaza(s.cedeaza_inregistrarii, alternative, liber, tv)
            return
        s.cedeaza_inregistrarii(alternative, liber, tv)
    except Exception:
        jurnal.eroare(ET, 'intaietatea pe grupul de alternative')


def _lista_grup():
    try:
        from Navigation import Navigation
        return Navigation.grupFaraTuner
    except Exception:
        return None


def _leaga_grupul(lista=None):
    """La pornirea serverului: la_grup in Navigation.grupFaraTuner (o singura data)."""
    lista = _lista_grup() if lista is None else lista
    if isinstance(lista, list) and la_grup not in lista:
        lista.append(la_grup)


def _dezleaga_grupul(lista=None):
    lista = _lista_grup() if lista is None else lista
    while isinstance(lista, list) and la_grup in lista:
        lista.remove(la_grup)


def _urmareste_reteaua(s):
    """0.7.0: la schimbarea setarii retelei de acasa (televizor sau web) serverul se leaga din nou, pe loc."""
    try:
        import sys
        element = sys.modules['Components.config'].config.misc.hds_fluxuri_retea_acasa
    except Exception:
        return
    element.addNotifier(lambda el: s.schimba_reteaua(el.value), initial_call=False)


def opreste():
    _dezleaga_zap()
    _dezleaga_inregistrarea()
    _dezleaga_grupul()
    while _server:
        _server.pop().opreste()


def obtine():
    return _server[0] if _server else None


def sesiuni_deschise(ref=None):
    """Firul principal. Sesiunile serverului local care inca tin sau pot lua tunerul (Server.deschise), sau None daca
    serverul nu ruleaza. Asa afla controlorii DAB+ / DVB-T2 cand s-a eliberat tunerul dupa plecarea releului."""
    s = obtine()
    return s.deschise(ref) if s is not None else None


ADRESE_LOCALE = ('127.0.0.1', '::1', '::ffff:127.0.0.1')


def _de_pe_receptor(ses):
    """Clientul sesiunii e chiar receptorul: 127.0.0.1, sau adresa lui din retea (atunci adresa clientului e aceeasi cu
    adresa locala a legaturii). Releul modulului cere canalul de la 127.0.0.1 pentru televizor, dar de la adresa din
    retea a receptorului pentru un aparat din casa (o ia din cererea aparatului; proba WCR pe receptorul de probe SF8008, 14.11.2026)."""
    ip = ses.adresa[0] if ses.adresa else None
    if not ip:
        return False
    if ip in ADRESE_LOCALE:
        return True
    stiut = getattr(ses, 'locala', None)     # 0.7.8: tinut minte, ca dupa inchiderea soclului sa ramana acelasi
    if stiut is not None:
        return stiut
    try:
        ses.locala = ses.conn.getsockname()[0] == ip
    except Exception:
        return False
    return ses.locala


def sesiuni_locale(ref):
    """Firul principal. Cate sesiuni deschise ale serviciului `ref` (aceeasi cheie ca la deschise) au fost cerute de pe
    receptor (_de_pe_receptor): asa isi ia canalul releul modulului de acces (Stream Relay). Cat releul da un canal,
    modulul trimite cuvintele lui numai releului (Components/HdsTransmisie.py, TEXT_GASIT_RELEU). 0 fara server."""
    s = obtine()
    cheie = _cheie_ref(ref)
    if s is None or not cheie:
        return 0
    return sum(1 for x in list(s.sesiuni) if not x.oprita.is_set() and _cheie_ref(x.ref) == cheie
        and _de_pe_receptor(x))


def _client_din_retea(ses):
    """Sesiunea unui client din retea care primeste (sau abia porneste) un flux: referinta citita, nerefuzata, neoprita,
    nu un releu al receptorului."""
    return bool(ses.ref) and not ses.eroare and not ses.in_pauza and not ses.oprita.is_set() and not _de_pe_receptor(ses)


def clienti_din_retea():
    """0.7.8, firul principal. Clientii din retea, in ordinea venirii, ca eStreamServer.getConnectedClients din OE-Alliance:
    [(adresa, referinta, 0)] (0 = fara transcodare). Releele receptorului (Stream Relay pentru televizor, DAB+, DVB-T2)
    nu sunt clienti: asa reda televizorul acele canale. [] fara server. Il citesc enigma.eStreamServer (HdsEnigmaCompat),
    temele (convertorul ClientsStreaming, addon-ul ServiceInfoBar) si pluginurile."""
    s = obtine()
    if s is None:
        return []
    return [(str(x.adresa[0]), x.ref, 0) for x in list(s.sesiuni) if _client_din_retea(x)]


def opreste_clientul(ip=None, ref=None):
    """0.7.8, firul principal. Opreste primul client din retea cu adresa `ip` si referinta `ref` (aceeasi cheie ca la
    deschise; fara ele, primul client), ca eStreamServer.stopStreamClient / stopStream. Clientul primeste sfarsitul
    obisnuit al fluxului, tunerul e liber cand se intoarce functia. -> True daca a oprit unul."""
    s = obtine()
    if s is None:
        return False
    cheie = _cheie_ref(ref) if ref else None
    for ses in list(s.sesiuni):
        if not _client_din_retea(ses):
            continue
        if ip is not None and str(ses.adresa[0]) != str(ip):
            continue
        if cheie is not None and _cheie_ref(ses.ref) != cheie:
            continue
        jurnal.noteaza(ET, 'fluxul %s cerut de %s oprit de pe receptor (%d octeti in %d s)' % (
            ses.ref, ses.adresa[0], ses.octeti, int(_monoton() - ses.inceput)))
        ses.cedata = True
        ses.motiv_cedare = MOTIV_OPRIT
        s._opreste_inregistrarea(ses)
        s._porneste_ceasul()
        return True
    return False


def opreste_sesiunile(ref):
    """Firul principal. Sesiunile de pe purtatorul `ref` se opresc pe loc (Server.opreste_sesiunile). -> numarul lor,
    0 daca serverul nu ruleaza."""
    s = obtine()
    return s.opreste_sesiunile(ref) if s is not None else 0


def frontend_sesiune(ref):
    """Firul principal. frontendInfo() al inregistrarii unei sesiuni deschise de pe purtatorul `ref`: tunerul care tine
    canalul pe care Stream Relay (OSCam/NCam) il ia de aici. None daca nu e nicio sesiune sau serverul nu ruleaza."""
    s = obtine()
    cheie = _cheie_ref(ref)
    if s is None or not cheie:
        return None
    for ses in list(s.sesiuni):
        rec = ses.rec
        if rec is None or ses.oprita.is_set() or _cheie_ref(ses.ref) != cheie:
            continue
        try:
            fe = rec.frontendInfo()
        except Exception:
            fe = None
        if fe is not None:
            return fe
    return None


def ref_releu(sref):
    """Referinta DVB redata prin Stream Relay de pe receptor (calea http://127.0.0.1:<port>/<referinta>, ca la
    HdsStreamRelay.textReleu), sau None pentru orice alta referinta."""
    campuri = str(sref or '').split(':')
    if len(campuri) < 11:
        return None
    cale = campuri[10].replace('%3a', ':').replace('%3A', ':')
    for inceput in ('http://127.0.0.1:', 'http://localhost:'):
        if cale.lower().startswith(inceput):
            rest = cale[len(inceput):].split('/', 1)
            if len(rest) == 2 and rest[0].isdigit() and re.match(r'^1:0:[0-9a-fA-F]+:', rest[1]):
                return rest[1]
    return None


def frontend_releu(sref):
    """Firul principal. Pentru un canal redat prin Stream Relay: frontendInfo() al tunerului care il tine (al sesiunii
    8001 de la care releul ia fluxul). Canalul redat e un flux, fara tuner al lui: enigma2 da 0 la semnal si calitate.
    None pentru orice alt serviciu."""
    tinta = ref_releu(sref)
    return frontend_sesiune(tinta) if tinta else None


def frontend_serviciu(service):
    """Firul principal. frontendInfo() de citit pentru un serviciu redat (Sources.FrontendStatus / FrontendInfo, temele
    din afara): la Stream Relay al tunerului care tine canalul, altfel al serviciului."""
    if service is None:
        return None
    try:
        from enigma import iServiceInformation
        info = service.info()
        fe = frontend_releu(info.getInfoString(iServiceInformation.sServiceref)) if info is not None else None
        if fe is not None:
            return fe
    except Exception:
        pass
    return service.frontendInfo()


def refuzuri(ref):
    """Firul principal. Sesiunile purtatorului `ref` refuzate la rand (Server.refuzuri), sau None daca serverul nu
    ruleaza (alte imagini: acolo streamserverul nu spune asa ceva)."""
    s = obtine()
    return s.refuzuri(ref) if s is not None else None


def uita_refuzurile(ref):
    s = obtine()
    if s is not None:
        s.uita_refuzurile(ref)


def tunere():
    """Firul principal. Tunerele sesiunilor serverului (Server.tunere): readucerea antenei (Components/HdsMotorPozitie)
    vede asa tunerul cu motor tinut de releul modulului de acces cand programul televizorului n-are tuner. [] fara
    server."""
    s = obtine()
    return s.tunere() if s is not None else []


def fara_pauza(ref):
    """Firul principal. Pauza canalului `ref` se sterge (Server.fara_pauza): readucerea antenei uita pozitia, iar acordul
    sesiunii urmatoare trimite comanda de motor. False fara server sau fara pauza."""
    s = obtine()
    return s.fara_pauza(ref) if s is not None else False
