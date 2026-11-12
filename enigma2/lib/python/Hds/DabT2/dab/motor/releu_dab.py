# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Releul DAB+ din satelit, pe 127.0.0.1:8898 (Hds/DabT2/profil.py, DAB.port). Facut de hdsatelit.com.
Ruleaza ca proces separat (nice 10), pornit de plugin; niciodata in enigma2.

  python3 releu_dab.py /tmp/hdsdab-feed.json [--port 8898] [--inactiv 10] [--iesi-fara-clienti]

  GET /stare                 JSON: sursa, debit, erori, procesor, memorie
  GET /sunet/<setare>        decodarea sunetului DAB+ al fluxurilor .ts: automat | placa | software (setarea schimbata
                             in ecranul DAB, pe televizor sau in pagina web); se aplica pe loc, cu PMT nou in TS
  GET /dab/<feed>/lista      JSON: posturile (raspunde cand FIC e complet sau dupa cel mult 6 s)
  GET /dab/<feed>/<SID>      audio: LOAS (DAB+) sau MP2 (DAB); SID zecimal (asa scrie buchetul) sau 0x... / hex
  GET /dab/<feed>/<SID>.ts   acelasi sunet intr-un TS cu un singur program (PAT/PMT, PES cu PTS, PCR), pentru redarea
                             prin placa (referinta tip 1 cu cale http): LATM/LOAS pe stream_type 0x11, MP2 pe 0x03;
                             dat in ritmul PCR-ului (RitmPcr, --ritm), nu in rafalele sursei. Pe placile care nu stiu
                             AAC-ul DAB+ (cadre de 960; Broadcom/Vu+) DAB+ se decodeaza aici si pleaca tot ca MP2 (0x03):
                             Hds/DabT2/sunet_software.py; setarea „sunet” din feed sau --sunet automat|placa|software

