# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Releul DAB+ din satelit, pe 127.0.0.1:8898 (Hds/DabT2/profil.py, DAB.port). Facut de hdsatelit.com.
Ruleaza ca proces separat (nice 10), pornit de plugin; niciodata in enigma2.

  python3 releu_dab.py /tmp/hdsdab-feed.json [--port 8898] [--inactiv 10] [--iesi-fara-clienti]

  GET /stare                 JSON: sursa, debit, erori, procesor, memorie
  GET /dab/<feed>/lista      JSON: posturile (raspunde cand FIC e complet sau dupa cel mult 6 s)
  GET /dab/<feed>/<SID>      audio: LOAS (DAB+) sau MP2 (DAB); SID zecimal (asa scrie buchetul) sau 0x... / hex
  GET /dab/<feed>/<SID>.ts   acelasi sunet intr-un TS cu un singur program (PAT/PMT, PES cu PTS, PCR), pentru redarea
                             prin placa (referinta tip 1 cu cale http): LATM/LOAS pe stream_type 0x11, MP2 pe 0x03

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
        self.Dispozitiv = DemuxFisier if arg.sursa_falsa else None
        if arg.sursa_falsa:
            DemuxFisier.cale = arg.sursa_falsa
            DemuxFisier.kbit = arg.debit_fals

    # ------------------------------------------------------------ HTTP (firul clientilor)
    def handler(self, server, client, cale):
        parti = [p for p in cale.split('/') if p]
        if parti == ['stare']:
            return H.json_raspuns(self.stare())
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
        pe_post = ()                                     # ((sid, [chei]), ...) din abonamente
        ab_vechi = None
        schimbari = -1
        n = 0
        for fic, mst in cadre:
            if oprire.is_set():
                return
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
                grupe = {}
                for sid, cheie in ab:
                    grupe.setdefault(sid, []).append(cheie)
                pe_post = tuple(sorted(grupe.items()))
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
                    m = muxere.get(cheie)
                    if m is None or m.tip != (0x11 if aac else 0x03):
                        m = muxere[cheie] = dab_edi.TsAudio(sid, aac)
                    publica(cheie, m.pachete(dab_edi.cadre_cu_pts(d, iesire)) if aac else m.cif(v))


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
        '--grupare': (float, GRUPARE_S)},
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
