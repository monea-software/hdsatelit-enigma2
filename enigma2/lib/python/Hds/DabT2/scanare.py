# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""„Scaneaza transponderul curent": detectorul ruleaza in proces separat (nice 10) pe transponderul pe care e
acordat serviciul care ruleaza, iar pluginul doar citeste JSON-ul iesit. Facut de hdsatelit.com.

Nu se foloseste eComponentScan: el scrie in lamedb servicii DVB, iar noi nu avem nevoie de lamedb (serviciile
noastre sunt referinte cu URL). Detectorul citeste doar filtre de sectiuni si pachete pe demux, deci merge cu
serviciul pornit, fara sa ia tunerul.

Ce gaseste detectorul ramane pe receptor prin salveaza_rezultatul (fir de fundal): feed-urile in scanate.json,
posturile citite din FIC in servicii.json, iar buchetul se reface cu ele. Fara posturi un feed nu intra in buchet
(buchete.intrari_noi), deci o scanare care n-ar citi posturile ar lasa buchetul gol.
"""
import json
import os

from . import compat, jurnal, tuner
from .limba import _

# detectorul citeste un PID cu EDI pana are lista posturilor fiecarui ansamblu (cel mult 9 s pe PID, vezi
# detector.TIMP_PID_MPE_S); termenul acopera si pornirea interpretorului pe receptor
TIMP_DETECTOR_S = 25
TERMEN_S = 60
IESIRE_MAX = 1024 * 1024
PROGRES = b'HDS-GASIT '
ERORI_MAX = 4096
ERORI_RANDURI = 12           # ultimele randuri de pe stderr (fara progres), pentru textul brut si jurnal
RAND_MAX = 300               # ... fiecare taiat la atatea caractere
NECITIT_MAX = 2000           # inceputul iesirii care nu s-a putut citi, pentru textul brut


def mesaj_esec():
    """Fraza de pe ecran cand detectorul nu da raspuns (iesire necitita, termen depasit, eroare): ce s-a intamplat si
    ce sa faci. Detaliul tehnic (codul de iesire, termenul) sta separat, in Scanare.detaliu."""
    return _('Scanarea s-a oprit inainte de sfarsit si nu a salvat nimic. Incearca din nou.')

POL = {0: 'H', 1: 'V', 2: 'L', 3: 'R'}
SISTEM = {0: 'DVB-S', 1: 'DVB-S2'}
MODULATIE = {0: 'auto', 1: 'QPSK', 2: '8PSK', 3: 'QAM16', 4: '16APSK', 5: '32APSK'}
PLS = {0: 'root', 1: 'gold', 2: 'combo'}
FEC = {0: 'auto', 1: '1/2', 2: '2/3', 3: '3/4', 4: '5/6', 5: '7/8', 6: '8/9', 7: '3/5', 8: '4/5', 9: '9/10'}


def transponder_curent(sesiune):
    """Transponderul serviciului care ruleaza, in formatul listei. None daca nu e un serviciu de satelit."""
    try:
        s = sesiune.nav.getCurrentService()
        fi = s and s.frontendInfo()
        if not fi:
            return None
        d = fi.getTransponderData(True) or {}
    except Exception:
        jurnal.eroare('scanare', 'transponder_curent')
        return None
    return transponder_din_enigma(d)


def transponder_din_enigma(d):
    d = dict((str(k), v) for k, v in (d or {}).items())
    tip = str(d.get('tuner_type', 'DVB-S'))
    if 'DVB-S' not in tip or not d.get('frequency') or d.get('orbital_position') is None:
        return None
    poz = int(d.get('orbital_position'))
    is_id = d.get('is_id', -1)
    return {
        'id': 'scanat_%d_%d%s' % (poz, int(d['frequency']) // 1000, POL.get(d.get('polarization'), 'H').lower()),
        'pozitie': poz,
        'frecventa': int(d['frequency']),
        'pol': POL.get(d.get('polarization'), 'H'),
        'sr': int(d.get('symbol_rate') or 0),
        'sistem': SISTEM.get(d.get('system'), 'DVB-S'),
        'modulatie': MODULATIE.get(d.get('modulation'), 'QPSK'),
        'fec': FEC.get(d.get('fec_inner'), 'auto'),
        'is_id': is_id if isinstance(is_id, int) and is_id >= 0 else None,
        'pls_cod': d.get('pls_code') if isinstance(is_id, int) and is_id >= 0 else None,
        'pls_mod': PLS.get(d.get('pls_mode'), 'root') if isinstance(is_id, int) and is_id >= 0 else None,
        'feeduri': [],
    }


def citeste_raspuns(text):
    """Obiectul JSON al detectorului din tot ce a venit pe iesire. -> dict sau None.

    Pe stdoutAvail vine numai JSON-ul. Pe dataAvail (rezerva) vin si bucatile de stderr: randurile de progres
    („HDS-GASIT {...}") si, rar, avertismentele interpretorului. Un rand de progres se scoate oriunde ar fi, nu numai
    la inceput de rand: enigma2 citeste stdout cate 2048 de octeti, deci o bucata de stderr poate cadea intre doua
    bucati ale aceluiasi JSON. Obiectul se citeste de la primul rand care incepe cu „{"; ce vine dupa el se ignora."""
    if not text:
        return None
    marcaj = PROGRES.decode('ascii')
    parti = []
    i = 0
    while True:
        j = text.find(marcaj, i)
        if j < 0:
            parti.append(text[i:])
            break
        parti.append(text[i:j])
        k = text.find('\n', j)
        if k < 0:
            break
        i = k + 1
    curat = ''.join(parti)
    if curat.startswith('{'):
        inceput = 0
    else:
        inceput = curat.find('\n{') + 1
        if inceput == 0:
            return None
    try:
        rez, _sfarsit = json.JSONDecoder().raw_decode(curat, inceput)
    except ValueError:
        return None
    return rez if isinstance(rez, dict) else None


class Scanare(object):
    """Porneste detectorul si intoarce feed-urile de tipul pluginului. la_gata(ok, feeduri_sau_mesaj).
    la_progres(dict), optional: fiecare ansamblu gasit, cat detectorul inca lucreaza (randurile HDS-GASIT de pe
    stderr). Dupa sfarsit `raspuns` tine tot raspunsul detectorului (candidatii, programele), pentru textul brut.
    Fara raspuns: `cod` (codul de iesire), `detaliu` (textul tehnic scurt, de aratat sub fraza simpla), `erori_detector`
    (ultimele randuri de pe stderr, fara progres) si `necitit` (inceputul iesirii care nu s-a putut citi)."""

    def __init__(self, profil, cale_plugin):
        self.profil = profil
        self.cale_plugin = cale_plugin
        self._container = None
        self._iesire = []
        self._marime = 0
        self._la_gata = None
        self._la_progres = None
        self._erori = b''
        self._timer = None
        self._conexiuni = []          # manierele legaturilor containerului si ale timerului (semnale-obiect: tinute aici)
        self.raspuns = None
        self.cod = None
        self.detaliu = ''
        self.erori_detector = []
        self.necitit = ''

    def ruleaza(self):
        return self._container is not None

    def cale_detector(self):
        """detector.py sta langa acest modul (codul comun, in imagine sau in pachetul pentru alte imagini). Rezerva:
        asezarile vechi, cu codul comun copiat in plugin (<plugin>/comun, <plugin>/motor)."""
        candidati = [os.path.join(os.path.dirname(os.path.abspath(__file__)), 'detector.py')]
        if self.cale_plugin:
            candidati += [os.path.join(self.cale_plugin, 'comun', 'detector.py'),
                          os.path.join(self.cale_plugin, 'motor', 'detector.py')]
        for c in candidati:
            if os.path.exists(c):
                return c
        return candidati[0]

    def porneste(self, la_gata, la_progres=None):
        if self._container is not None:
            return False
        script = self.cale_detector()
        self._la_gata = la_gata
        self._la_progres = la_progres
        self._iesire, self._marime, self._erori = [], 0, b''
        self.raspuns = None
        self.cod, self.detaliu, self.erori_detector, self.necitit = None, '', [], ''
        try:
            from enigma import eConsoleAppContainer, eTimer
            c = eConsoleAppContainer()
            # JSON-ul vine numai pe stdout. dataAvail primeste in Enigma2 si fiecare bucata de stderr
            # (eConsoleAppContainer::readyErrRead), deci progresul de pe stderr s-ar amesteca in JSON; stdoutAvail
            # are numai stdout. Unde lipseste (imagini vechi), dataAvail, iar citeste_raspuns scoate progresul.
            iesire = getattr(c, 'stdoutAvail', None)
            self._conexiuni.append(compat.conecteaza(c.dataAvail if iesire is None else iesire, self._date))
            self._conexiuni.append(compat.conecteaza(c.appClosed, self._inchis))
            try:
                # teava de erori golita mereu (altfel detectorul se opreste cand e plina); randurile de progres se
                # dau mai departe
                self._conexiuni.append(compat.conecteaza(c.stderrAvail, self._erori_venite))
            except Exception:
                pass
            self._container = c
            # fara `2>/dev/null`: o teava inchisa poate face enigma2 sa astepte blocant procesul (releu_http.muta_erorile)
            comanda = 'exec nice -n 10 %s %s %d %s' % (compat.interpretor_python(), script, TIMP_DETECTOR_S,
                                                       self.profil.tip)
            if c.execute(comanda):
                self._curata()
                return False
            self._timer = eTimer()
            self._conexiuni.append(compat.conecteaza_timer(self._timer, self._termen))
            self._timer.start(TERMEN_S * 1000, True)
            jurnal.noteaza(self.profil.eticheta, 'detector pornit')
            return True
        except Exception:
            jurnal.eroare(self.profil.eticheta, 'pornirea detectorului')
            self._curata()
            return False

    def _date(self, date):
        try:
            if self._marime < IESIRE_MAX:
                self._iesire.append(date)
                self._marime += len(date)
        except Exception:
            pass

    def _erori_venite(self, date):
        """stderr-ul detectorului: randurile „HDS-GASIT {json}" merg la la_progres; celelalte (avertismente, un
        Traceback) raman, ultimele ERORI_RANDURI, pentru textul brut si jurnal cand raspunsul lipseste."""
        try:
            if not isinstance(date, bytes):
                date = str(date).encode('utf-8', 'replace')
            linii = (self._erori + date).split(b'\n')
            self._erori = linii.pop()[-ERORI_MAX:]
            for linie in linii:
                self._rand_eroare(linie)
        except Exception:
            jurnal.eroare(self.profil.eticheta, 'progresul detectorului')

    def _rand_eroare(self, linie):
        if linie.startswith(PROGRES):
            if self._la_progres is None:
                return
            try:
                x = json.loads(linie[len(PROGRES):].decode('utf-8', 'replace'))
            except ValueError:
                return
            if isinstance(x, dict) and self._la_progres is not None:
                self._la_progres(x)
            return
        text = linie.decode('utf-8', 'replace').rstrip()
        if text.strip():
            # forma nativa (octeti UTF-8 pe 2.7): randul ajunge si in jurnal, langa texte native
            self.erori_detector.append(compat.text_nativ(text[:RAND_MAX]))
            del self.erori_detector[:-ERORI_RANDURI]

    def _ultimul_rand_eroare(self):
        """Randul de stderr ramas fara sfarsit de rand cand procesul s-a oprit."""
        rest, self._erori = self._erori, b''
        if rest:
            try:
                self._rand_eroare(rest)
            except Exception:
                pass

    def _jurnal_erori(self):
        return '; stderr: %s' % ' | '.join(self.erori_detector[-3:]) if self.erori_detector else ''

    def _curata(self):
        c, self._container = self._container, None
        compat.deconecteaza_toate(self._conexiuni)
        if self._timer is not None:
            try:
                self._timer.stop()
            except Exception:
                pass
            self._timer = None
        return c

    def opreste(self):
        c = self._curata()
        if c is not None:
            try:
                if c.running():
                    c.kill()
            except Exception:
                pass
        self._la_gata = None
        self._la_progres = None

    def _termen(self):
        cb = self._la_gata
        self.opreste()
        self.detaliu = _('Detectorul nu s-a oprit la timp (%d s).') % TERMEN_S
        jurnal.noteaza(self.profil.eticheta, 'detectorul oprit la termen (%d s)%s' % (TERMEN_S, self._jurnal_erori()))
        if cb:
            cb(False, mesaj_esec())

    def _inchis(self, cod=None):
        cb = self._la_gata
        chemat = [False]

        def raspunde(ok, rez):
            chemat[0] = True
            if cb:
                cb(ok, rez)
        try:
            self._curata()
            self._la_gata = None
            self._la_progres = None
            self.cod = cod
            self._ultimul_rand_eroare()
            bucati = [b if isinstance(b, bytes) else (b if compat.e_text(b) else str(b)).encode('utf-8', 'replace')
                      for b in self._iesire]
            self._iesire = []
            text = b''.join(bucati).decode('utf-8', 'replace')
            rez = citeste_raspuns(text)
            if rez is None:
                self.necitit = text[:NECITIT_MAX]
                self.detaliu = _('Detectorul s-a oprit cu codul %s, fara un raspuns care sa se poata citi.') % cod
                jurnal.noteaza(self.profil.eticheta, 'raspunsul detectorului nu se poate citi (cod %s, %d caractere): '
                               '%r%s' % (cod, len(text), text[:160], self._jurnal_erori()))
                raspunde(False, mesaj_esec())
                return
            self.raspuns = rez
            feeduri = [f for f in rez.get('feeduri') or [] if isinstance(f, dict) and f.get('tip') == self.profil.tip]
            jurnal.noteaza(self.profil.eticheta, 'detector gata: %d feed-uri, %d posturi'
                           % (len(feeduri), sum(len(f.get('posturi') or []) for f in feeduri)))
            raspunde(True, feeduri)
        except Exception:
            jurnal.eroare(self.profil.eticheta, 'rezultatul detectorului')
            # fara raspuns ecranul scanarii ar ramane pe „Caut..."
            if not chemat[0]:
                try:
                    self.detaliu = self.detaliu or _('Raspunsul detectorului nu s-a putut prelucra (detalii in jurnal).')
                    raspunde(False, mesaj_esec())
                except Exception:
                    jurnal.eroare(self.profil.eticheta, 'raspunsul catre ecran')


def text_transponder(tp):
    return tuner.text_transponder(tp)


# ---------------------------------------------------------------- ce ramane dupa scanare
FELURI_PRIN_8001 = ('t2mi', 'abertis', 'ts2na', 'ts2na12', 'tsniv2ni')     # T2-MI, TS in PID si ETI: pe HiSilicon numai prin portul 8001


def cauta_in_lista(lista, tp, feed):
    """Feed-ul detectorului in lista unita (liste.incarca): transponderul dupa pozitie, frecventa (+-2 MHz),
    polarizare si flux, feed-ul dupa cheie (PID + IP/port la EDI, PID + PLP la T2). -> (feed, transponder) sau
    (None, None). Id-ul poate diferi de al detectorului: manual.json are prioritate fata de scanate.json."""
    from . import liste
    try:
        cheie = liste._cheie_feed(feed)
    except (KeyError, TypeError):
        return None, None
    for t in (lista or {}).get('transpondere', []):
        if not liste._acelasi_transponder(t, tp):
            continue
        for f in t.get('feeduri', []):
            try:
                if liste._cheie_feed(f) == cheie:
                    return f, t
            except (KeyError, TypeError):
                continue
    return None, None


def feed_candidat_t2(candidat, tp):
    """Un PID cu T2MI_descriptor pe care detectorul nu l-a putut confirma (pe receptor T2-MI vine numai prin 8001):
    feed de incercat prin releu, cu PLP 0 (cel folosit de toate multiplexurile din lista)."""
    pid = candidat.get('pid')
    if not isinstance(pid, int) or not 0 < pid < 8191:
        return None
    return {'id': 'det_t2_%d_%d_%04x' % (int(tp.get('pozitie') or 0), int(tp.get('frecventa') or 0) // 1000, pid),
            'tip': 't2', 'fel': 't2mi', 'pid': pid, 'plp': 0,
            'nume': candidat.get('serviciu') or 'DVB-T2 PID %d' % pid, 'confirmat': True}


def salveaza_rezultatul(profil, tp, feeduri, candidati=None, director_enigma2=None, incorporat=None,
                        cu_nedecodabile=False, invatari_max=4):
    """Blocant: se cheama din fir de fundal, sub zavorul scrierilor (pornire._sub_zavor). Ce a gasit detectorul
    ramane pe receptor si dupa repornire: feed-urile in scanate.json, posturile citite din FIC in servicii.json (sub
    id-ul din lista unita), apoi buchetul („DAB+ din satelit" / „DVB-T2 din satelit") si indexul lui. Reincarcarea
    buchetelor in enigma2 ramane pentru firul principal.

    Feed-urile care se asculta numai prin portul 8001 (T2-MI, ETI) si cele gasite fara posturi nu au inca o lista de
    posturi: intra in `de_invatat`, pe care apelantul le trece pe rand prin releu (Controlor.invata), afara de cele
    pe care servicii.json le stie deja (invatate la o scanare de dinainte sau cand au cantat): acelea intra direct
    in `gasite`, fara inca un drum prin releu. Pe un transponder fara niciun feed al tipului in lista, PID-urile cu
    T2MI_descriptor (candidatii) se pun in scanate.json ca feed-uri noi (`adaugat`: se scot daca invatarea nu merge).
    -> {'gasite': [(feed, tp, posturi)], 'de_invatat': [(feed, tp, adaugat)], 'noi': feed-uri noi in scanate.json,
        'buchet': buchete.reface(...)}"""
    from . import buchete, liste
    feeduri = [f for f in feeduri or [] if isinstance(f, dict) and f.get('tip') == profil.tip]
    lista = liste.incarca(profil.tip, profil.director, incorporat)
    are_in_lista = False
    for t in lista.get('transpondere', []):
        if liste._acelasi_transponder(t, tp) and any(f.get('tip') == profil.tip for f in t.get('feeduri', [])):
            are_in_lista = True
    noi = []
    if profil.tip == 't2' and not are_in_lista:
        vazute = set(f.get('pid') for f in feeduri)
        for c in candidati or []:
            if isinstance(c, dict) and c.get('tip') == 't2' and c.get('pid') not in vazute:
                f = feed_candidat_t2(c, tp)
                if f is not None:
                    vazute.add(f['pid'])
                    noi.append(f)
    n_noi = 0
    if feeduri or noi:
        n_noi = liste.adauga_scanat(profil.tip, tp, feeduri + noi, profil.director)
        lista = liste.incarca(profil.tip, profil.director, incorporat)
    memorate = buchete.citeste_servicii(profil)

    def stiute(feed):
        return (memorate.get(buchete._curata_id(feed.get('id'))) or {}).get('servicii') or []

    gasite, de_invatat, chei = [], [], set()
    for f in feeduri + noi:
        feed_u, tp_u = cauta_in_lista(lista, tp, f)
        if feed_u is None:
            continue
        chei.add(liste._cheie_feed(feed_u))
        posturi = [p for p in f.get('posturi') or [] if isinstance(p, dict)]
        if posturi and f not in noi:
            buchete.salveaza_servicii(profil, buchete._curata_id(feed_u.get('id')), posturi)
            gasite.append((feed_u, tp_u, posturi))
        elif stiute(feed_u):
            gasite.append((feed_u, tp_u, stiute(feed_u)))
        else:
            de_invatat.append((feed_u, tp_u, f in noi))
    # feed-urile listei de pe acest transponder care vin numai prin 8001: detectorul nu le poate vedea pe receptor
    for t in lista.get('transpondere', []):
        if not liste._acelasi_transponder(t, tp):
            continue
        for f in sorted(t.get('feeduri', []), key=lambda x: x.get('stare_verificare') != 'merge'):
            if f.get('tip') != profil.tip or str(f.get('fel')) not in FELURI_PRIN_8001:
                continue
            if f.get('stare_verificare') == liste.STARE_NEDECODABIL or liste._cheie_feed(f) in chei:
                continue
            chei.add(liste._cheie_feed(f))
            if stiute(f):
                gasite.append((f, t, stiute(f)))
            else:
                de_invatat.append((f, t, False))
    # un buchet gol nu se face la o scanare fara rezultat (ar aparea in lista de canale ca un dosar gol); unul care
    # exista se reface oricum (intrarile feed-urilor disparute ies)
    rez_b = {'schimbat': False, 'intrari': 0, 'feeduri': 0}
    if gasite or os.path.exists(os.path.join(director_enigma2 or buchete.DIRECTOR_ENIGMA2, profil.buchet)):
        pentru_buchet = lista if cu_nedecodabile else liste.fara_nedecodabile(lista)
        rez_b = buchete.reface(profil, pentru_buchet, director_enigma2, reincarca=False)
    return {'gasite': gasite, 'de_invatat': de_invatat[:invatari_max], 'noi': n_noi, 'buchet': rez_b}