Memorie: vezi REGULILE din comun/surse.py (demux cel mult 1 MB, nimic mare in /tmp). Releul nu scrie fisiere.
Sursa porneste la primul client si se opreste dupa --inactiv secunde fara clienti; cu --iesi-fara-clienti
procesul iese apoi. Un fir de date (sursa -> EDI/ETI -> FIC -> DAB+) si un fir pentru toti clientii HTTP.
Feed-ul (JSON): id, fel (edi|ts2na|ts2na12|tsniv2ni), pid, ip, port, adapter, demux; optional drum_sectiuni
(filtru|tap), drum_ts (http8001|tap|dvr|fifo), ref_8001 sau purtator {sid, tsid, onid, ns}, port_8001, fifo.
EDI merge pe sectiuni (dovedit). ETI in TS merge implicit pe 8001 cand exista referinta purtatorului, altfel TAP.
Merge pe Python 3 si pe Python 2.7 (imagini vechi, fara al doilea Python): ajutoarele din comun/compat.py."""
from __future__ import division

import json
import os
import struct
import sys
import threading
import time

AICI = os.path.dirname(os.path.abspath(__file__))
# Codul comun (surse.py, releu_http.py, compat.py) se cauta in ordine: in imaginea HDSatelit doua niveluri mai sus
# (Hds/DabT2/dab/motor -> Hds/DabT2); ca plugin in Plugins/SystemPlugins/HdsComun (langa Extensions, apoi calea
# fixa), inaintea directoarelor comun/ de dinainte (un rest ramas de la o instalare veche nu are voie sa fie luat in
# locul lui); in surse (S) comunul e S/comun, gasit prin ultima cale. Un dosar intra numai daca are surse.py.
for _d in (AICI, os.path.dirname(AICI)):
    if os.path.isdir(_d) and _d not in sys.path:
        sys.path.append(_d)
for _d in (os.path.normpath(os.path.join(AICI, '..', '..')),
           os.path.normpath(os.path.join(AICI, '..', '..', '..', 'SystemPlugins', 'HdsComun')),
           '/usr/lib/enigma2/python/Plugins/SystemPlugins/HdsComun',
           os.path.join(os.path.dirname(AICI), 'comun'),
           os.path.normpath(os.path.join(AICI, '..', '..', '..', 'comun'))):
    if os.path.isfile(os.path.join(_d, 'surse.py')) and _d not in sys.path:
        sys.path.append(_d)

import dab_edi                     # noqa: E402
import releu_http as H             # noqa: E402
import surse                       # noqa: E402

if sys.version_info[0] < 3:        # Python 2.7: aceleasi nume ca pe Python 3
    from compat import (monoton as _monoton, ceas_procesor as _ceas_procesor, citeste_fd as _citeste_fd,  # noqa: E402
                        BlockingIOError)
    OSError = EnvironmentError     # noqa: A001  (pe 2.7 IOError si socket.error nu sunt OSError)
else:
    _monoton = time.monotonic
    _ceas_procesor = time.process_time
    _citeste_fd = os.read

# portul cand feed-ul nu are http_port (pornit de mana): acelasi cu profil.DAB.port; releul ruleaza ca proces
# separat, fara pachetul Hds, deci valoarea sta si aici
PORT_IMPLICIT = 8898
CHEIE_SURSA = 'sursa'
ASTEPTARE_LISTA_S = 6.0
CAP_CLIENT = 256 * 1024            # ~20 s de audio la 96 kbit/s; peste atat clientul e prea lent
FELURI = ('edi', 'ts2na', 'ts2na12', 'tsniv2ni')


class Jurnal(object):
    """Pe stderr (plugin il duce in /tmp/hdsdab-releu.err), cu acelasi mesaj cel mult o data la 10 s."""

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
            linie = '%s releu_dab: %s\n' % (time.strftime('%H:%M:%S'), text[:300])
            self.scris += len(linie)
            sys.stderr.write(linie)
            sys.stderr.flush()
        except Exception:
            pass


class DemuxFisier(object):
    """Sursa falsa pentru probe: sectiuni dintr-un fisier (lungime pe 4 octeti + sectiune), in bucla, la debitul
    dat. Aceeasi interfata ca surse.Demux. Nu tine fisierul in memorie."""
    cale = None
    kbit = 1178.0

    def __init__(self, adapter=0, demux=0):
        self.f = open(DemuxFisier.cale, 'rb')
        self.t0 = _monoton()
        self.trimis = 0
        self.rata = DemuxFisier.kbit * 1000 / 8

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
        h = self.f.read(4)
        if len(h) < 4:
            self.f.seek(0)
            h = self.f.read(4)
            if len(h) < 4:
                raise EOFError('fisier gol')
        n = struct.unpack('>I', h)[0]
        b = self.f.read(n)
        self.trimis += len(b)
        return b

    def inchide(self):
        f, self.f = self.f, None
        if f is not None:
            f.close()


GRUPARE_S = 0.1                    # pauza intre rafalele de citiri (vezi CitireGrupata)
PRAG_FLUX = 32 * 1024              # flux (8001, fifo): o citire mai mica decat atat inseamna ca s-a golit soclul


class CitireGrupata(object):
    """Dispozitiv (demux) citit in rafale: se citeste fara asteptare cat timp sunt date, iar cand e gol firul doarme
    GRUPARE_S in loc sa se trezeasca la fiecare sectiune. Un flux EDI de 1,2 Mbit/s vine in ~200 de sectiuni pe
    secunda: citit una cate una inseamna ~200 de treziri, fiecare cu read ratat, exceptie, select si read; in rafale
    raman ~10 treziri pe secunda (masurat pe PC cu Linux, releul ca proces, EDI 1212 kbit/s si un client:
    ~1,2% -> ~0,36% dintr-un nucleu, impreuna cu decodarea mai rapida). Octetii si ordinea lor raman aceiasi. Daca nu
    vine nimic de doua ori la rand, se asteapta in select (fara treziri dese cand fluxul e oprit). Demux-ul tine in
    tampon 1 MB, adica ~7 s de flux la 1,2 Mbit/s."""

    def __init__(self, dev, pauza=GRUPARE_S):
        self.dev = dev
        self.pauza = pauza
        self.goale = 0
        # demux-ul adevarat (fd neblocant): read direct, fara inca un apel Python pe fiecare sectiune; o eroare de
        # citire (EOVERFLOW etc.) urca la fel ca din Demux.citeste
        self._fd = dev.fd if type(dev) is surse.Demux or getattr(dev, 'citire_directa', False) else -1

    def __getattr__(self, nume):                  # buffer, filtru_sectiuni, filtru_pes, fd
        return getattr(self.__dict__['dev'], nume)

    def citeste(self, timeout, marime=65536):
        if self._fd >= 0:
            try:
                b = _citeste_fd(self._fd, marime)
            except BlockingIOError:
                b = None
        else:
            b = self.dev.citeste(0, marime)
        if b is not None:
            self.goale = 0
            return b
        if self.goale >= 2:
            b = self.dev.citeste(timeout, marime)
            if b is not None:
                self.goale = 0
            return b
        self.goale += 1
        time.sleep(self.pauza)
        return None

    def inchide(self):
        self._fd = -1
        self.dev.inchide()


def _fabrica_grupata(Clasa, pauza):
    def fabrica(adapter=0, demux=0):
        return CitireGrupata(Clasa(adapter, demux), pauza)
    return fabrica


def _flux_grupat(blocuri, pauza, prag=PRAG_FLUX):
    """Pentru fluxuri fara granite (soclul 8001, fifo): dupa o citire mica firul doarme `pauza`, ca urmatorul recv sa
    ia deodata tot ce s-a strans (in loc de zeci de bucati mici pe secunda). Peste prag nu se doarme: firul tine pasul
    si la debite mari."""
    dormi = time.sleep
    for b in blocuri:
        yield b
        if len(b) < prag:
            dormi(pauza)


def _generator(sursa):
    """surse._Sursa tine generatorul in _gen; iterarea lui direct scuteste un apel Python pe fiecare citire."""
    g = getattr(sursa, '_gen', None)
    return g if g is not None and (hasattr(g, '__next__') or hasattr(g, 'next')) else sursa     # next: Python 2.7


# ritmul TS-ului (0.7.4, forumul 801 #1562: DAB+ din satelit pe Vu+ Uno4K SE, volum care urca si coboara). Sursa vine in
# rafale (citirea grupata, superframe-ul de 120 ms: masurat pe .114 ~190 ms de plaja); fiecare PES pleaca deci cand
# ceasul monoton ajunge la el. Atentie: enigma2 NU da decodorului PID-ul PCR pentru fluxurile releului (servicedvb.cpp,
# setSyncPCR(-1) cand m_is_pvr), deci decodorul nu se potriveste dupa PCR; ritmul conteaza numai prin cat de lin vin
# datele si cat raman in rezerva playerului (eHdsFluxHttp, 400 ms de ceas). Masurat pe .114 (aceeasi sursa):
# plaja sosire-PTS 424 ms in 0.7.3, 192 ms numai cu trezirea reparata, 20 ms cu ritmul; pe .122 (HiSilicon) nicio
# golire la niciunul (lucru-sesiune/paralel-1111b/STADIU-F-DAB-SATELIT.md: acolo si proba care hotaraste daca rezerva
# de pornire ajunge la decodor sau se pierde inainte de filtrul sunetului).
RITM_REZERVA_S = 0.4               # cat sta un PES in releu dupa sosire (absoarbe rafalele); cat rezerva playerului
RITM_FEREASTRA_S = 10.0            # rezerva cea mai mica se urmareste pe ferestre de atat
RITM_PRAG_S = 0.1                  # rezerva cea mai mica din fereastra peste atat: ancora coboara incet
RITM_COBORARE = 5e-5               # cu cel mult 50 ppm (0,5 ms la 10 s): decodorul nu vede salt de ceas
RITM_REANCORARE_S = 1.0            # peste atat (pauza a sursei, apoi totul deodata): ancora coboara la rezerva deodata
RITM_SALT_90K = 10 * 90000         # PTS mutat cu mai mult de 10 s: alt flux, se ancoreaza din nou
# decodarea software a DAB+ (sunet_software): peste atatea AU, daca faad2 strica mai mult de jumatate, postul trece pe
# decodorul placii (AudioSpecificConfig gresit sau flux pe care faad2 nu-l stie)
RENUNTA_DUPA_AU = 50


class RitmPcr(object):
    """Momentul (ceasul monoton) la care pleaca fiecare PES al unui TS, dupa PTS-ul lui (PCR = PTS - 0,5 s, deci
    acelasi ritm): moment = ancora + PTS / 90 kHz. Logica pura, fara fire; ceasul se poate da (probe).

    - Primul PES pleaca pe loc: porneste ceasul rezervei din player (hdsfluxhttp.cpp, implicit 400 ms). Ancora se pune
      cu `rezerva` dupa sosirea lui, deci urmatoarele PES pleaca la rezerva + distanta lor in timp; cand rezerva
      playerului e cel putin cat a releului, decodorul vede PCR-urile la distante egale chiar de la primul.
    - Un PES venit dupa momentul lui (sursa a intarziat, un superframe pierdut, ceasul sursei mai lent): ancora urca
      cat sa fie la timp si PES-ul pleaca pe loc. Nimic nu se arunca.
    - Ca intarzierea sa nu creasca (ceasul sursei mai rapid, rezerva ramasa mare dupa o pauza a sursei): la fiecare
      fereastra, daca cea mai mica rezerva vazuta e peste RITM_PRAG_S, ancora coboara cu cel mult RITM_COBORARE pe
      secunda; daca e peste RITM_REANCORARE_S, coboara deodata pana la `rezerva`.
    - Pe aceeasi cheie momentele nu scad (ordinea pachetelor TS)."""

    __slots__ = ('rezerva', 'ceas', 'ancora', '_pts', '_desf', '_ultim', '_capat', '_min',
                 'pes', 'urcari', 'coborari', 'reancorari', 'rezerva_min')

    def __init__(self, rezerva=RITM_REZERVA_S, ceas=None):
        self.rezerva = float(rezerva)
        self.ceas = ceas or _monoton
        self.ancora = None
        self._pts = None                 # ultimul PTS (33 de biti)
        self._desf = 0                   # PTS desfasurat (fara intoarcerea la 0 dupa 2^33), fata de primul
        self._ultim = None               # ultimul moment dat
        self._capat = 0.0                # sfarsitul ferestrei
        self._min = None                 # cea mai mica rezerva din fereastra
        self.pes = self.urcari = self.coborari = self.reancorari = 0
        self.rezerva_min = None          # cea mai mica rezerva din ultima fereastra incheiata (pentru /stare)

    def moment(self, pts):
        acum = self.ceas()
        self.pes += 1
        if self._pts is not None:
            d = (pts - self._pts) & dab_edi.TsAudio.MASCA_33
            if d >= 1 << 32:
                d -= 1 << 33
            if -RITM_SALT_90K < d < RITM_SALT_90K:
                self._desf += d
            else:
                self.ancora = None
        self._pts = pts
        if self.ancora is None:
            self._desf = 0
            self.ancora = acum + self.rezerva
            self._capat = acum + RITM_FEREASTRA_S
            self._min = None
            t = acum if self._ultim is None else max(acum, self._ultim)
            self._ultim = t
            return t
        m = self._desf / 90000.0
        sosire = acum - m                # ancora la care PES-ul asta ar pleca exact cand a venit
        if sosire > self.ancora:
            self.ancora = sosire
            self.urcari += 1
        rez = self.ancora - sosire       # cat sta PES-ul in releu
        if self._min is None or rez < self._min:
            self._min = rez
        if acum >= self._capat:
            r = self._min
            self.rezerva_min = r
            if r > RITM_REANCORARE_S:
                self.ancora -= r - self.rezerva
                self.reancorari += 1
            elif r > RITM_PRAG_S:
                self.ancora -= min(r - RITM_PRAG_S, RITM_COBORARE * (acum - self._capat + RITM_FEREASTRA_S))
                self.coborari += 1
            self._capat = acum + RITM_FEREASTRA_S
            self._min = None
        t = self.ancora + m
        if t < self._ultim:
            t = self._ultim
        self._ultim = t
        return t

    def stare(self):
        return {'rezerva_ms': int(self.rezerva * 1000), 'pes': self.pes, 'urcari': self.urcari,
                'coborari': self.coborari, 'reancorari': self.reancorari,
                'rezerva_min_ms': None if self.rezerva_min is None else round(self.rezerva_min * 1000, 1)}


def curata_id(feed_id):
    """La fel ca buchete._curata_id: asa se construieste URL-ul in plugin."""
    return ''.join(ch for ch in str(feed_id or '') if ch.isalnum() or ch in '_-.')[:64]


def sid_din_cale(text):
    t = text.split('.', 1)[0].strip()
    if not t:
        raise ValueError('SID gol')
    if t[:2].lower() == '0x':
        v = int(t, 16)
    elif t.isdigit():
        v = int(t)
    else:
        v = int(t, 16)
    if not 0 < v <= 0xFFFF:
        raise ValueError('SID in afara intervalului')
    return v


class ReleuDab(object):
    def __init__(self, feed, arg, jurnal):
        self.feed = feed
        self.arg = arg
        self.jurnal = jurnal
        self.feed_id = curata_id(feed.get('id'))
        self.fel = str(feed.get('fel') or 'edi')
        self.pid = int(feed.get('pid') or 0)
        self.server = None
        self.ans = dab_edi.Ansamblu()
        self.lungimi = {}
        self.abonamente = ()             # ((sid, cheie), ...) citit de firul de date
        self.chei_active = set()
        self.viata = {}
        self._fir = None
        self._oprire = None
        self._eti = None
        self._lipsa = None
        self.stare_sursa = surse.stare_noua()
        self.dec_edi = None
        self.stare_eti = {}
        self.decodoare = {}
        self.cadre = 0
        self.porniri = 0
        self.opriri = 0
        self.ultima_oprire_sursa = None                  # defect 8: cand si de ce s-a inchis sesiunea 8001
        self.erori = 0
        self.ultima_eroare = ''
        self._debit = (_monoton(), 0, 0.0)
        self.cap_client = int(arg.cap_client * 1024)
        self.ritm_s = max(0.0, float(getattr(arg, 'ritm', RITM_REZERVA_S) or 0))     # 0 = TS-ul pleaca pe loc
        self.ritmuri = {}                                # cheie dabts:<sid> -> RitmPcr (pentru /stare)
        # decodarea sunetului DAB+ (0.7.4): setarea omului, apoi modul hotarat o data pe proces (_mod_sunet)
        self.sunet_setare = str(getattr(arg, 'sunet', None) or feed.get('sunet') or 'automat')
        self.sunet_mod = None                            # 'placa' / 'software', dupa primul post cerut ca .ts
        self.sunet_motiv = ''
        self.transcodoare = {}                           # cheie dabts:<sid> -> sunet_software.Transcodor
        self._sunet_nou = False                          # setarea schimbata prin /sunet/<setare>
        self.Dispozitiv = DemuxFisier if arg.sursa_falsa else None
        if arg.sursa_falsa:
            DemuxFisier.cale = arg.sursa_falsa
            DemuxFisier.kbit = arg.debit_fals

    # ------------------------------------------------------------ HTTP (firul clientilor)
    def handler(self, server, client, cale):
        parti = [p for p in cale.split('/') if p]
        if parti == ['stare']:
            return H.json_raspuns(self.stare())
        if len(parti) == 2 and parti[0] == 'sunet':
            if parti[1] not in ('automat', 'placa', 'software'):
                return H.Raspuns(404, 'setare necunoscuta')
            if parti[1] != self.sunet_setare:
                self.sunet_setare = parti[1]
                self._sunet_nou = True                   # firul de date hotaraste din nou la urmatorul cadru
            return H.json_raspuns(self.stare()['sunet'])
        if len(parti) != 3 or parti[0] != 'dab':
            return H.Raspuns(404, 'cale necunoscuta')
        if parti[1] != self.feed_id:
            return H.Raspuns(404, 'feed necunoscut')
        lipsa = self._verifica_fel()
        if lipsa:
            return H.Raspuns(501, lipsa)
        if parti[2] == 'lista':
            if self.ans.complet():
                return H.json_raspuns(self.lista())

            def lista_gata(expirat):
                if self.ans.complet() or expirat:
                    return H.json_raspuns(self.lista())
                return None
            return H.Asteapta(lista_gata, ASTEPTARE_LISTA_S, (CHEIE_SURSA,))
        try:
            sid = sid_din_cale(parti[2])
        except ValueError:
            return H.Raspuns(404, 'SID gresit')
        ts = parti[2].lower().endswith('.ts')
        cheie = ('dabts:%d' if ts else 'dab:%d') % sid

        def flux_gata(expirat):
            p = self.ans.posturi.get(sid)
            if p is not None and p['subch'] is not None:
                tip = 'video/MP2T' if ts else 'audio/aac' if p['ascty'] == 63 else 'audio/mpeg'
                return H.Flux(cheie, tip, self.cap_client)
            if expirat:
                return H.Raspuns(404, 'postul nu e in ansamblu')
            return None
        return flux_gata(False) or H.Asteapta(flux_gata, ASTEPTARE_LISTA_S, (CHEIE_SURSA,))

    def lista(self):
        posturi = []
        for sid, p in sorted(list(self.ans.posturi.items()), key=lambda x: (x[1]['nume'].lower(), x[0])):
            if not p['nume'] or p['subch'] is None:
                continue
            posturi.append({'sid': sid, 'sid_hex': '%04X' % sid, 'nume': p['nume'],
                            'fel': 'DAB+' if p['ascty'] == 63 else 'DAB', 'subcanal': p['subch'],
                            'kbit': int(round(self.lungimi.get(p['subch'], 0) * 8 / 24))})     # round da float pe 2.7
        return {'feed': self.feed_id, 'ansamblu': self.ans.nume, 'eid': '%04X' % self.ans.eid if self.ans.eid is not None else None,
                'complet': bool(self.ans.complet()), 'posturi': posturi}

    def stare(self):
        s = self.server
        st = dict(self.stare_sursa)
        st.pop('marimi', None)
        edi = None
        if self.dec_edi is not None:
            d = self.dec_edi
            edi = {'af_bune': d.af_bune, 'af_rele': d.af_rele, 'pf_rele': d.pft.rele, 'af_pierdute': d.pft.pierdute}
        return {'releu': 'dab', 'feed': self.feed_id, 'fel': self.fel, 'pid': self.pid,
                'sursa_activa': self._fir is not None, 'porniri': self.porniri, 'opriri': self.opriri,
                'ultima_oprire_sursa': self.ultima_oprire_sursa,
                'cadre': self.cadre, 'debit_kbit': round(self._debit[2], 1), 'octeti': st.get('octeti', 0),
                'sursa': st, 'edi': edi,
                'eti': dict(self.stare_eti) if self.stare_eti else None,
                'au': dict((('%04X' % sid), [d.au_bune, d.au_rele]) for sid, d in list(self.decodoare.items())),
                'ritm': dict((k, r.stare()) for k, r in list(self.ritmuri.items())) or None,
                'sunet': {'setare': self.sunet_setare, 'mod': self.sunet_mod, 'motiv': self.sunet_motiv,
                          'transcodoare': dict((k, t.stare()) for k, t in list(self.transcodoare.items())) or None},
                'ansamblu': self.ans.nume, 'complet': bool(self.ans.complet()), 'posturi': len(self.ans.posturi),
                'clienti': len(s.clienti) if s else 0,
                'abonati': dict((k, len(v)) for k, v in s.abonati.items()) if s else {},
                'http': dict(s.contoare) if s else {}, 'http_cai': dict(getattr(s, 'cereri_pe_cale', {})) if s else {}, 'erori': self.erori, 'ultima_eroare': self.ultima_eroare,
                'cpu_s': round(_ceas_procesor(), 3), 'rss_kb': H.rss_kb(), 'fire': threading.active_count(),
                'lipsa': self._lipsa}

    def _verifica_fel(self):
        if self.fel not in FELURI:
            return 'fel necunoscut: %s' % self.fel
        if self.fel != 'edi' and self._eti is None and self._lipsa is None:
            try:
                import eti                               # lenes: doar pentru ETI in TS
                self._eti = eti
            except Exception as e:
                self._lipsa = 'eti.py lipseste sau nu se incarca: %s' % e
        return self._lipsa if self.fel != 'edi' else None

    def _mod_sunet(self):
        """Cine decodeaza AAC-ul DAB+ al fluxurilor .ts: 'placa' sau 'software' (o data pe proces). Software numai daca
        bibliotecile se incarca si proba de pornire iese; altfel placa, cu motivul in /stare si in jurnal."""
        if self.sunet_mod is None:
            try:
                import sunet_software as ss
                mod, motiv = ss.alege(self.sunet_setare)
                if mod == ss.MOD_SOFTWARE:
                    ok, de_ce = ss.disponibil()
                    if not ok:
                        mod, motiv = ss.MOD_PLACA, '%s; software nu se poate: %s' % (motiv, de_ce)
                        self.jurnal('sunet: raman pe placa, %s' % de_ce)
            except Exception as e:                       # modulul lipsa sau stricat: niciodata fara sunet
                mod, motiv = 'placa', 'sunet_software: %s: %s' % (type(e).__name__, e)
                self.jurnal(motiv)
            self.sunet_mod, self.sunet_motiv = mod, motiv
        return self.sunet_mod

    def _transcodor(self, d):
        import sunet_software as ss
        i = d.info
        asc = ss.asc_dab(i['rata_baza'], i['canale_baza'])
        t = ss.Transcodor(lambda: ss.DecodorAac(asc))
        t.info_sursa = i                                 # DABPlus face alt dict cand postul se reconfigureaza
        return t

    def la_tic(self, acum):
        necesare = self.server.chei_necesare()
        ab = tuple(sorted((int(k.split(':', 1)[1]), k) for k in necesare
                          if k.startswith(('dab:', 'dabts:')) and self.server.are_abonati(k)))
        if ab != self.abonamente:
            self.abonamente = ab
        H.ciclu_viata(self.server, self.chei_active, self._porneste_cheie, self._opreste_cheie,
                      self.arg.inactiv, self.arg.iesi_fara_clienti, self.viata)
        t0, o0, _ = self._debit
        if acum - t0 >= 2.0:
            o = self.stare_sursa.get('octeti', 0)
            self._debit = (acum, o, max(0.0, (o - o0) * 8 / 1000 / (acum - t0)))

    def _porneste_cheie(self, k):
        if self._fir is None:
            self._porneste_sursa()

    def _opreste_cheie(self, k):
        if not (self.chei_active - {k}) and self._fir is not None:
            # defect 8: urma in /stare si in jurnal, ca o redeschidere a sesiunii 8001 sa se poata explica
            s = self.server
            self.ultima_oprire_sursa = {'ora': time.strftime('%H:%M:%S'), 'cheie': k, 'inactiv_s': self.arg.inactiv,
                                        'abonati': sum(len(v) for v in s.abonati.values()) if s else 0,
                                        'porniri': self.porniri}
            self.jurnal('sursa oprita: %s fara clienti de %s s (abonati audio %d, porniri %d)'
                        % (k, self.arg.inactiv, self.ultima_oprire_sursa['abonati'], self.porniri))
        if not (self.chei_active - {k}):
            self._opreste_sursa()

    # ------------------------------------------------------------ sursa (firul de date)
    def _porneste_sursa(self):
        vechi = getattr(self, '_fir_vechi', None)
        if vechi is not None and vechi.is_alive():
            vechi.join(1.0)
        self._oprire = threading.Event()
        self.porniri += 1
        self._fir = threading.Thread(target=self._fir_date, args=(self._oprire,), name='date-dab')
        self._fir.daemon = True                          # pe 2.7 Thread nu primeste daemon in constructor
        self._fir.start()

    def _opreste_sursa(self):
        if self._fir is None:
            return
        self._oprire.set()
        self._fir_vechi = self._fir
        self._fir = None
        self.opriri += 1

    def _deschide(self, oprire):
        st = surse.stare_noua()
        self.stare_sursa = st
        f = self.feed
        ad, dm = int(f.get('adapter') or 0), int(f.get('demux') or 0)
        grupare = float(getattr(self.arg, 'grupare', GRUPARE_S) or 0)
        Dispozitiv = self.Dispozitiv
        if grupare > 0:
            Dispozitiv = _fabrica_grupata(Dispozitiv or surse.Demux, grupare)
        if self.fel == 'edi':
            sct = surse.sectiuni(self.pid, ad, dm, cale=f.get('drum_sectiuni') or 'filtru', oprire=oprire, stare=st,
                                 Dispozitiv=Dispozitiv)
            # generatorul din spatele sursei direct (next() in C, fara metoda __next__ in Python pe fiecare sectiune);
            # sursa ramane pentru close()
            udp = surse.udp_din_mpe(_generator(sct), f.get('ip') or '', int(f.get('port') or 0), stare=st)
            self.dec_edi = dab_edi.DecodorEdi()
            return dab_edi.cadre_eti(udp, self.dec_edi), sct
        eti = self._eti
        drum = self.drum_ts()
        ref = surse.ref_purtator(f) if drum == 'http8001' else f.get('ref')
        st['ref'] = ref
        flux = drum in ('http8001', 'fifo')              # fara granite: se grupeaza la consumator, nu la dispozitiv
        ts = surse.pachete_ts(self.pid, drum, ad, dm, ref=ref, fifo=f.get('fifo'),
                              oprire=oprire, stare=st, Dispozitiv=self.Dispozitiv if flux else Dispozitiv,
                              impacheteaza=False,
                              gazda_8001=str(f.get('gazda_8001') or '127.0.0.1'), port_8001=int(f.get('port_8001') or 8001),
                              termen_8001=float(f.get('termen_8001') or 90.0))
        blocuri = _generator(ts)
        if flux and grupare > 0:
            blocuri = _flux_grupat(blocuri, grupare)
        self.stare_eti = {}
        if self.fel == 'tsniv2ni':
            return eti.cadre_din_tsniv2ni(blocuri, stare=self.stare_eti, pid=self.pid), ts
        return eti.cadre_din_ts2na(blocuri, 12 if self.fel == 'ts2na12' else 0, stare=self.stare_eti, pid=self.pid), ts

    def drum_ts(self):
        """ETI in TS (ts2na, tsniv2ni): drum_ts din feed daca e dat; altfel portul 8001 pe serviciul purtator cand
        feed-ul are referinta (TS intreg, fara pierderi, ca la T2-MI), iar ca rezerva TAP."""
        if self.feed.get('drum_ts'):
            return str(self.feed['drum_ts'])
        if self.Dispozitiv is None and surse.ref_purtator(self.feed):
            return 'http8001'
        return 'tap'

    def _fir_date(self, oprire):
        while not oprire.is_set():
            sursa = None
            try:
                cadre, sursa = self._deschide(oprire)
                self._bucla(cadre, oprire)
                if not oprire.is_set():
                    raise EOFError('sursa s-a terminat')
            except Exception as e:
                if oprire.is_set():
                    break
                self.erori += 1
                self.ultima_eroare = '%s: %s' % (type(e).__name__, e)
                self.jurnal('sursa: %s' % self.ultima_eroare)
                oprire.wait(1.0)
            finally:
                if sursa is not None:
                    try:
                        sursa.close()
                    except Exception:
                        pass

    def _bucla(self, cadre, oprire):
        ans = self.ans
        server = self.server
        publica = server.publica
        self.decodoare = decodoare = {}
        muxere = {}                                      # cheie dabts:<sid> -> TsAudio
        self.ritmuri = ritmuri = {}                      # cheie dabts:<sid> -> RitmPcr, cat traieste TsAudio-ul ei
        for t in list(self.transcodoare.values()):
            t.inchide()
        self.transcodoare = transcodoare = {}            # cheie dabts:<sid> -> Transcodor (DAB+ decodat aici)
        sw = None                                        # DAB+ decodat aici? se hotaraste la primul post cerut ca .ts
        # ritmul cere un server care stie sa dea la un moment dat (releu_http.Server.amana); altfel TS-ul pleaca pe loc
        ritm_s = self.ritm_s if getattr(server, 'amana', False) else 0
        pe_post = ()                                     # ((sid, [chei]), ...) din abonamente
        ab_vechi = None
        schimbari = -1
        n = 0
        for fic, mst in cadre:
            if oprire.is_set():
                return
            if self._sunet_nou:
                # setarea s-a schimbat din ecran: modul se hotaraste din nou; fluxurile .ts trec pe noul fel de sunet
                # la cadrul urmator (TsAudio nou, PMT in versiunea urmatoare)
                self._sunet_nou = False
                self.sunet_mod = None
                sw = (self._mod_sunet() == 'software') if any(c.startswith('dabts:') for _, c in ab_vechi or ()) else None
                for x in decodoare.values():
                    x.cu_brute = bool(sw)
                if not sw:
                    for k in list(transcodoare):
                        transcodoare.pop(k).inchide()
            if fic:
                ans.fic(fic)
                if ans.schimbari != schimbari:
                    schimbari = ans.schimbari
                    server.trezeste()                    # /lista si fluxurile care asteapta afla imediat
            n += 1
            self.cadre += 1
            if n % 42 == 1:
                self.lungimi = dict((k, len(v)) for k, v in mst.items())
            ab = self.abonamente
            if not ab:
                if decodoare:
                    decodoare.clear()
                continue
            if ab is not ab_vechi:
                ab_vechi = ab
                vii = set(sid for sid, _ in ab)
                for sid in [s for s in decodoare if s not in vii]:
                    del decodoare[sid]
                for k in [k for k in muxere if k not in set(c for _, c in ab)]:
                    del muxere[k]
                    ritmuri.pop(k, None)
                    t = transcodoare.pop(k, None)
                    if t is not None:
                        t.inchide()
                grupe = {}
                for sid, cheie in ab:
                    grupe.setdefault(sid, []).append(cheie)
                pe_post = tuple(sorted(grupe.items()))
                if sw is None and any(c.startswith('dabts:') for _, c in ab):
                    sw = self._mod_sunet() == 'software'
                    for d in decodoare.values():          # un post deschis inainte ca LOAS: de acum si AU brute
                        d.cu_brute = sw
            # un post cerut si ca LOAS si ca TS trece o singura data prin decodorul DAB+ (superframe-ul se cauta cadru
            # cu cadru, deci acelasi cadru dat de doua ori l-ar strica)
            for sid, chei in pe_post:
                p = ans.posturi.get(sid)
                if p is None or p['subch'] is None:
                    continue
                v = mst.get(p['subch'])
                if not v:
                    continue
                aac = p['ascty'] == 63
                if aac:
                    d = decodoare.get(sid)
                    if d is None:
                        d = decodoare[sid] = dab_edi.DABPlus()
                        d.cu_brute = bool(sw)                    # AU brute pentru faad2 (numai in modul software)
                    iesire = d.adauga(v)
                    if not iesire:
                        continue
                    brut = iesire[0] if len(iesire) == 1 else b''.join(iesire)
                else:
                    brut = v
                for cheie in chei:
                    if not cheie.startswith('dabts:'):
                        publica(cheie, brut)
                        continue
                    soft = aac and d.cu_brute                    # DAB+ decodat aici, placa primeste MP2
                    m = muxere.get(cheie)
                    if m is None or m.tip != (0x11 if aac and not soft else 0x03):
                        # TS nou: PTS-ul reincepe de la PTS_START, deci si ritmul lui. Pe aceeasi cheie (alt fel de
                        # sunet): PMT cu versiunea urmatoare si contorii de continuitate dusi mai departe
                        vechi = m
                        m = muxere[cheie] = dab_edi.TsAudio(sid, aac and not soft,
                                                            versiune=vechi.versiune + 1 if vechi is not None else 0)
                        if vechi is not None:
                            m.cc = dict(vechi.cc)
                        if ritm_s > 0 and not (vechi is not None and aac and cheie in ritmuri):
                            ritmuri[cheie] = RitmPcr(ritm_s)
                        # DAB+ trecut intre placa si software: PTS-ul merge mai departe (din AU-uri), deci ritmul ramane;
                        # unul nou ar da primul PES pe loc, inaintea celor vechi inca programate (pachete amestecate)
                    r = ritmuri.get(cheie)
                    if soft:
                        # faad2 -> MP2: un PES pe cadru MP2, fiecare la momentul lui (PTS-ul vine din cel al AU-urilor)
                        try:
                            t = transcodoare.get(cheie)
                            if t is None or t.info_sursa is not d.info:  # post nou sau reconfigurat: alt ASC
                                if t is not None:
                                    t.inchide()
                                t = transcodoare[cheie] = self._transcodor(d)
                            pas = 10800 // d.info['au_pe_superframe']
                            for (_, pts), au in zip(dab_edi.cadre_cu_pts(d, iesire), d.brute):
                                for cadru, p_mp2 in t.adauga(au, pts, pas):
                                    if r is None:
                                        publica(cheie, m.pachete(((cadru, p_mp2),)))
                                    else:
                                        publica(cheie, m.pachete(((cadru, p_mp2),)), r.moment(p_mp2))
                            if t.au >= RENUNTA_DUPA_AU and t.au_rele * 2 > t.au:
                                raise ValueError('faad2: %d AU rele din %d (%s)' % (t.au_rele, t.au, t.ultima_eroare))
                        except Exception as e:
                            # plasa: decodarea software nu merge pe postul asta -> placa (niciodata fara sunet); TS-ul
                            # trece pe LOAS de la cadrul urmator, cu PMT nou
                            motiv = '%s: %s' % (type(e).__name__, e)
                            self.jurnal('sunet: trec pe placa, %s' % motiv)
                            self.sunet_mod, self.sunet_motiv = 'placa', 'software oprit: %s' % motiv
                            sw = False
                            for k in list(transcodoare):
                                transcodoare.pop(k).inchide()
                            for x in decodoare.values():
                                x.cu_brute = False
                    elif r is None:
                        publica(cheie, m.pachete(dab_edi.cadre_cu_pts(d, iesire)) if aac else m.cif(v))
                    elif aac:
                        for cadru, pts in dab_edi.cadre_cu_pts(d, iesire):       # un PES pe AU, fiecare la momentul lui
                            publica(cheie, m.pachete(((cadru, pts),)), r.moment(pts))
                    else:
                        b = m.cif(v)
                        publica(cheie, b, r.moment(m.pts))


def citeste_feed(cale):
    with open(cale, 'rb') as f:
        date = json.loads(f.read(1024 * 1024).decode('utf-8'))
    if isinstance(date, dict) and isinstance(date.get('feeduri'), list):
        dab = [x for x in date['feeduri'] if x.get('tip', 'dab') == 'dab']
        if not dab:
            raise ValueError('niciun feed DAB in fisier')
        baza = dict((k, v) for k, v in date.items() if k != 'feeduri')
        baza.update(dab[0])
        date = baza
    if not isinstance(date, dict) or not date.get('id'):
        raise ValueError('feed fara id')
    return date


def main(argv=None):
    H.muta_erorile()
    arg = H.citeste_argumente(sys.argv[1:] if argv is None else argv, {
        '--port': (int, None), '--gazda': (str, '127.0.0.1'), '--inactiv': (float, 10.0),
        '--sursa-falsa': (str, None), '--debit-fals': (float, 1178.0), '--cap-client': (float, CAP_CLIENT / 1024),
        '--grupare': (float, GRUPARE_S), '--ritm': (float, RITM_REZERVA_S), '--sunet': (str, None)},
        ('--iesi-fara-clienti',), ('feed',), 'Releul DAB+ din satelit (hdsatelit.com)')
    jurnal = Jurnal()
    try:
        if hasattr(os, 'nice') and os.nice(0) < 10:
            os.nice(10 - os.nice(0))
    except OSError:
        pass
    feed = citeste_feed(arg.feed)
    port = arg.port if arg.port is not None else int(feed.get('http_port') or PORT_IMPLICIT)
    releu = ReleuDab(feed, arg, jurnal)
    server = H.Server(releu.handler, releu.la_tic, port=port, gazda=arg.gazda, coada_max=2 * 1024 * 1024, jurnal=jurnal)
    releu.server = server
    try:
        sys.stdout.write('ASCULT %d\n' % server.port)
        sys.stdout.flush()
    except Exception:
        pass
    try:
        return server.ruleaza()
    finally:
        releu._opreste_sursa()


if __name__ == '__main__':
    sys.exit(main())
