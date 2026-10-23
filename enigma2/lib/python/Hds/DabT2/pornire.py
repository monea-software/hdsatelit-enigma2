# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Pornirea la zap: tunerul si releul merg doar cat e ascultat / vizionat un serviciu al nostru.
Facut de hdsatelit.com.

Legatura cu enigma2 (Navigation.py, punctele de extensie ale zap-ului si ale inregistrarii):
  playService: pnav.stopService() -> streamrelay -> serviceHook -> Navigation.playServiceExtensions -> pnav.playService
  Extensia primeste (nav, playref, event, infobar) si intoarce (playref, asincron).
  - serviciu al nostru, nepregatit: pornim acordul si releul si intoarcem (playref, True); enigma2 NU mai
    porneste playerul. Cand releul are date, chemam nav.playService(ref, forceRestart=True); a doua oara
    extensia vede „pregatit" si intoarce (playref, False), iar playerul porneste pe un releu care raspunde.
    Fara asta, sursa http a serviciului (eHdsFluxHttp in imagine, sursa bazei pe alte imagini, souphttpsrc la 4097)
    s-ar conecta la un port inchis si serviciul ar cadea.
  - serviciu strain: oprim releul si eliberam tunerul SINCRON, inainte ca enigma2 sa aloce tunerul pentru el.
  recordService: Navigation.recordServiceExtensions ruleaza inainte de pnav.recordService. La o inregistrare
  adevarata (simulate=False) cedam tunerul acolo, altfel alocarea ar cadea.

Imagini fara Navigation.playServiceExtensions (multe imagini mai vechi): se lucreaza pe evenimentele serviciului. La evEnd al unui serviciu de-al nostru se elibereaza
tot, sincron (evEnd vine din stopService, inainte ca serviciul nou sa ceara tunerul); la evStart pe o
referinta de-a noastra se pregateste acordul si releul, apoi playerul se reporneste cand releul are date.
Plasa pentru opriri fara zap (stop, standby, alt plugin care iese primul din bucla extensiilor): un eTimer la
2 s, activ doar cat tinem ceva, verifica referinta care ruleaza; 10 s pe altceva = oprim tot.

FIRUL (reparatia dupa un blocaj cu zap cerut din alt fir): extensiile de mai sus pot fi chemate de enigma2 din orice fir care a
chemat Navigation.playService (puntea 1.12 o facea din fir twisted). Din alt fir decat cel principal NU se atinge
nimic din enigma2 si nici starea controlorului: extensia de zap intoarce (playref, True) daca serviciul e al nostru
sau daca tinem ceva, iar toata munca se muta in firul principal prin fir.programeaza; acolo se reface zap-ul cu
nav.playService(forceRestart=True), care cheama din nou extensia, de data asta in firul bun. Un serviciu strain
pornit din alt fir cat tineam tunerul poate astepta o clipa (tunerul se elibereaza abia in firul principal).
Scrierile pe disc (lamedb, buchete, servicii) si citirile de frontend se fac in fire de fundal; in firul principal
raman apelurile enigma2 (reloadServicelist, reloadBouquets, ferestre), care nu pot pleca de acolo.

PORTUL 8001 (T2-MI si ETI, reparatia din 0.1.3): pe Viper 4K V20 fiecare sesiune 8001 pierde ~4 MB vmalloc in driver si
dupa ~45 de sesiuni decodorul video nu mai porneste pana la repornirea completa. De aceea:
  - zap intre canalele aceluiasi feed: releul (si sesiunea lui 8001) ramane pornit, playerul se muta pe alt SID;
  - o sesiune NOUA porneste abia dupa ce utilizatorul sta INTARZIERE_8001_MS pe canal (CH+ tinut apasat nu deschide
    sesiuni pentru fiecare canal trecut); pana atunci releul vechi ramane „tinut";
  - la plecarea de pe canalele noastre spre ceva ce nu cere tunerul (stop, standby, fisier, flux din retea, alt canal
    de pe acelasi transponder) releul se tine inca TINERE_8001_S; o intoarcere in acest timp nu deschide sesiune noua.
    Spre un canal care cere tunerul (alt transponder) totul se elibereaza sincron, ca inainte;
  - fara date: releul se reconecteaza singur la 8001 (cu limita de sesiuni); pluginul nu mai reporneste releul, doar
    renunta dupa FARA_DATE_8001_S. Un releu agatat (nu raspunde la /stare) se reporneste ca inainte.

PLECAREA DE PE 8001 SPRE UN CANAL CARE CERE TUNERUL (reparatia din 0.1.4: un canal de satelit pornit dupa T2 a
ramas fara tuner 200 s, al doilea zap a mers): releul si t2mi_decap se opresc sincron in extensia de zap, dar capatul
8001 al streamserverului se inchide abia cand bucla principala enigma2 prelucreaza inchiderea socketului, adica dupa ce
playService a alocat deja (fara succes) tunerul pentru serviciul nou. De aceea:
  - daca streamserverul mai are un client pe purtatorul nostru (eStreamServer.getConnectedClients, altfel conexiunile
    portului 8001 din /proc/net/tcp), extensia intoarce (playref, True) si un eTimer la ELIBERARE_PAS_MS verifica, fara
    asteptare in firul principal, cand clientul a plecat (doua citiri la rand), cel mult ELIBERARE_MAX_S; apoi
    nav.playService(forceRestart=True) porneste canalul (a doua trecere prin extensie nu mai tine nimic);
  - plasa, pe toate imaginile (si pe cele fara extensii de zap): la VERIFICARE_TUNER_S dupa plecare, daca serviciul
    curent este tot cel ales, se uita la tuner si la imagine. Cat antena inca se roteste (isRotorMoving), verificarea
    se amana cu VERIFICARE_PAS_S, cel mult pana la VERIFICARE_MAX_S de la plecare: imaginea si lock-ul lipsesc firesc
    in timpul rotirii. Fara tuner (frontendInfo fara tuner_number), sau cu tuner dar fara imagine pe un canal TV
    (PID video stiut, decodorul fara marimea imaginii), se da O SINGURA DATA stopService + playService, cu jurnal.
    Daca nici dupa el canalul nu are tuner, serviciul se opreste (Navigation il uita, deci OK pe acelasi canal in lista
    sau un zap din web il porneste) si apare mesajul, cu numele canalului deasupra. Cu tuner dar tot fara imagine nu se
    mai face nimic: ecranul negru (Components/HdsEcranNegru) spune de ce (criptat, fara semnal). Nimic la plecarea
    spre alt feed al nostru, spre un flux din retea sau spre alt canal de pe acelasi transponder.
  - dupa „Caută posturile din flux”, starea repunerii canalului de dinainte (repunere: asteapta, pornit, fara_imagine,
    nepornit) o citeste si pagina web /dabt2, cu acelasi text ca pe televizor.
"""
import json
import os
import sys
import threading
import time

from . import buchete, compat, coordonator, fir, fundal, jurnal, marcaj, proces, receptie, sesiuni8001, tuner
from . import profil as profil_mod
from .limba import _

# Duratele si termenele merg pe ceasul monoton (compat.monoton): nu sare cand ora sistemului se potriveste din retea
# dupa pornire. time.time() ramane numai pentru ora adevarata (marcajul de pe disc, receptie.json, repunerea din /dabt2).
_monoton = compat.monoton

PAS_ASTEPTARE_MS = 700
TERMEN_RELEU_S = 40
PAZA_MS = 2000
ABATERI_MAX = 5              # 10 s pe alt serviciu = oprim
REINCERCARI_DATE = 3
LINISTE_RESETARE_S = 60
PRIMELE_DATE_S = 90         # T2: cat asteptam primii octeti (acordul si rotirea le face streamserver-ul)
ID_POPUP = 'hdsdabt2'
TINERE_8001_S = 20          # releul si sesiunea 8001 se tin atat dupa plecarea de pe canalele noastre
INTARZIERE_8001_MS = 1500   # o sesiune 8001 noua porneste abia dupa atata timp pe canal
FARA_DATE_8001_S = 45       # 8001: fara octeti atat timp (releul viu, reconectandu-se singur) -> renuntare
PAZA_STARE_S = 5            # /stare cel mult o data la 5 s
INACTIV_RELEU_S = 30        # releul tine sursa atat fara clienti (acopera tinerea)
ELIBERARE_PAS_MS = 100      # plecarea de pe 8001: cat de des se intreaba daca streamserverul a eliberat purtatorul
ELIBERARE_MAX_S = 3.0       # ... si cel mult cat timp, apoi canalul porneste oricum (plasa de mai jos il reia)
ELIBERARE_FARA_API_S = 0.5  # nici eStreamServer, nici /proc/net/tcp: o pauza fixa, cat sa ruleze bucla principala
VERIFICARE_TUNER_S = 9      # dupa plecarea de pe 8001: serviciul nou are tuner si imagine? daca nu, un zap din nou
VERIFICARE_PAS_S = 3        # cat antena inca se roteste, verificarea se amana cu atat...
VERIFICARE_MAX_S = 60       # ... dar cel mult atat de la plecare
# T2: playerul porneste cand releul raspunde, inainte de date (antena se poate roti). enigma2 cauta tabelul PAT al
# fluxului cel mult PAT_TERMEN_S (eDVBPATSpec, lib/dvb/specs.h), apoi renunta. La RELUARE_DUPA_S de la pornirea
# playerului, cu datele curgand, serviciul fara tabelul programului (sPMTPID) se porneste o data din nou
PAT_TERMEN_S = 20
RELUARE_DUPA_S = PAT_TERMEN_S + 2
REFUZURI_8001_MAX = 2       # sesiuni 8001 refuzate la rand (tuner ocupat) cat nu a venit niciun octet = mesaj pe loc


def _sub_zavor(functie, *argumente):
    """Scrierile din fundal (servicii.json, buchet, lamedb) una cate una. Zavorul sta in coordonatorul comun: lamedb
    e scris de ambele pluginuri, iar fiecare are copia lui de module."""
    coord = coordonator.obtine()
    zavor = getattr(coord, 'zavor_disc', None)
    if zavor is None:
        zavor = coord.zavor_disc = threading.Lock()
    with zavor:
        return functie(*argumente)


def _ref_text(ref):
    try:
        return ref.toString()
    except Exception:
        return str(ref) if ref is not None else ''


def _ref_dupa_text(vechi, text):
    """Referinta noua din text, de acelasi fel cu cea primita: eServiceReference in enigma2 (numele vine din text,
    ca la toString), textul insusi cand s-a primit un text sau enigma lipseste (probele de pe PC)."""
    if compat.e_text(vechi):
        return text
    try:
        from enigma import eServiceReference
    except ImportError:
        return text
    return eServiceReference(text)


def aceeasi_ref(a, b):
    """Doua referinte (sir sau eServiceReference) ale aceluiasi serviciu? Pe cheie, nu pe text: fara nume, fara ':' la
    sfarsit, %3A = %3a, litere mari = mici (altfel un zap in acelasi feed era tratat ca plecare). None sau
    gol e egal doar cu None sau gol."""
    ta, tb = _ref_text(a) if a is not None else '', _ref_text(b) if b is not None else ''
    if not ta.strip() or not tb.strip():
        return not ta.strip() and not tb.strip()
    return buchete.cheie_ref(ta).rstrip(':').lower() == buchete.cheie_ref(tb).rstrip(':').lower()


def _hex(v):
    try:
        return int(v, 16)
    except (TypeError, ValueError):
        return None


def cere_tunerul(text, ref_purtator):
    """Serviciul `text` are nevoie de tunerul de satelit (altul decat transponderul purtatorului nostru)?
    Nu: nimic (stop), fisier sau flux din retea (cale in referinta / URL), alt tip decat 1 (4097, 5001, 5002),
    sau acelasi transponder ca purtatorul (TSID, ONID, namespace egale: streamserver-ul imparte canalul).
    Da, in rest (inclusiv cand nu se poate citi referinta): la dubiu tunerul se da. Functie pura."""
    t = str(text or '')
    if not t.strip():
        return False
    if '%3a//' in t.lower() or '://' in t:
        return False
    parti = t.split(':')
    if len(parti) < 10:
        return True
    tip = _hex(parti[0]) if parti[0].isdigit() else None
    if tip is None:
        return True
    if int(parti[0]) != 1:
        return False
    if len(parti) > 10 and parti[10].strip().startswith('/'):
        return False                           # inregistrare de pe disc
    p = str(ref_purtator or '').split(':')
    if len(p) < 7:
        return True
    acelasi = all(_hex(parti[i]) is not None and _hex(parti[i]) == _hex(p[i]) for i in (4, 5, 6))
    return not acelasi


def _sesiuni_server_local(ref):
    """Imaginea HDSatelit: sesiunile serverului local 8001 (server8001.py, acelasi proces) care inca tin sau pot lua
    tunerul pentru purtatorul `ref`. None in afara imaginii (modulul lipseste) sau cu serverul oprit."""
    try:
        from . import server8001
    except ImportError:
        return None
    try:
        return server8001.sesiuni_deschise(ref)
    except Exception:
        return None


def _nume_serviciu(ref):
    """Numele de afisat al unui serviciu (lista enigma2, apoi numele din referinta), fara caracterele de evidentiere
    din numele DVB. '' daca nu se afla."""
    nume = ''
    try:
        from enigma import eServiceCenter
        info = eServiceCenter.getInstance().info(ref)
        nume = info.getName(ref) if info is not None else ''
    except Exception:
        nume = ''
    if not nume:
        text = _ref_text(ref)
        nume = text.split(':', 10)[10].split(':', 1)[-1] if text.count(':') > 10 else ''
    if isinstance(nume, bytes):
        nume = nume.decode('utf-8', 'replace')
    return compat.text_nativ(u''.join(c for c in nume if c not in u'\x86\x87').strip())


def _inchide_popup_acord():
    """Fereastra de eroare a pornirii canalului (Screens/InfoBarGenerics.py, id ZapError)."""
    try:
        from Tools.Notifications import RemovePopup
        RemovePopup('ZapError')
    except Exception:
        pass


class Controlor(object):

    def __init__(self, profil, cale_plugin):
        self.profil = profil
        self.nume = profil.nume
        self.et = profil.eticheta
        self.cale_plugin = cale_plugin
        self.sesiune = None
        self.coord = coordonator.obtine()
        self.tuner = tuner.Tuner(self.et)
        self.releu = proces.Supraveghetor(self.et, self._releu_repornit, self._releu_renunta)
        self.fundal = fundal.Fundal(self.et)
        self.fundal_disc = fundal.Fundal(self.et + '-disc')   # scrieri pe disc; nu se opreste la zap
        self.zapuri_din_alt_fir = 0
        self.stare = 'oprit'          # oprit / pregatire / canta
        self.mod = None               # zap / invata
        self.feed = None
        self.tp = None
        self.ref_asteptat = None
        self._playref = None
        self._releu_gata = False
        self._termen = 0
        self._timer_asteptare = None
        self._timer_paza = None
        self._paza_abateri = 0
        self._la_invatat = None
        self._ref_inainte = None
        self._invata_prin_8001 = False   # invatarea curenta trece prin 8001 (repunerea asteapta eliberarea)
        self._lista = None
        self._lista_semn = None
        self.ultima_stare_releu = {}
        self.mesaj = None
        self.zapuri = 0
        self._extensii = False
        self._servicii_cerute = False
        self._asteapta_prime_date_pana = 0.0
        self.rotire = False
        self._in_repornire = False
        self._ultimii_octeti = None
        self._date_la = 0.0
        self._ultimele_utile = None   # contorul datelor care chiar ies din releu (T2 octeti iesiti, DAB cadre)
        self._utile_de_la = 0.0
        self._utile_la = 0.0
        self._reincercari_date = 0
        self._flux_de_la = 0.0
        self._protectie = None
        self._ultimul_strain = None
        self._marcaj_la = None
        self._timer_protectie = None
        self._boot = marcaj.boot_id()
        self._receptie_la = 0.0
        self._receptie_scrisa = False
        self._servicii_cache = {}
        self._ref_purtator = None
        self._amanat = None           # (feed, tp, playref, text): zap pe un feed 8001 nou, pornit dupa intarziere
        self._timer_amanat = None
        self._timer_tinere = None
        self._tinut_pana = 0.0
        self._stare_la = 0.0
        self.amanari = 0              # cate zapuri pe un feed 8001 nou au trecut prin intarziere (probe, jurnal)
        self.tineri = 0
        self._eliberare = None        # zap strain amanat pana streamserverul elibereaza purtatorul (dict)
        self._timer_eliberare = None
        self._verificare = None       # dupa plecarea de pe 8001: serviciul nou are tuner? (dict)
        self._timer_verificare = None
        self.zapuri_dupa_eliberare = 0
        self.rezapuri = 0             # zapuri date din nou pe un serviciu ramas fara tuner (probe, jurnal)
        self._player_la = 0.0         # cand a pornit playerul pe un serviciu al nostru (T2: reluarea dupa date tarzii)
        self._reluat_dupa_date = False
        self.reluari_dupa_date = 0    # probe, jurnal
        self._fara_imagine_notat = False  # randul „fara imagine” al pornirii de acum a playerului e scris
        self._a_curs = False          # a venit macar un octet de la releu de la pornirea postului
        self._nota_pornire = False    # nota „Pornesc ...” sta pe ecran pana la primele date (T2)
        self.repunere = None          # dupa „Caută posturile din flux”: canalul de dinainte (pentru /dabt2), vezi _noteaza_repunerea
        self._semnal_purtator = None  # 8001: semnalul frontend-ului purtatorului, citit in fundal (receptie.json)
        self._semnal_la = 0.0
        self._frontend_purtator = None  # (cheia transponderului, slot, calea frontend-ului)
        self._fundal_semnal = None
        # manierele legaturilor timerelor, pe nume (compat.conecteaza_timer). Cu semnale-obiect legatura traieste
        # doar cat e tinut manierul; timerele raman eTimer simple in atributele _timer_*.
        self._legaturi = {}

    def _leaga(self, nume, timer, functie):
        """Leaga functia la timer si tine manierul sub `nume` (un timer nou cu acelasi nume il inlocuieste)."""
        vechi = self._legaturi.pop(nume, None)
        compat.deconecteaza(vechi)
        self._legaturi[nume] = compat.conecteaza_timer(timer, functie)

    # ------------------------------------------------------------ instalarea in enigma2
    def instaleaza(self, sesiune):
        fir.marcheaza_principal()
        fir.porneste_plasa()
        self.sesiune = sesiune
        self.coord.inregistreaza_controlor(self.nume, self)
        self.fundal_disc.lanseaza(self._curata_orfani, None)
        try:
            self._verifica_marcajul()
        except Exception:
            jurnal.eroare(self.et, 'marcajul de pornire la sesiune')
        zap = self._eticheta(lambda nav, playref, *rest: self.extensie_zap(nav, playref, *rest))
        inreg = self._eticheta(lambda nav, ref, *rest: self.extensie_inregistrare(nav, ref, *rest))
        ev = self._eticheta(lambda e: self._eveniment(e))
        try:
            from Navigation import Navigation
            self._pune_in_lista(Navigation.playServiceExtensions, zap)
            self._pune_in_lista(Navigation.recordServiceExtensions, inreg)
            self._extensii = True
            jurnal.noteaza(self.et, 'extensiile de zap si inregistrare puse')
        except Exception:
            jurnal.noteaza(self.et, 'imaginea nu are extensii de zap; merge doar paza la 5 s')
        try:
            self._pune_in_lista(sesiune.nav.event, ev)
        except Exception:
            jurnal.eroare(self.et, 'nav.event')

    def _eticheta(self, functie):
        """Functiile puse in listele enigma2 poarta numele pluginului, ca o reincarcare sa o scoata pe cea veche."""
        functie._hds_nume = self.nume
        return functie

    def _pune_in_lista(self, lista, functie):
        for f in list(lista):
            if getattr(f, '_hds_nume', None) == self.nume:
                lista.remove(f)
        lista.append(functie)

    def dezinstaleaza(self):
        self.opreste('dezinstalare')
        self._anuleaza_eliberarea()
        self._anuleaza_verificarea()
        try:
            from Navigation import Navigation
            liste_ = [Navigation.playServiceExtensions, Navigation.recordServiceExtensions]
            if self.sesiune is not None:
                liste_.append(self.sesiune.nav.event)
            for lista in liste_:
                for f in list(lista):
                    if getattr(f, '_hds_nume', None) == self.nume:
                        lista.remove(f)
        except Exception:
            pass

    def _curata_orfani(self):
        """Un releu ramas dintr-o enigma2 cazuta ar tine portul. Se cauta dupa numele scriptului in /proc."""
        tinte = [('motor/%s' % self.profil.releu).encode()]
        if self.profil.tip == 't2':
            tinte.append(b'/bin/t2mi_decap')      # binarul serveste singur fluxul; ramas orfan ar tine 8889 si 8001
        try:
            for pid in os.listdir('/proc'):
                if not pid.isdigit():
                    continue
                try:
                    with open('/proc/%s/cmdline' % pid, 'rb') as f:
                        linie = f.read(1024)
                except (IOError, OSError):
                    continue
                if any(t in linie for t in tinte) and int(pid) != os.getpid():
                    try:
                        os.kill(int(pid), 15)
                        jurnal.noteaza(self.et, 'releu orfan oprit, pid %s' % pid)
                    except OSError:
                        pass
        except OSError:
            pass

    # ------------------------------------------------------------ lista de feed-uri, tinuta in memorie
    def _semn_lista(self):
        semn = []
        for c in (os.path.join(self.profil.director, n) for n in ('manual.json', 'scanate.json', 'frecvente.json')):
            try:
                semn.append(os.stat(c).st_mtime)
            except OSError:
                semn.append(None)
        return tuple(semn)

    @staticmethod
    def _arata_nedecodabile():
        """Setarea „Arata si feed-urile care nu se decodeaza" (implicit nu)."""
        try:
            from . import captura
            return bool(captura.configureaza().nedecodabile.value)
        except Exception:
            return False

    def lista(self, forteaza=False):
        arata = self._arata_nedecodabile()
        semn = self._semn_lista() + (arata,)
        if forteaza or self._lista is None or semn != self._lista_semn:
            try:
                from . import liste
                incorporat = os.path.join(self.cale_plugin, 'date', 'frecvente.json')
                self._lista = liste.incarca(self.profil.tip, self.profil.director, incorporat)
                if not arata:
                    self._lista = liste.fara_nedecodabile(self._lista)
            except Exception:
                jurnal.eroare(self.et, 'incarcarea listei')
                self._lista = {'transpondere': []}
            self._lista_semn = semn
        return self._lista

    def cauta_feed(self, feed_id):
        for tp in self.lista().get('transpondere', []):
            for f in tp.get('feeduri', []):
                if buchete._curata_id(f.get('id')) == feed_id:
                    return f, tp
        return None, None

    def feeduri_active(self, plus=None):
        """T2: feed-urile care au nevoie de purtator in lamedb: cele invatate (servicii.json), cel care ruleaza
        acum si `plus` (cel care porneste). Restul listei nu intra in lamedb-ul utilizatorului."""
        active = set(k for k in buchete.citeste_servicii(self.profil) if k)
        if self.feed is not None and self.stare != 'oprit':
            active.add(buchete._curata_id(self.feed.get('id')))
        if plus is not None:
            active.add(buchete._curata_id(plus.get('id')))
        return active

    def reface_buchete(self):
        # sub acelasi zavor ca scrierile din fundal (_scrie_servicii, purtatorul): altfel doi scriitori pe acelasi
        # lamedb.hds-tmp pot lasa lamedb trunchiat
        return _sub_zavor(self._reface_buchete)

    def reface_in_fundal(self):
        """Dupa o lista noua (descarcarea zilnica): lista citita din nou, buchetul si purtatorii scrisi in fundal, sub
        zavorul scrierilor; reincarcarile enigma2 vin in firul principal (_servicii_scrise), numai daca s-a schimbat
        ceva."""
        lista = self.lista(forteaza=True)
        active = self.feeduri_active()

        def scrie():
            rez = {'buchete': bool(buchete.reface(self.profil, lista, reincarca=False).get('schimbat'))}
            from . import lamedb
            rez['lamedb'] = bool(lamedb.actualizeaza(lista, reincarca=False, active=active,
                                                     tip=self.profil.tip).get('schimbat'))
            return rez
        self.fundal_disc.lanseaza(_sub_zavor, self._servicii_scrise, scrie)

    def _reface_buchete(self):
        rez = buchete.reface(self.profil, self.lista())
        # purtatorii din lamedb: T2-MI (HdsT2mi) sau ETI in TS (HdsDab: ts2na, ts2na12, tsniv2ni)
        from . import lamedb
        rez['lamedb'] = lamedb.actualizeaza(self.lista(), active=self.feeduri_active(), tip=self.profil.tip)
        return rez

    def _prin_8001(self, feed=None):
        """Datele vin prin portul 8001 al enigma2 (serviciu purtator in lamedb, tunerul il ia streamserver-ul):
        T2-MI mereu; DAB doar pentru ETI in TS. EDI (sectiuni MPE) tine singur tunerul (canal brut)."""
        if not self.profil.tine_tuner:
            return True
        feed = self.feed if feed is None else feed
        return bool(feed) and str(feed.get('fel') or '') in profil_mod.FELURI_ETI

    def _tine_tuner(self, feed=None):
        return not self._prin_8001(feed)

    # ------------------------------------------------------------ intrebari
    def activ(self):
        return self.stare == 'canta'

    def ocupat(self):
        return self.stare != 'oprit'

    def context(self):
        """Pentru captura: ce canta, pe ce transponder, cu ce semnal."""
        rez = {'plugin': self.nume, 'tip': self.profil.tip, 'stare': self.stare}
        if self.feed:
            rez['feed'] = dict((k, v) for k, v in self.feed.items() if k != 'sursa')
        if self.tp:
            rez['transponder'] = dict((k, v) for k, v in self.tp.items() if k not in ('feeduri', 'sursa'))
        if self._tine_tuner():
            rez['semnal'] = self.tuner.semnal()
        elif self.tp:
            # T2: tunerul e al streamserver-ului; frontend-ul de satelit pentru pozitia feed-ului se citeste in
            # fundal de captura (ioctl, nu in firul principal)
            rez['frontend_slot'] = tuner.alege_slot(tuner.parametri(self.tp)['orbital_position'])[0]
        rez['releu'] = self.ultima_stare_releu
        rez['latime_video'] = self.latime_video()
        return rez

    # ------------------------------------------------------------ extensiile enigma2
    def extensie_zap(self, nav, playref, *rest):
        try:
            if not fir.in_principal():
                return self._zap_din_alt_fir(nav, playref)
            return self._extensie_zap(nav, playref)
        except Exception:
            jurnal.eroare(self.et, 'extensia de zap')
            return playref, False

    def _zap_din_alt_fir(self, nav, playref):
        """Extensia chemata din alt fir: doar citiri de atribute Python, nimic din enigma2, nicio asteptare."""
        text = _ref_text(playref)
        al_nostru = buchete.desparte_ref(self.profil, text) is not None
        tine_ceva = self.stare != 'oprit' or self.tuner.canal is not None or self.releu._container is not None
        if not al_nostru and not tine_ceva:
            return playref, False
        self.zapuri_din_alt_fir += 1
        jurnal.noteaza(self.et, 'zap cerut din alt fir (%s): il mut in firul principal' % text[:80])
        fir.programeaza(self._zap_amanat, nav, playref, text)
        return playref, True

    def _zap_amanat(self, nav, playref, text):
        """In firul principal: zap-ul cerut din alt fir, refacut prin enigma2 ca sa treaca iar prin extensie."""
        curent = _ref_text(nav.getCurrentlyPlayingServiceReference())
        if not aceeasi_ref(curent, text):
            jurnal.noteaza(self.et, 'zap-ul din alt fir e depasit (acum ruleaza %s)' % curent[:80])
            return
        if buchete.desparte_ref(self.profil, text) is None and self.stare != 'oprit':
            if self.mod == 'invata':
                self._ref_inainte = None
                tinea_8001 = self._tine_8001()
                self._esec(self._text_cautare_oprita())
                if self._dupa_plecarea_de_pe_8001(nav, playref, text, tinea_8001):
                    return
            else:
                tinea_8001 = self._tine_8001()
                self.opreste('zap pe alt serviciu (cerut din alt fir)')
                if self._dupa_plecarea_de_pe_8001(nav, playref, text, tinea_8001):
                    return                # canalul porneste din timer, dupa eliberarea purtatorului
        nav.playService(playref, checkParentalControl=False, forceRestart=True)

    def _extensie_zap(self, nav, playref):
        text = _ref_text(playref)
        reparat = buchete.repara_cale_decodata(text)
        if reparat is not None and buchete.al_nostru(self.profil, reparat):
            # zap cu referinta decodata o data in plus (de pilda un sRef cu „%3a” pus intr-o adresa web fara sa fie
            # scris „%253a”): enigma2 ar lua calea „http” si playerul n-ar avea flux. Se reda in forma buna.
            jurnal.noteaza(self.et, 'referinta cu adresa decodata (%s), redata in forma buna' % text[:100])
            playref, text = _ref_dupa_text(playref, reparat), reparat
        nou = buchete.ref_curenta(self.profil, text)
        if nou is not None:
            # post al nostru scris cu un port vechi sau, la DAB, in alta forma a sunetului (favorite, ultimul
            # serviciu, un buchet nerescris): se reda in forma de acum. Inlocuit aici, inaintea oricarei comparatii,
            # ca marcajul, paza si pornirea amanata sa vada aceeasi referinta; Navigation porneste referinta intoarsa
            # si o tine ca serviciul curent.
            jurnal.noteaza(self.et, 'referinta veche, redata pe %d (tipul %s)' % (self.profil.port, nou.split(':', 1)[0]))
            playref, text = _ref_dupa_text(playref, nou), nou
        parti = buchete.desparte_ref(self.profil, text)
        protectie, self._protectie = self._protectie, None      # doar primul zap dupa pornirea sesiunii
        if (protectie is not None and parti is not None and buchete.cheie_ref(text) == protectie['cheie']
                and marcaj.compat.monoton() < protectie['pana']):
            return self._refuza_pornirea_automata(nav, playref, text, protectie)
        if self._verificare is not None and not aceeasi_ref(self._verificare.get('text'), text):
            self._anuleaza_verificarea()          # utilizatorul a ales altceva: verificarea tunerului nu mai are rost
        if parti is None:
            if not buchete.al_hds(text):
                self._ultimul_strain = text
            self._anuleaza_amanat()
            if self._eliberare is not None:
                if cere_tunerul(text, self._ref_purtator):
                    # alt canal de satelit cat inca asteptam eliberarea purtatorului: il pornim pe acesta, dupa ea
                    # (si in locul canalului de dinainte de invatare, daca acela astepta)
                    self._eliberare.update(nav=nav, playref=playref, text=text, repunere=False)
                    if self._verificare is None:
                        self._arma_verificarea(text)
                    return playref, True
                self._anuleaza_eliberarea()
            if self.stare != 'oprit':
                if self.mod == 'invata':
                    self._ref_inainte = None      # utilizatorul a ales alt serviciu: nu il mai repunem
                    tinea_8001 = self._tine_8001()
                    self._esec(self._text_cautare_oprita())
                    if self._dupa_plecarea_de_pe_8001(nav, playref, text, tinea_8001):
                        return playref, True
                elif self._poate_tine(text):
                    self._tine('zap pe un serviciu care nu cere tunerul', TINERE_8001_S)
                else:
                    tinea_8001 = self._tine_8001()
                    self.opreste('zap pe alt serviciu')
                    if self._dupa_plecarea_de_pe_8001(nav, playref, text, tinea_8001):
                        return playref, True
            return playref, False
        self._anuleaza_eliberarea()
        if self.mod == 'invata':
            self._ref_inainte = None
            self._esec(self._text_cautare_oprita())
        self._anuleaza_amanat()
        self.zapuri += 1
        feed_id = parti[0]
        feed, tp = self.cauta_feed(feed_id)
        if feed is None:
            self._popup(_('Feed-ul %s nu mai e in lista. Refa buchetele.') % feed_id)
            return playref, False
        if tuner.multistream_neprins(tp):
            # fara is_id / pls in nucleu acordul ar da alt flux: mesajul limitei in loc de esecul general
            jurnal.noteaza(self.et, 'zap refuzat: %s cere multistream' % feed_id)
            self._popup(tuner.text_multistream())
            return playref, True
        if self.feed is None or self.feed.get('id') != feed.get('id'):
            self._reincercari_date = 0
        self._scrie_marcaj(text)
        if self._pregatit_pentru(feed, tp):
            # acelasi feed (si din starea „tinut"): releul si sesiunea 8001 raman, playerul trece pe alt SID
            self._opreste_tinerea()
            self.stare = 'canta'
            self.mod = 'zap'
            jurnal.noteaza(self.et, 'zap in acelasi feed, playerul pe %s' % text[:100])
            self.ref_asteptat = text
            self._playref = playref
            self._paza_abateri = 0
            self._player_la = _monoton()
            self._fara_imagine_notat = False
            # bara citeste receptie.json cel mult o data la 2 s: scris inaintea playerului, il gaseste la primul
            # eveniment al serviciului nou (altfel ar ramane pe „Flux IP” cu datele programului de dinainte)
            self._scrie_receptie(fortat=True)
            self._porneste_paza()
            return playref, False
        if self._prin_8001(feed) and self._sesiune_noua(feed):
            self._amana(feed, tp, playref, text)
            return playref, True
        self._opreste_tinerea()
        self._pregateste(feed, tp, playref, 'zap')
        return playref, True

    # ------------------------------------------------------------ 8001: intarzierea pornirii si tinerea sesiunii
    def _sesiune_noua(self, feed):
        """Porneste o sesiune 8001 noua? Nu, daca releul aceluiasi feed ruleaza (in orice stare)."""
        return not (self.feed is not None and self.feed.get('id') == feed.get('id') and self.releu.ruleaza())

    def _amana(self, feed, tp, playref, text):
        """Zap pe un feed 8001 fara releu pornit: releul porneste abia dupa INTARZIERE_8001_MS pe canal. Releul de acum
        (alt feed) se tine intre timp, ca o intoarcere rapida sa nu deschida sesiune noua."""
        if self.stare in ('canta', 'pregatire') and self.mod == 'zap':
            if self.releu.ruleaza() and self._prin_8001():
                self._tine('trecere pe alt feed', TINERE_8001_S)
            else:
                self.opreste('trecere pe alt feed')
        self._amanat = (feed, tp, playref, text)
        self.amanari += 1
        if self._timer_amanat is None:
            from enigma import eTimer
            self._timer_amanat = eTimer()
            self._leaga('amanat', self._timer_amanat, self._amanat_expirat)
        self._timer_amanat.start(INTARZIERE_8001_MS, True)

    def _anuleaza_amanat(self):
        if self._amanat is not None:
            self._amanat = None
            self._opreste_timer(self._timer_amanat)

    def _amanat_expirat(self):
        try:
            a, self._amanat = self._amanat, None
            if a is None or self.sesiune is None:
                return
            feed, tp, playref, text = a
            curent = _ref_text(self.sesiune.nav.getCurrentlyPlayingServiceReference())
            if not aceeasi_ref(curent, text):
                # utilizatorul a plecat fara zap prin extensie (stop, standby): releul tinut expira singur
                jurnal.noteaza(self.et, 'zap-ul amanat e depasit (acum %s)' % curent[:80])
                return
            self._opreste_tinerea()
            self._pregateste(feed, tp, playref, 'zap')
        except Exception:
            jurnal.eroare(self.et, 'pornirea amanata')

    def _poate_tine(self, text_nou):
        """Releul 8001 se poate tine dupa plecare daca serviciul nou nu cere tunerul nostru."""
        if self.mod != 'zap' or self.stare not in ('canta', 'tinut') or not self._prin_8001():
            return False
        if not self.releu.ruleaza():
            return False
        return not cere_tunerul(text_nou, self._ref_purtator)

    def _tine(self, motiv, secunde):
        if self.stare == 'tinut':
            return                       # termenul nu se prelungeste la fiecare zap
        jurnal.noteaza(self.et, 'tin releul si sesiunea 8001 inca %d s (%s)' % (secunde, motiv))
        self.tineri += 1
        self._nota_pornire = False
        self.stare = 'tinut'
        self.ref_asteptat = None
        self._paza_abateri = 0
        self._sterge_marcaj('plecare de pe canal')
        if self._receptie_scrisa:
            self._receptie_scrisa = False
            receptie.sterge()
        self._opreste_timer(self._timer_asteptare)
        self._opreste_timer(self._timer_paza)
        self.fundal.opreste()
        fundal.inchide_conexiunile(self.profil.port_control)   # paza nu mai cere /stare: fara socket lasat deschis
        self._ascunde()
        self._tinut_pana = _monoton() + secunde
        if self._timer_tinere is None:
            from enigma import eTimer
            self._timer_tinere = eTimer()
            self._leaga('tinere', self._timer_tinere, self._tinere_expirata)
        self._timer_tinere.start(int(secunde * 1000), True)

    def _opreste_tinerea(self):
        self._opreste_timer(self._timer_tinere)
        self._tinut_pana = 0.0

    def _tinere_expirata(self):
        try:
            if self.stare == 'tinut':
                self.opreste('tinerea sesiunii 8001 a expirat')
        except Exception:
            jurnal.eroare(self.et, 'tinerea sesiunii')

    # ------------------------------------------------------------ 8001: plecarea spre un canal care cere tunerul
    def _tine_8001(self):
        """Tinem acum o sesiune (sau un releu care o poate deschide) pe portul 8001?"""
        return self._prin_8001() and self.releu.ruleaza()

    def _dupa_plecarea_de_pe_8001(self, nav, playref, text, tinea_8001):
        """Chemat imediat dupa opreste(), in firul principal. -> True daca pornirea canalului se amana pana cand
        streamserverul elibereaza purtatorul (atunci extensia intoarce asincron)."""
        if not tinea_8001 or not cere_tunerul(text, self._ref_purtator):
            return False
        self._arma_verificarea(text)
        clienti = self._clienti_purtator()
        if clienti == 0:
            return False                  # streamserverul a eliberat deja purtatorul
        acum = _monoton()
        self._eliberare = {'nav': nav, 'playref': playref, 'text': text, 'de_la': acum,
                           'pana': acum + ELIBERARE_MAX_S, 'libere': 0, 'fara_api': clienti is None}
        jurnal.noteaza(self.et, 'astept ca streamserverul sa elibereze purtatorul (%s) inainte de %s'
                       % ('fara lista de clienti' if clienti is None else '%d clienti' % clienti, text[:80]))
        if self._timer_eliberare is None:
            from enigma import eTimer
            self._timer_eliberare = eTimer()
            self._leaga('eliberare', self._timer_eliberare, self._pas_eliberare)
        self._timer_eliberare.start(ELIBERARE_PAS_MS, False)
        return True

    def _clienti_purtator(self):
        """Cati clienti ai streamserverului enigma2 mai sunt pe purtatorul nostru. None = nu se poate afla.
        Doar citiri fara asteptare: in imaginea HDSatelit sesiunile serverului local (server8001.py, acelasi proces),
        altfel lista din enigma2 sau, pe imaginile fara ea, /proc/net/tcp (fisier mic)."""
        n = _sesiuni_server_local(self._ref_purtator)
        if n is not None:
            return n
        try:
            from enigma import eStreamServer
            lista = eStreamServer.getInstance().getConnectedClients()
        except Exception:
            lista = None
        if isinstance(lista, (list, tuple)):
            cheie = buchete.cheie_ref(self._ref_purtator).upper().rstrip(':') if self._ref_purtator else ''
            n = 0
            for client in lista:
                try:
                    ref = str(client[1])
                except Exception:
                    ref = ''
                if not cheie or buchete.cheie_ref(ref).upper().rstrip(':').startswith(cheie):
                    n += 1
            return n
        return sesiuni8001.conexiuni_8001()

    def _pas_eliberare(self):
        try:
            e = self._eliberare
            if e is None:
                self._opreste_timer(self._timer_eliberare)
                return
            curent = _ref_text(e['nav'].getCurrentlyPlayingServiceReference())
            # repunerea canalului de dinainte de invatare: in timpul asteptarii nu ruleaza nimic (invatarea a oprit
            # serviciul); orice alt serviciu pornit intre timp (din web, fara extensie) o face depasita
            liber = e.get('repunere') and not curent.strip()
            if not liber and not aceeasi_ref(curent, e['text']):
                jurnal.noteaza(self.et, 'pornirea amanata pana la eliberarea purtatorului e depasita (acum %s)'
                               % curent[:80])
                self._anuleaza_eliberarea()
                return
            acum = _monoton()
            if e['fara_api']:
                gata = acum - e['de_la'] >= ELIBERARE_FARA_API_S
            else:
                clienti = self._clienti_purtator()
                e['libere'] = e['libere'] + 1 if not clienti else 0
                gata = e['libere'] >= 2
            if not gata and acum < e['pana']:
                return
            self._anuleaza_eliberarea()
            self.zapuri_dupa_eliberare += 1
            jurnal.noteaza(self.et, '%s dupa %.1f s: pornesc %s' % (
                'purtatorul eliberat' if gata else 'purtatorul tot tinut la termen', acum - e['de_la'], e['text'][:80]))
            e['nav'].playService(e['playref'], checkParentalControl=False, forceRestart=True)
        except Exception:
            self._eliberare = None
            self._opreste_timer(self._timer_eliberare)
            jurnal.eroare(self.et, 'pornirea dupa eliberarea purtatorului')

    def _anuleaza_eliberarea(self):
        if self._eliberare is not None:
            self._eliberare = None
            self._opreste_timer(self._timer_eliberare)

    def _arma_verificarea(self, text, repunere=False):
        """text None: imagine fara extensii de zap; serviciul nou se afla la verificare. repunere: canalul de dinainte
        de „Caută posturile din flux” (rezultatul ajunge si in /dabt2)."""
        if not repunere:
            self._noteaza_repunerea(self._verificare, 'depasit')   # alt canal decat cel repus: nu mai e urmarit
        try:
            self._verificare = {'text': text, 'purtator': self._ref_purtator, 'rezap': False, 'la': _monoton(),
                                'repunere': repunere}
            if self._timer_verificare is None:
                from enigma import eTimer
                self._timer_verificare = eTimer()
                self._leaga('verificare', self._timer_verificare, self._verifica_tunerul)
            self._timer_verificare.start(int(VERIFICARE_TUNER_S * 1000), True)
        except Exception:
            self._verificare = None
            jurnal.eroare(self.et, 'verificarea tunerului dupa 8001')

    def _anuleaza_verificarea(self):
        if self._verificare is not None:
            self._noteaza_repunerea(self._verificare, 'depasit')
            self._verificare = None
            self._opreste_timer(self._timer_verificare)

    def _tunerul_serviciului(self):
        """Numarul tunerului folosit de serviciul curent: >= 0, -1 fara tuner, None daca imaginea nu spune.
        Datele frontend-ului tinute de enigma2 (getFrontendData), fara citire din placa."""
        try:
            s = self.sesiune.nav.getCurrentService()
        except Exception:
            return None
        if s is None:
            return -1
        try:
            fe = s.frontendInfo()
        except Exception:
            return None
        if not fe:
            return -1
        citit, date = False, None
        for nume in ('getFrontendData', 'getAll'):
            f = getattr(fe, nume, None)
            if f is None:
                continue
            try:
                date = f() if nume == 'getFrontendData' else f(True)
                citit = True
                break
            except Exception:
                continue
        if not citit:
            return None
        if not date:
            return -1
        try:
            nr = date.get('tuner_number')
            if nr is None:
                return 0 if date.get('tuner_type') else -1
            return int(nr)
        except Exception:
            return None

    def _imaginea_serviciului(self):
        """Serviciul curent da imagine? True: decodorul are marimea imaginii; False: canal TV (PID video din PMT sau din
        lamedb) fara imagine; None: fara PID video (radio, PMT inca necitit pe un canal necunoscut) sau nu se poate
        afla. Numai citiri ale info-ului tinut de enigma2, fara fisiere."""
        try:
            from enigma import iServiceInformation
            s = self.sesiune.nav.getCurrentService()
            info = s and s.info()
            if not info:
                return None
            if int(info.getInfo(iServiceInformation.sVideoPID)) <= 0:
                return None
            return int(info.getInfo(iServiceInformation.sVideoWidth)) > 0
        except Exception:
            return None

    def _noteaza_repunerea(self, v, stare):
        """Rezultatul repunerii canalului de dinainte de „Caută posturile din flux”, pentru /dabt2 (dabt2_web), cu textul de pe
        televizor. stare: asteapta, pornit, fara_imagine, nepornit, depasit (s-a ales alt canal)."""
        if not v or not v.get('repunere') or self.repunere is None:
            return
        nume = self.repunere.get('nume') or ''
        texte = {
            'asteapta': _('Pornesc din nou canalul de dinainte (%s)...'),
            'pornit': _('Canalul de dinainte (%s) a pornit din nou.'),
            'fara_imagine': _('Canalul de dinainte (%s) a pornit, dar nu da imagine.'),
            'nepornit': _('Canalul de dinainte (%s) nu a pornit: tunerul e inca ocupat. Alege-l din nou.'),
        }
        if stare == 'depasit':
            self.repunere = None
            return
        self.repunere.update(stare=stare, mesaj=texte[stare] % nume, la=time.time())
        self.repunere['la_mono'] = _monoton()     # varsta rezultatului in /dabt2; `la` ramane ora de perete

    def _verifica_tunerul(self):
        try:
            v = self._verificare
            if v is None or self.sesiune is None:
                return
            nav = self.sesiune.nav
            ref = nav.getCurrentlyPlayingServiceReference()
            curent = _ref_text(ref)
            if v['text'] is None:
                if not cere_tunerul(curent, v['purtator']):
                    self._verificare = None
                    return
                v['text'] = curent
            elif not aceeasi_ref(curent, v['text']):
                self._verificare = None
                self._noteaza_repunerea(v, 'depasit')
                return
            nr = self._tunerul_serviciului()
            if nr is None:
                jurnal.noteaza(self.et, 'dupa plecarea de pe 8001: imaginea nu spune tunerul serviciului, nu fac nimic')
                self._verificare = None
                self._noteaza_repunerea(v, 'pornit')
                return
            if nr >= 0 and self._rotorul_se_misca() and _monoton() - v['la'] < VERIFICARE_MAX_S:
                # antena inca se roteste spre satelitul canalului: imaginea nu are cum sa vina inca
                self._timer_verificare.start(int(VERIFICARE_PAS_S * 1000), True)
                return
            imagine = self._imaginea_serviciului() if nr >= 0 else None
            if nr >= 0 and imagine is not False:
                if v['rezap']:
                    jurnal.noteaza(self.et, 'dupa zap-ul dat din nou, %s are tunerul %d' % (curent[:80], nr))
                    _inchide_popup_acord()        # fereastra de tuner ocupat a primei porniri nu mai e adevarata
                self._verificare = None
                self._noteaza_repunerea(v, 'pornit')
                return
            if v['rezap'] and nr < 0:
                jurnal.noteaza(self.et, 'tot fara tuner si dupa zap-ul dat din nou (%s); opresc serviciul, ca alegerea '
                               'lui din nou sa-l porneasca' % curent[:80])
                self._verificare = None
                nav.stopService()             # Navigation uita serviciul: OK pe acelasi canal (lista, web) il porneste
                self._mesaj_canal(ref, _('Canalul nu a pornit: tunerul e inca ocupat. Alege-l din nou.'))
                self._noteaza_repunerea(v, 'nepornit')
                return
            if v['rezap']:
                jurnal.noteaza(self.et, '%s are tunerul %d, dar tot fara imagine dupa zap-ul dat din nou; ecranul negru '
                               'spune de ce' % (curent[:80], nr))
                self._verificare = None
                self._noteaza_repunerea(v, 'fara_imagine')
                return
            v['rezap'] = True
            self.rezapuri += 1
            jurnal.noteaza(self.et, '%s la %.0f s dupa plecarea de pe 8001: %s; dau zap din nou, o singura data'
                           % ('FARA TUNER' if nr < 0 else 'FARA IMAGINE cu tunerul %d' % nr, _monoton() - v['la'],
                              curent[:80]))
            nav.stopService()
            nav.playService(ref)
            if self._verificare is v:
                self._timer_verificare.start(int(VERIFICARE_TUNER_S * 1000), True)
        except Exception:
            v, self._verificare = self._verificare, None
            try:
                self._noteaza_repunerea(v, 'depasit')   # fara rezultat: /dabt2 nu mai asteapta
            except Exception:
                self.repunere = None
            jurnal.eroare(self.et, 'verificarea tunerului dupa 8001')

    # ------------------------------------------------------------ protectia la pornire (marcajul pe disc)
    def _scrie_marcaj(self, text):
        try:
            marcaj.scrie(self.profil.director, text, self._ultimul_strain, time.time(), marcaj.compat.monoton(),
                         self._boot)
            self._marcaj_la = _monoton()          # varsta redarii (_redare_buna); pe disc raman ora si ceasul monoton
        except Exception:
            self._marcaj_la = None
            jurnal.eroare(self.et, 'marcajul de pornire')

    def _sterge_marcaj(self, motiv):
        if self._marcaj_la is None:
            return
        self._marcaj_la = None
        if marcaj.sterge(self.profil.director):
            jurnal.noteaza(self.et, 'marcaj de pornire sters (%s)' % motiv)

    def _verifica_marcajul(self):
        """La pornirea sesiunii. Marcaj ramas si recent = enigma2 a murit cat pornea un serviciu al nostru."""
        m = marcaj.citeste(self.profil.director)
        if m is None:
            return
        marcaj.sterge(self.profil.director)
        if not marcaj.recent(m, time.time(), marcaj.compat.monoton(), self._boot):
            jurnal.noteaza(self.et, 'marcaj de pornire vechi, sters: %s' % m.get('ref'))
            return
        self._protectie = {'cheie': buchete.cheie_ref(m['ref']), 'inainte': m.get('inainte'),
                           'pana': marcaj.compat.monoton() + 300, 'ref': m['ref']}
        text_ref = compat.text_nativ(m['ref']) if compat.e_text(m['ref']) else str(m['ref'])   # 2.7: nume ne-ASCII
        nume = text_ref.split(':', 10)[-1].split(':', 1)[-1] if text_ref.count(':') > 10 else text_ref
        jurnal.noteaza(self.et, 'PROTECTIE: enigma2 a murit cat pornea %s (marcaj de acum %d s); nu il pornesc automat'
                       % (m['ref'], max(0, time.time() - (m.get('t') or 0))))
        self._anunta(_('Pornirea postului %s a oprit interfata data trecuta. Nu l-am mai pornit automat.') % nume,
                     m.get('t'))

    def _refuza_pornirea_automata(self, nav, playref, text, protectie):
        jurnal.noteaza(self.et, 'PROTECTIE: nu pornesc automat %s; zap pe %s' % (text, protectie.get('inainte') or
                                                                                'nimic (stop)'))
        try:
            from enigma import eTimer
            t = eTimer()
            self._leaga('protectie', t, lambda: self._zap_inapoi(protectie.get('inainte'), text))
            t.start(0, True)
            self._timer_protectie = t
        except Exception:
            jurnal.eroare(self.et, 'protectia la pornire')
        return playref, True

    def _zap_inapoi(self, inainte, refuzat):
        self._timer_protectie = None
        try:
            nav = self.sesiune.nav
            if not aceeasi_ref(nav.getCurrentlyPlayingServiceReference(), refuzat):
                return          # utilizatorul a ales deja altceva
            if inainte:
                from enigma import eServiceReference
                nav.playService(eServiceReference(inainte))
            else:
                nav.stopService()
        except Exception:
            jurnal.eroare(self.et, 'zap-ul inapoi al protectiei')

    def _anunta(self, mesaj, t=None):
        from . import intrare
        intrare.arata_notita(mesaj, t)

    def extensie_inregistrare(self, nav, ref, *rest):
        try:
            # un post al nostru scris cu un port vechi sau in alta forma a sunetului (de pilda intr-un timer facut
            # inainte) se inregistreaza in forma de acum; pe portul vechi asculta acum alt program
            nou = buchete.ref_curenta(self.profil, _ref_text(ref))
            if nou is not None:
                return _ref_dupa_text(ref, nou)
        except Exception:
            jurnal.eroare(self.et, 'extensia de inregistrare (portul vechi)')
        try:
            tine = self.tuner.tinut() or (self._prin_8001() and self.releu.ruleaza())
            if tine and not self._simulare():
                text = _ref_text(ref)
                if '%3a//' not in text and '://' not in text:
                    if not fir.in_principal():
                        # din alt fir tunerul nu se poate da sincron: se cedeaza in firul principal, cat de curand
                        jurnal.noteaza(self.et, 'o inregistrare din alt fir cere tunerul: cedez in firul principal')
                        fir.programeaza(self.cedeaza, 'inregistrare', True)
                        return ref
                    jurnal.noteaza(self.et, 'o inregistrare cere tunerul: cedez')
                    self.cedeaza('inregistrare', opreste_serviciul=True)
        except Exception:
            jurnal.eroare(self.et, 'extensia de inregistrare')
        return ref

    @staticmethod
    def _rotorul_se_misca():
        try:
            from enigma import eDVBSatelliteEquipmentControl
            return bool(eDVBSatelliteEquipmentControl.getInstance().isRotorMoving())
        except Exception:
            return False

    @staticmethod
    def _simulare():
        """In Navigation.recordService, variabila locala `simulate` spune daca e doar o verificare.
        Daca nu o putem citi, tratam cererea ca inregistrare adevarata (inregistrarea are prioritate)."""
        try:
            cadru = sys._getframe(2)
            for _pas in range(3):
                if cadru is None:
                    break
                if 'simulate' in cadru.f_locals:
                    return bool(cadru.f_locals['simulate'])
                cadru = cadru.f_back
        except Exception:
            pass
        return False

    def _eveniment(self, ev):
        """Doar pe imaginile fara extensii de zap. Evenimentele vin des: aici nu se face nimic greu."""
        if self._extensii or self._in_repornire:
            return
        if not fir.in_principal():
            fir.programeaza(self._eveniment, ev)
            return
        try:
            from enigma import iPlayableService
            if ev == iPlayableService.evEnd:
                if self.stare != 'oprit' and self.mod == 'zap':
                    tinea_8001 = self._tine_8001()
                    self.opreste('serviciul s-a oprit (imagine fara extensii de zap)')
                    if tinea_8001:
                        self._arma_verificarea(None)   # serviciul nou porneste chiar acum: doar plasa la 9 s
            elif ev == iPlayableService.evStart and self.stare == 'oprit' and self.sesiune is not None:
                ref = self.sesiune.nav.getCurrentlyPlayingServiceReference()
                parti = buchete.desparte_ref(self.profil, _ref_text(ref))
                if parti is None:
                    return
                feed, tp = self.cauta_feed(parti[0])
                if feed is not None:
                    self._scrie_marcaj(_ref_text(ref))
                    self._pregateste(feed, tp, ref, 'zap')
        except Exception:
            jurnal.eroare(self.et, 'evenimentul serviciului')

    # ------------------------------------------------------------ pregatirea
    def _pregatit_pentru(self, feed, tp):
        return (self.feed is not None and self.feed.get('id') == feed.get('id') and self._releu_gata
                and self.releu.ruleaza() and (self.tuner.prins_pe(tp) or self._prin_8001(feed)))

    def _pregateste(self, feed, tp, playref, mod):
        self._ultimii_octeti = None
        self._date_la = 0.0
        self._ultimele_utile = None
        self._utile_de_la = self._utile_la = 0.0
        self._a_curs = False
        self._nota_pornire = False
        self._semnal_purtator = None
        if self._tine_tuner(feed):
            acelasi_tp = self.tuner.prins_pe(tp)
        else:
            acelasi_tp = self.tp is not None and tuner.cheie_transponder(self.tp) == tuner.cheie_transponder(tp)
        acelasi_feed = acelasi_tp and self.feed is not None and self.feed.get('id') == feed.get('id') \
            and self.releu.ruleaza()
        self.mod = mod
        self.stare = 'pregatire'
        self.feed, self.tp = feed, tp
        self._playref = playref
        self.ref_asteptat = _ref_text(playref) if playref is not None else None
        self._paza_abateri = 0
        self.fundal.opreste()
        if acelasi_feed:
            self._asteapta_releul()
        elif acelasi_tp:
            if self._prin_8001(feed):
                self.tuner.elibereaza()       # din EDI (canal brut) in ETI pe acelasi transponder: 8001 cere tunerul
            self.releu.opreste()
            self._releu_gata = False
            self._porneste_releul()
        elif self._prin_8001(feed):
            # 8001 (T2-MI, ETI): tunerul il ia streamserver-ul enigma2 pentru purtator; celalalt plugin si un canal
            # brut al nostru (feed EDI de dinainte) trebuie sa-l dea inapoi
            self.tuner.elibereaza()
            self.releu.opreste()
            # imaginea: sesiunea feed-ului de dinainte (alt transponder) se opreste pe loc, ca releul nou sa gaseasca
            # tunerul liber la prima cerere (altfel cererea lui cade pe tuner ocupat si se reia dupa o pauza)
            self._inchide_sesiunile_8001('trecere pe alt feed')
            self._releu_gata = False
            self.coord.cere_tuner(self)
            self._porneste_releul()
        else:
            self.releu.opreste()
            self._releu_gata = False
            self.coord.cere_tuner(self)
            self._arata(_('Acord pe %s') % tuner.text_transponder(tp))
            self.tuner.acordeaza(tp, self._acord_gata, self._arata)
        if mod == 'zap':
            self._porneste_paza()

    def _acord_gata(self, ok, mesaj):
        if self.stare != 'pregatire':
            return
        if not ok:
            self._esec(_('Nu pot receptiona transponderul: %s') % mesaj)
            return
        self._porneste_releul()

    def _porneste_releul(self):
        date = dict((k, v) for k, v in self.tp.items() if k not in ('feeduri', 'sursa'))
        date.update(dict((k, v) for k, v in self.feed.items() if k != 'sursa'))
        date.update({'http_port': self.profil.port, 'port_control': self.profil.port_control, 'adapter': 0, 'demux': 0,
                     'frontend': self.tuner.slot, 'plugin': self.nume})
        if self._prin_8001():
            from . import lamedb
            purtator = lamedb.purtator_pentru(self.lista(), self.tp, self.feed)
            if purtator is None:
                self._esec(_('Eroare interna.'))
                return
            # feed nou: purtatorul lui se scrie acum, inainte de releu (streamserver-ul trebuie sa-l stie).
            # Scrierea (citire lamedb, fsync) merge in fundal; releul porneste din callback, in firul principal.
            feed_id = self.feed.get('id')
            self.fundal_disc.lanseaza(_sub_zavor, lambda ok, r: self._purtator_scris(ok, r, feed_id, date,
                                                                                               purtator),
                                      lamedb.actualizeaza, self.lista(), None, None, False,
                                      self.feeduri_active(plus=self.feed),
                                      self.profil.tip)
            return
        self._lanseaza_releul(date)

    def _purtator_scris(self, ok, r, feed_id, date, purtator):
        if self.stare != 'pregatire' or self.feed is None or self.feed.get('id') != feed_id:
            return
        if not ok or not isinstance(r, dict) or r.get('eroare'):
            self._esec(_('Nu pot scrie serviciul purtator in lamedb.'))
            return
        if r.get('schimbat'):
            from . import lamedb
            lamedb.reincarca_servicii()          # enigma2: doar in firul principal
        date['purtator_ref'] = purtator['ref']
        date['ref_8001'] = purtator['ref']      # asta citeste releul (surse.ref_purtator)
        self._ref_purtator = purtator['ref']
        self._uita_refuzurile()                 # refuzurile 8001 se numara de la pornirea acestui releu
        date['url_8001'] = 'http://127.0.0.1:8001/%s' % purtator['ref']
        self._lanseaza_releul(date)

    def _lanseaza_releul(self, date):
        try:
            buchete.scrie_atomic(self.profil.fisier_feed(), json.dumps(date, ensure_ascii=False).encode('utf-8'))
        except Exception:
            jurnal.eroare(self.et, 'fisierul feed-ului')
            self._esec(_('Nu pot scrie in /tmp.'))
            return
        script = os.path.join(self.cale_plugin, 'motor', self.profil.releu)
        # FARA redirectari (>/dev/null, 2>fisier): o teava inchisa face enigma2 sa astepte blocant procesul in
        # firul principal (vezi releu_http.muta_erorile). Fisierul de erori il deschide releul, din HDS_ERORI.
        # interpretorul: python3 cand exista pe receptor, altfel python (imagini doar cu 2.7); aflat o data, fara
        # subprocess (compat.interpretor_python), deci nimic blocant in firul principal
        comanda = 'exec env HDS_ERORI=%s nice -n 10 %s %s %s --inactiv %d' % (
            self.profil.fisier_erori_releu(), compat.interpretor_python(), script, self.profil.fisier_feed(),
            INACTIV_RELEU_S)
        self._arata(_('Pornesc %s') % (self.feed.get('nume') or self.feed.get('id')))
        if not self.releu.porneste(comanda):
            self._esec(_('Releul nu a pornit.'))
            return
        self._asteapta_releul()

    def _asteapta_releul(self):
        self._releu_gata = False
        self._termen = _monoton() + TERMEN_RELEU_S
        if self._timer_asteptare is None:
            from enigma import eTimer
            self._timer_asteptare = eTimer()
            self._leaga('asteptare', self._timer_asteptare, self._pas_asteptare)
        self._timer_asteptare.start(PAS_ASTEPTARE_MS, False)

    def _cale_gata(self):
        fid = buchete._curata_id(self.feed.get('id'))
        if self.profil.tip == 't2' and self.mod == 'zap':
            # T2: ordinea dovedita pe receptor: playerul porneste imediat ce releul asculta;
            # releul cere 8001, streamserver-ul roteste antena si acordeaza, enigma2 asteapta datele fara sa
            # renunte. Deci „gata" = releul raspunde, nu „are servicii". Serviciile se invata dupa, in fundal.
            return '/stare'
        if self.profil.tip == 'dab':
            return '/dab/%s/lista' % fid
        return '/t2/%s/%d/servicii' % (fid, buchete._int(self.feed.get('plp'), 0))

    def _pas_asteptare(self):
        try:
            if self.stare != 'pregatire' or self.feed is None:
                self._opreste_timer(self._timer_asteptare)
                return
            if self._prin_8001() and self._rotorul_se_misca():
                # streamserver-ul roteste antena: termenul curge doar dupa ce s-a oprit
                self._termen = max(self._termen, _monoton() + 20)
                self.rotire = True
                self._arata(_('Se roteste antena'))
            else:
                self.rotire = False
            if _monoton() > self._termen:
                self._esec(_('Releul nu a primit date de la %s.') % (self.feed.get('nume') or self.feed.get('id')))
                return
            if self._tuner_8001_refuzat():
                return
            if self.fundal.in_curs() == 0:
                self.fundal.lanseaza(fundal.cere_json, self._raspuns_releu, self.profil.url_releu(self._cale_gata()))
        except Exception:
            jurnal.eroare(self.et, 'asteptarea releului')
            self._esec(_('Eroare interna.'))

    @staticmethod
    def _servicii_din(raspuns):
        if isinstance(raspuns, list):
            return raspuns
        if isinstance(raspuns, dict):
            for k in ('posturi', 'servicii', 'lista'):
                if isinstance(raspuns.get(k), list):
                    return raspuns[k]
        return []

    def _raspuns_releu(self, ok, raspuns):
        if self.stare != 'pregatire' or self.feed is None:
            return
        if not ok:
            return   # releul inca porneste; mai incercam pana la termen
        if self.profil.tip == 't2' and self.mod == 'zap':
            if not isinstance(raspuns, dict):
                return
            self._opreste_timer(self._timer_asteptare)
            self._releu_gata = True
            self._servicii_cerute = False
            self._asteapta_prime_date_pana = _monoton() + PRIMELE_DATE_S
            # playerul porneste inainte de date (acordul si rotirea le face sesiunea 8001): nota „Pornesc ...”
            # ramane pe ecran pana vin primele date sau apare imaginea, ca ecranul negru sa nu ramana fara nimic
            self._arata_pornesc()
            self._porneste_playerul()
            return
        servicii = self._servicii_din(raspuns)
        if not servicii:
            return
        self._opreste_timer(self._timer_asteptare)
        self._releu_gata = True
        self._memoreaza_servicii(servicii)
        self._ascunde()
        if self.mod == 'invata':
            self._invatare_gata(True, len(servicii))
            return
        self._porneste_playerul()

    def _porneste_playerul(self):
        nav = self.sesiune and self.sesiune.nav
        if nav is None:
            self.opreste('fara sesiune')
            return
        curent = _ref_text(nav.getCurrentlyPlayingServiceReference())
        if not aceeasi_ref(curent, self.ref_asteptat):
            self.opreste('utilizatorul a plecat in timpul pregatirii')
            return
        self.stare = 'canta'
        jurnal.noteaza(self.et, 'gata, pornesc playerul pe %s' % self.ref_asteptat)
        self._player_la = _monoton()
        self._reluat_dupa_date = False
        self._fara_imagine_notat = False
        # inaintea playerului: bara citeste receptie.json cel mult o data la 2 s, iar PMT-ul poate veni in acest timp
        self._scrie_receptie(fortat=True)
        self._in_repornire = True
        try:
            nav.playService(self._playref, checkParentalControl=False, forceRestart=True)
        finally:
            self._in_repornire = False

    def _scrie_receptie(self, fortat=False):
        """/tmp/hdsatelit/receptie.json pentru skin: la pornirea postului si apoi cel mult la 2 s (din paza)."""
        if self.stare != 'canta' or self.feed is None or self.mod != 'zap':
            return
        acum = _monoton()
        if not fortat and acum - self._receptie_la < receptie.PAS_S:
            return
        self._receptie_la = acum
        try:
            fid = buchete._curata_id(self.feed.get('id'))
            parti = buchete.desparte_ref(self.profil, self.ref_asteptat or '')
            sid = parti[1] if parti and self.profil.tip == 'dab' else None
            post = None
            for s in self._servicii_cache.get(fid) or []:
                if isinstance(s, dict) and buchete._int(s.get('sid'), -1) == sid:
                    post = s
                    break
            if self._tine_tuner():
                semnal, slot = self.tuner.semnal(), self.tuner.slot
            else:
                fe = self._frontend_purtator
                semnal, slot = self._semnal_purtator, (fe[1] if fe is not None else None)
            # `actualizat` din fisier e ora de perete: skinul il compara cu ora lui (pasul de 2 s merge pe ceasul monoton)
            receptie.scrie(receptie.compune(self.profil.tip, self.ref_asteptat, self.feed, self.tp, sid, post,
                                            self.ultima_stare_releu, semnal,
                                            self._ref_purtator if self._prin_8001() else None, time.time(), slot))
            self._receptie_scrisa = True
        except Exception:
            jurnal.eroare(self.et, 'receptie.json')

    def _text_cautare_oprita(self):
        """Mesajul cand cautarea posturilor / programelor (mod „invata”) se opreste inainte de sfarsit."""
        if self.profil.tip == 'dab':
            return _('Cautarea posturilor s-a oprit.')
        return _('Cautarea programelor s-a oprit.')

    def _esec(self, mesaj):
        jurnal.noteaza(self.et, mesaj)
        mod = self.mod
        self.opreste(mesaj)
        if mod == 'invata':
            self._invatare_gata(False, mesaj)
        else:
            self._popup(mesaj)

    # ------------------------------------------------------------ paza
    def _porneste_paza(self):
        if self._timer_paza is None:
            from enigma import eTimer
            self._timer_paza = eTimer()
            self._leaga('paza', self._timer_paza, self._pas_paza)
        self._timer_paza.start(PAZA_MS, False)

    def _pas_paza(self):
        try:
            if self.stare in ('oprit', 'tinut') or self.mod != 'zap':
                self._opreste_timer(self._timer_paza)
                return
            if self._amanat is not None:
                return                   # zap amanat pe alt feed: referinta curenta e a lui, nu a releului de acum
            nav = self.sesiune and self.sesiune.nav
            curent = _ref_text(nav.getCurrentlyPlayingServiceReference()) if nav else ''
            if not aceeasi_ref(curent, self.ref_asteptat):
                self._paza_abateri += 1
                if self._paza_abateri == 1:
                    # dovada pe receptor pentru defectul 9: ce forma are referinta curenta fata de cea asteptata
                    asteptat = self.ref_asteptat
                    asteptat = compat.text_nativ(asteptat) if compat.e_text(asteptat) else _ref_text(asteptat)
                    jurnal.noteaza(self.et, 'paza: alta referinta, curent=%s asteptat=%s'
                                   % (compat.text_nativ(curent or '')[:80], (asteptat or '')[:80]))
                if self._paza_abateri >= ABATERI_MAX:
                    if self._poate_tine(curent):
                        # oprire fara zap (stop, standby): s-au scurs deja ABATERI_MAX pasi
                        self._tine('serviciul nostru nu mai ruleaza',
                                   max(PAZA_MS / 1000.0, TINERE_8001_S - ABATERI_MAX * PAZA_MS / 1000.0))
                    else:
                        self.opreste('serviciul nostru nu mai ruleaza')
                return
            self._paza_abateri = 0
            acum = _monoton()
            if self.stare == 'canta' and self.fundal.in_curs() == 0 and acum - self._stare_la >= PAZA_STARE_S:
                self._stare_la = acum
                self.fundal.lanseaza(fundal.cere_json, self._stare_paza, self.profil.url_releu('/stare'))
            if self.stare == 'canta' and self._tine_tuner():
                self.tuner.reimprospateaza()     # semnalul pentru receptie.json si captura, citit in fundal
            elif self.stare == 'canta' and self._prin_8001():
                self._citeste_semnalul_purtatorului(acum)
            if self._nota_pornire and self.latime_video() > 0:
                self._nota_pornire = False       # imaginea a venit inaintea primei citiri /stare cu date
                self._ascunde()
            if self.stare == 'canta' and self.ultima_stare_releu:
                self._scrie_receptie()           # la 2 s cu semnalul proaspat; starea releului e cea de la ultimul /stare
        except Exception:
            jurnal.eroare(self.et, 'paza')

    def _prag_fara_date(self):
        return 8.0 if self.profil.tip == 'dab' else 5.0

    def _numara_utile(self, r, acum):
        """T2 fara semnal (vazut pe 53E): octetii intrati din 8001 pot creste fara nicio data utila, iar
        marcajul de pornire se stergea ca dupa o redare buna. Aici se numara ce iese chiar din releu: T2 octetii iesiti
        din decapsulatoare, DAB cadrele. Daca /stare nu are aceste campuri (releu vechi), nu se numara nimic."""
        utile = None
        try:
            if self.profil.tip == 't2':
                dec = r.get('decapsulatoare')
                if isinstance(dec, dict) and dec:
                    utile = sum(int(d.get('iesit') or 0) for d in dec.values() if isinstance(d, dict))
            else:
                cadre = r.get('cadre')
                if isinstance(cadre, int) and not isinstance(cadre, bool):
                    utile = cadre
        except (TypeError, ValueError, AttributeError):
            utile = None
        if utile is None:
            return
        if self._ultimele_utile is not None and utile > self._ultimele_utile:
            if not self._utile_de_la:
                self._utile_de_la = acum
            self._utile_la = acum
        self._ultimele_utile = utile

    def _pe_placa(self):
        """Postul curent se reda prin placa (tipul 1 cu sursa http, eHdsFluxHttp): T2, si DAB in forma TS. Atunci
        programul (PAT/PMT) se poate citi din serviciu; la 4097 (servicemp3) nu."""
        if self.profil.tip == 't2':
            return True
        return _ref_text(self.ref_asteptat or '').split(':', 1)[0] == '1'

    def _are_program(self):
        """Serviciul curent are tabelul programului (PMT gasit dupa PAT)? True / False; None daca nu se poate afla."""
        try:
            from enigma import iServiceInformation
            s = self.sesiune.nav.getCurrentService()
            info = s and s.info()
            if not info:
                return None
            return int(info.getInfo(iServiceInformation.sPMTPID)) > 0
        except Exception:
            return None

    def _reia_dupa_date_tarzii(self, acum):
        """T2 si DAB pe placa (_pe_placa): playerul porneste cand releul raspunde, uneori inainte de date; enigma2 cauta
        PAT-ul numai PAT_TERMEN_S. O singura hotarare pe pornirea playerului, luata dupa starea serviciului, nu dupa
        ceas: la RELUARE_DUPA_S de la pornire, cu datele utile curgand, serviciul fara tabelul programului (sPMTPID) a
        pierdut PAT-ul, deci playerul porneste o data din nou pe aceeasi referinta (releul si sesiunea 8001 raman). Cu
        programul gasit imaginea sau sunetul merg si nu se atinge nimic; fara raspuns de la info nu se reporneste
        nimic."""
        if (not self._pe_placa() or self.mod != 'zap' or self._reluat_dupa_date or not self._player_la
                or not self._utile_de_la or acum - self._player_la < RELUARE_DUPA_S):
            return
        self._reluat_dupa_date = True
        nav = self.sesiune and self.sesiune.nav
        if nav is None or not aceeasi_ref(nav.getCurrentlyPlayingServiceReference(), self.ref_asteptat):
            return
        are = self._are_program()
        if are is not False:
            if are is None:
                jurnal.noteaza(self.et, 'starea programului nu se poate citi; playerul ramane cum e')
            return
        self.reluari_dupa_date += 1
        jurnal.noteaza(self.et, 'la %.0f s dupa pornirea playerului serviciul n-are inca programul (PAT pierdut, date '
                       'de la %.0f s): il pornesc din nou pe %s'
                       % (acum - self._player_la, self._utile_de_la - self._player_la, (self.ref_asteptat or '')[:80]))
        self._in_repornire = True
        try:
            nav.playService(self._playref, checkParentalControl=False, forceRestart=True)
        finally:
            self._in_repornire = False

    def _noteaza_fara_imagine(self, acum):
        """T2 pe placa: la RELUARE_DUPA_S de la pornirea playerului, cu datele utile curgand, programul gasit si un PID
        video, dar fara imagine: un singur rand in jurnal pe pornirea playerului. Asa arata decodorul video care nu a
        pornit (in nucleu: „VDEC_Chan_Create ... no memory” in /home/root/logs/messages), deosebit de un flux
        care nu vine. Nu se reporneste nimic: o repornire nu ajuta cand decodorul nu-si gaseste memoria."""
        if (self._fara_imagine_notat or self.profil.tip != 't2' or self.mod != 'zap' or not self._player_la
                or not self._utile_de_la or acum - self._player_la < RELUARE_DUPA_S):
            return
        if self._are_program() is not True or self._imaginea_serviciului() is not False:
            return
        self._fara_imagine_notat = True
        jurnal.noteaza(self.et, 'fara imagine la %.0f s dupa pornirea playerului, cu programul gasit si datele '
                       'curgand: decodorul video nu da imagine (%s)' % (acum - self._player_la,
                                                                        (self.ref_asteptat or '')[:80]))

    def _redare_buna(self, acum):
        """Redarea merge de REDARE_BUNA_S cu date adevarate? Cu contorul datelor utile: a crescut de atata timp si
        creste si acum. Fara el (releu vechi): dupa octetii din /stare, ca inainte. Pe placa (_pe_placa) si serviciul
        trebuie sa aiba programul (PMT gasit): datele releului singure nu spun ca decodorul le primeste."""
        if self._pe_placa() and self._are_program() is False:
            return False
        if self._ultimele_utile is not None:
            return (bool(self._utile_de_la) and acum - self._utile_la <= 2 * PAZA_STARE_S
                    and acum - max(self._marcaj_la, self._utile_de_la) >= marcaj.REDARE_BUNA_S)
        return acum - max(self._marcaj_la, self._flux_de_la) >= marcaj.REDARE_BUNA_S

    def _stare_paza(self, ok, r):
        """Paznicul releului: fara octeti noi N secunde (DAB 8, T2 5) cat canta = reacord si releu nou."""
        if self.stare != 'canta':
            return
        agatat = False
        if not ok or not isinstance(r, dict):
            if not self.releu.ruleaza():
                return   # releul cazut il prinde supraveghetorul procesului
            r = {}       # procesul traieste dar /stare nu raspunde (releu agatat): se socoteste ca fara octeti
            agatat = True
        else:
            self.ultima_stare_releu = r
            self._scrie_receptie()
        acum = _monoton()
        if self._prin_8001():
            if self._rotorul_se_misca():
                # antena se roteste pentru streamserver: nu e lipsa de date, doar asteptam (fara alt zap)
                self.rotire = True
                self._asteapta_prime_date_pana = max(self._asteapta_prime_date_pana, acum + 30)
                self._arata(_('Se roteste antena'))
                return
            if self.rotire:
                self.rotire = False
                if self._nota_pornire:
                    self._arata_pornesc()
                else:
                    self._ascunde()
            if not self._a_curs and self._tuner_8001_refuzat():
                return
        self._numara_utile(r, acum)
        self._reia_dupa_date_tarzii(acum)
        self._noteaza_fara_imagine(acum)
        octeti = r.get('octeti', r.get('octeti_intrare'))
        if isinstance(octeti, (int, float)) and not isinstance(octeti, bool):
            curg = self._ultimii_octeti is not None and octeti != self._ultimii_octeti
            self._ultimii_octeti = octeti
        else:
            debit = r.get('debit_kbit', r.get('debit'))
            curg = isinstance(debit, (int, float)) and debit > 0
        if curg:
            self._a_curs = True
            if self._nota_pornire:
                self._nota_pornire = False
                self._ascunde()
            if self.profil.tip == 't2' and not self._servicii_cerute and self.feed is not None:
                self._servicii_cerute = True
                fid = buchete._curata_id(self.feed.get('id'))
                cale = '/t2/%s/%d/servicii' % (fid, buchete._int(self.feed.get('plp'), 0))
                self.fundal.lanseaza(fundal.cere_json, self._servicii_venite, self.profil.url_releu(cale))
            self._asteapta_prime_date_pana = 0.0
            if not self._date_la:
                self._flux_de_la = acum
            self._date_la = acum
            if self._reincercari_date and acum - self._flux_de_la >= LINISTE_RESETARE_S:
                self._reincercari_date = 0
            if self._marcaj_la is not None and self._redare_buna(acum):
                self._sterge_marcaj('redarea merge de %d s' % marcaj.REDARE_BUNA_S)
            return
        if not self._date_la:
            if self._asteapta_prime_date_pana and acum < self._asteapta_prime_date_pana:
                return   # T2: primii octeti pot intarzia cat acordeaza streamserver-ul
            self._date_la = acum
        if self._prin_8001() and not agatat:
            # releul raspunde si se reconecteaza singur la 8001 (cu limita de sesiuni): un releu nou ar insemna inca o
            # sesiune (4 MB pierduti in driver). Se renunta dupa FARA_DATE_8001_S, fara reporniri.
            if acum - self._date_la < FARA_DATE_8001_S:
                return
            nume = self.feed.get('nume') or self.feed.get('id')
            jurnal.noteaza(self.et, 'fara date de %.0f s pe 8001 (releul raspunde, %s): renunt'
                           % (acum - self._date_la, 'au venit date' if self._a_curs else 'niciun octet'))
            self._reincercari_date = 0
            if self._a_curs:
                self._esec(_('Nu mai vin date de la %s. Tunerul a fost eliberat.') % nume)
            else:
                self._esec(_('Nu au venit date de la %s. Tunerul a fost eliberat.') % nume)
            return
        if acum - self._date_la < self._prag_fara_date():
            return
        self._reincercari_date += 1
        jurnal.noteaza(self.et, 'fara date de %.0f s, incercarea %d' % (acum - self._date_la,
                                                                        self._reincercari_date))
        if self._reincercari_date > REINCERCARI_DATE:
            nume = self.feed.get('nume') or self.feed.get('id')
            self._reincercari_date = 0
            self._esec(_('Nu mai vin date de la %s. Tunerul a fost eliberat.') % nume)
            return
        feed, tp, playref, incercari = self.feed, self.tp, self._playref, self._reincercari_date
        self.releu.opreste()
        self.tuner.elibereaza()
        self.coord.elibereaza_tuner(self)
        self._pregateste(feed, tp, playref, 'zap')
        self._reincercari_date = incercari
        self._arata(_('Nu mai vin date. Reiau acordul.'))

    def _servicii_venite(self, ok, raspuns):
        if not ok or self.feed is None:
            self._servicii_cerute = False
            return
        servicii = self._servicii_din(raspuns)
        if not servicii:
            self._servicii_cerute = False
            return
        self._memoreaza_servicii(servicii)

    def _memoreaza_servicii(self, servicii):
        """Serviciile invatate, buchetul si purtatorii se scriu in fundal; reincarcarile enigma2 vin in firul
        principal, doar daca s-a schimbat ceva."""
        try:
            fid = buchete._curata_id(self.feed.get('id'))
            self._servicii_cache[fid] = list(servicii)[:500]
            self.fundal_disc.lanseaza(_sub_zavor, self._servicii_scrise, self._scrie_servicii, fid, servicii,
                                      self.lista(),
                                      self.feeduri_active() | set([fid]))
        except Exception:
            jurnal.eroare(self.et, 'memorarea serviciilor')

    def _scrie_servicii(self, fid, servicii, lista, active):
        """In firul de fundal: doar fisiere, nimic din enigma2."""
        rez = {'buchete': False, 'lamedb': False}
        if buchete.salveaza_servicii(self.profil, fid, servicii):
            rez['buchete'] = bool(buchete.reface(self.profil, lista, reincarca=False).get('schimbat'))
            from . import lamedb
            rez['lamedb'] = bool(lamedb.actualizeaza(lista, reincarca=False, active=active,
                                                     tip=self.profil.tip).get('schimbat'))
        return rez

    def _servicii_scrise(self, ok, rez):
        if not ok:
            jurnal.noteaza(self.et, 'memorarea serviciilor: %s' % rez)
            return
        if rez.get('buchete'):
            buchete.reincarca_buchete()
        if rez.get('lamedb'):
            from . import lamedb
            lamedb.reincarca_servicii()

    def latime_video(self):
        """Martorul imaginii (dovedit pe receptor): latimea din info-ul serviciului. -1 daca nu se stie."""
        try:
            from enigma import iServiceInformation
            s = self.sesiune.nav.getCurrentService()
            info = s and s.info()
            return int(info.getInfo(iServiceInformation.sVideoWidth)) if info else -1
        except Exception:
            return -1

    # ------------------------------------------------------------ releul cade
    def _releu_repornit(self, numar):
        jurnal.noteaza(self.et, 'releul repornit (%d)' % numar)
        fundal.inchide_conexiunile(self.profil.port_control)     # conexiunea spre releul mort nu se mai refoloseste
        if self.stare == 'canta' and self.mod == 'zap':
            self.stare = 'pregatire'
            self._asteapta_releul()
        elif self.stare == 'pregatire':
            self._asteapta_releul()

    def _releu_renunta(self, mesaj):
        self._esec(mesaj)

    # ------------------------------------------------------------ oprirea si cedarea
    def cedeaza(self, motiv, opreste_serviciul=False):
        canta = self.stare in ('canta', 'pregatire') and self.mod == 'zap'
        if self.mod == 'invata':
            self._ref_inainte = None
            self._esec(self._text_cautare_oprita())
            return
        self.opreste(motiv)
        if opreste_serviciul and canta:
            self._popup(_('Tunerul a fost dat inregistrarii. Postul s-a oprit.'))
            self._opreste_serviciul_dupa()

    def _opreste_serviciul_dupa(self):
        """Serviciul nostru care ruleaza se opreste la urmatoarea trecere prin bucla principala (nu din mijlocul unui
        apel al Navigation sau al pazei): Navigation il uita, deci alegerea lui din nou (lista, web) il porneste."""
        try:
            from enigma import eTimer
            t = eTimer()
            self._leaga('oprire', t, lambda: self._opreste_serviciul(t))
            t.start(0, True)
            self._timer_oprire = t
        except Exception:
            pass

    def _opreste_serviciul(self, t):
        try:
            nav = self.sesiune.nav
            if buchete.al_nostru(self.profil, _ref_text(nav.getCurrentlyPlayingServiceReference())):
                nav.stopService()
        except Exception:
            jurnal.eroare(self.et, 'oprirea serviciului')
        self._timer_oprire = None

    def opreste(self, motiv=''):
        if self.stare != 'oprit' or self.tuner.tinut() or self.releu.ruleaza():
            jurnal.noteaza(self.et, 'opresc: %s' % motiv)
        self._sterge_marcaj('oprire normala')
        if self._receptie_scrisa:
            self._receptie_scrisa = False
            receptie.sterge()
        self._anuleaza_amanat()
        self._opreste_tinerea()
        prin_8001 = self._prin_8001()
        self.releu.opreste()
        if prin_8001:
            self._inchide_sesiunile_8001(motiv)
        self.tuner.elibereaza()
        self.coord.elibereaza_tuner(self)
        self.fundal.opreste()
        # 0.1.4: fara CLOSE_WAIT ramas in enigma2 spre releul oprit (conexiunea tinuta a pazei)
        fundal.inchide_conexiunile(self.profil.port_control)
        self._opreste_timer(self._timer_asteptare)
        self._opreste_timer(self._timer_paza)
        self._ascunde()
        self._releu_gata = False
        self._ultimii_octeti = None
        self._date_la = 0.0
        self._ultimele_utile = None
        self._utile_de_la = self._utile_la = 0.0
        self._nota_pornire = False
        self._semnal_purtator = None
        self.stare = 'oprit'
        self.mod = None
        self.feed = None
        self.tp = None
        self._playref = None
        self.ref_asteptat = None

    @staticmethod
    def _opreste_timer(t):
        if t is not None:
            try:
                t.stop()
            except Exception:
                pass

    # ------------------------------------------------------------ invatarea posturilor fara zap
    def servicii_invatate(self, feed_id):
        """Posturile / serviciile invatate ale unui feed: cele tinute de la ultima invatare, altfel servicii.json
        (citire mica). [] daca nu se stie nimic."""
        fid = buchete._curata_id(feed_id)
        if self._servicii_cache.get(fid):
            return list(self._servicii_cache[fid])
        return list((buchete.citeste_servicii(self.profil).get(fid) or {}).get('servicii') or [])

    def invata(self, feed, tp, la_gata):
        """Acord + releu doar cat sa aflam posturile / serviciile. la_gata(ok, numar_sau_mesaj).
        Serviciul care rula se opreste (tunerul e unul) si se repune la sfarsit."""
        self.repunere = None
        try:
            nav = self.sesiune.nav
            self._ref_inainte = nav.getCurrentlyPlayingServiceReference()
            if self._ref_inainte is not None and not buchete.al_nostru(self.profil, _ref_text(self._ref_inainte)):
                nav.stopService()
            else:
                self._ref_inainte = None
        except Exception:
            self._ref_inainte = None
        self._la_invatat = la_gata
        self._invata_prin_8001 = self._prin_8001(feed)
        self._pregateste(feed, tp, None, 'invata')

    def _invatare_gata(self, ok, rezultat):
        cb, self._la_invatat = self._la_invatat, None
        self.opreste('invatare terminata')
        inainte, self._ref_inainte = self._ref_inainte, None
        if inainte is not None:
            try:
                self._repune(inainte, self._invata_prin_8001)
            except Exception:
                jurnal.eroare(self.et, 'repunerea serviciului')
        self._invata_prin_8001 = False
        if cb is not None:
            try:
                cb(ok, rezultat)
            except Exception:
                jurnal.eroare(self.et, 'la_invatat')

    def _repune(self, inainte, prin_8001):
        """Dupa invatare: canalul de dinainte porneste din nou, cu pornire fortata (un playService simplu pe aceeasi
        referinta nu face nimic in Navigation, iar o pornire cazuta pe tuner ocupat lasa ultimul cadru pe ecran).
        Daca invatarea a mers prin 8001 si sesiunea de pe purtator inca tine tunerul (streamserverul altor imagini o
        inchide abia in bucla principala), pornirea asteapta eliberarea, ca la plecarea de pe un canal 8001.
        Verificarea de la VERIFICARE_TUNER_S da un zap din nou, o singura data, daca serviciul a ramas fara tuner."""
        nav = self.sesiune.nav
        text = _ref_text(inainte)
        curent = _ref_text(nav.getCurrentlyPlayingServiceReference())
        if curent.strip():
            jurnal.noteaza(self.et, 'dupa invatare ruleaza deja %s: nu repun %s' % (curent[:80], text[:80]))
            return
        try:
            from Screens import Standby
            standby = Standby.inStandby
        except Exception:
            standby = None
        if standby is not None:
            # in standby nu porneste nimic acum: standby-ul tine minte canalul (invatarea il oprise, deci tinea minte
            # niciunul) si il porneste la iesire
            if getattr(standby, 'prev_running_service', None) is None:
                standby.prev_running_service = inainte
            jurnal.noteaza(self.et, 'dupa invatare receptorul e in standby: %s porneste la iesirea din standby'
                           % text[:80])
            return
        self.repunere = {'text': text, 'nume': _nume_serviciu(inainte) or text[:40], 'stare': 'asteapta',
                         'mesaj': '', 'la': time.time(), 'la_mono': _monoton()}
        if cere_tunerul(text, self._ref_purtator):
            self._arma_verificarea(text, repunere=True)
            self._noteaza_repunerea(self._verificare, 'asteapta')
            clienti = self._clienti_purtator() if prin_8001 else 0
            if clienti != 0:
                acum = _monoton()
                self._eliberare = {'nav': nav, 'playref': inainte, 'text': text, 'de_la': acum,
                                   'pana': acum + ELIBERARE_MAX_S, 'libere': 0, 'fara_api': clienti is None,
                                   'repunere': True}
                jurnal.noteaza(self.et, 'dupa invatare astept eliberarea purtatorului (%s) inainte de %s'
                               % ('fara lista de clienti' if clienti is None else '%d clienti' % clienti, text[:80]))
                if self._timer_eliberare is None:
                    from enigma import eTimer
                    self._timer_eliberare = eTimer()
                    self._leaga('eliberare', self._timer_eliberare, self._pas_eliberare)
                self._timer_eliberare.start(ELIBERARE_PAS_MS, False)
                return
        jurnal.noteaza(self.et, 'dupa invatare repornesc %s' % text[:80])
        nav.playService(inainte, checkParentalControl=False, forceRestart=True)
        if self._verificare is None or not self._verificare.get('repunere'):
            self.repunere = None              # fara verificare (flux, alt transponder al purtatorului): nimic de urmarit

    def _inchide_sesiunile_8001(self, motiv):
        """Imaginea HDSatelit: sesiunile serverului local 8001 de pe purtatorul nostru se opresc acum, in firul
        principal, deci tunerul e liber cand se intoarce functia (altfel s-ar elibera abia dupa ce bucla principala
        prelucreaza plecarea releului, iar un canal pornit imediat dupa ar ramane fara tuner). Pe alte imagini nu
        exista serverul local: streamserverul enigma2 il elibereaza singur, iar pornirea asteapta (_eliberare)."""
        if not self._ref_purtator or not fir.in_principal():
            return 0
        try:
            from . import server8001
        except ImportError:
            return 0
        try:
            n = server8001.opreste_sesiunile(self._ref_purtator)
        except Exception:
            jurnal.eroare(self.et, 'oprirea sesiunilor 8001')
            return 0
        if n:
            jurnal.noteaza(self.et, 'sesiuni 8001 oprite pe loc (%s): %d' % (motiv, n))
        return n

    def _uita_refuzurile(self):
        try:
            from . import server8001
            server8001.uita_refuzurile(self._ref_purtator)
        except Exception:
            pass

    def _tuner_8001_refuzat(self):
        """Imaginea: sesiunea 8001 a purtatorului a fost refuzata de REFUZURI_8001_MAX ori la rand (inregistrarea nu
        porneste: tunerul de satelit e luat de o inregistrare sau de alt canal). Atunci asteptarea datelor se opreste,
        mesajul apare pe loc, nu dupa PRIMELE_DATE_S + FARA_DATE_8001_S de ecran negru, iar serviciul se opreste (fara
        el Navigation l-ar tine ca serviciu curent, iar alegerea lui din nou n-ar face nimic). -> True daca s-a oprit."""
        if not self._prin_8001() or not self._ref_purtator or not fir.in_principal():
            return False
        try:
            from . import server8001
            n = server8001.refuzuri(self._ref_purtator)
        except Exception:
            return False
        if not n or n < REFUZURI_8001_MAX:
            return False
        jurnal.noteaza(self.et, 'sesiunea 8001 refuzata de %d ori la rand (tunerul nu se poate lua): renunt' % n)
        self._uita_refuzurile()
        mod = self.mod
        self._esec(_('Tunerul e ocupat (inregistrare sau alt canal). Alege mai tarziu.'))
        if mod == 'zap':
            self._opreste_serviciul_dupa()
        return True

    def _citeste_semnalul_purtatorului(self, acum):
        """8001: tunerul il tine sesiunea serverului (sau streamserverul), nu controlorul; semnalul frontend-ului de
        satelit al purtatorului se citeste in fundal (ioctl, ca la captura), cel mult o data la receptie.PAS_S, pentru
        receptie.json (bara)."""
        if self.tp is None or acum - self._semnal_la < receptie.PAS_S:
            return
        if self._fundal_semnal is None:
            self._fundal_semnal = fundal.Fundal(self.et + '-semnal')
        if self._fundal_semnal.in_curs():
            return
        self._semnal_la = acum
        cheie = tuner.cheie_transponder(self.tp)
        fe = self._frontend_purtator
        if fe is None or fe[0] != cheie:
            fe = self._frontend_purtator = (cheie, tuner.alege_slot(tuner.parametri(self.tp)['orbital_position'])[0],
                                            None)
        tp = self.tp

        def venit(ok, rez):
            if not ok or not isinstance(rez, tuple) or self.tp is not tp or self.stare != 'canta':
                return
            cale, semnal = rez
            if self._frontend_purtator is not None and self._frontend_purtator[0] == cheie:
                self._frontend_purtator = (cheie, self._frontend_purtator[1], cale)
            self._semnal_purtator = semnal or None
        self._fundal_semnal.lanseaza(tuner.citire_frontend, venit, fe[1], fe[2])

    def _arata_pornesc(self):
        self._nota_pornire = True
        self._arata(_('Pornesc %s') % (self.feed.get('nume') or self.feed.get('id')) if self.feed else '')

    def _mesaj_canal(self, ref, text):
        """Fereastra scurta despre un canal care nu e al nostru (de pilda cel de dinainte de invatare): numele lui
        deasupra, nu titlul DVB-T2 / DAB+ al profilului."""
        try:
            from Tools.Notifications import AddPopup
            from Screens.MessageBox import MessageBox
            nume = _nume_serviciu(ref)
            AddPopup('%s\n\n%s' % (nume, text) if nume else text, MessageBox.TYPE_INFO, 8, ID_POPUP)
        except Exception:
            jurnal.eroare(self.et, 'mesajul canalului')

    # ------------------------------------------------------------ mesaje
    def _arata(self, text):
        try:
            if self.sesiune is None:
                return
            if self.mesaj is None:
                from .ecrane import EcranMesaj
                self.mesaj = self.sesiune.instantiateDialog(EcranMesaj)
            self.mesaj.seteaza(_(self.profil.titlu), text)
            self.mesaj.show()
        except Exception:
            jurnal.eroare(self.et, 'mesajul de stare')

    def _ascunde(self):
        try:
            if self.mesaj is not None:
                self.mesaj.hide()
        except Exception:
            pass

    def _popup(self, text):
        try:
            from Tools.Notifications import AddPopup
            from Screens.MessageBox import MessageBox
            AddPopup('%s\n\n%s' % (_(self.profil.titlu), text), MessageBox.TYPE_INFO, 8, ID_POPUP)
        except Exception:
            jurnal.eroare(self.et, 'popup')

