# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# canale_web.py: lista de canale in interfata web (HdsWebControl): alegerea si pornirea canalului pe televizor.
#
# Aceeasi pagina pe telefon, tableta si calculator: asezarea se schimba numai dupa latimea ecranului.
#
# Ce arata si de unde:
# - filele TV / Radio si lista aleasa: buchetele utilizatorului, cu aceleasi radacini ca lista de pe televizor
#   (Screens/ChannelSelection.py, recallBouquetMode: bouquets.tv|radio cand „mai multe buchete” e pornit, altfel numai
#   userbouquet.favourites), si „Toate canalele” (indexul cautarii de pe televizor, Screens/HdsCautareCanale.py);
# - continutul unui buchet: exact lista de pe televizor (eServiceCenter.list(buchet).getContent("SN", False), ordinea
#   din fisier), cu marcajele ca titluri de sectiune;
# - numarul canalului: cel la care duc cifrele telecomenzii (InfoBarGenerics.zapToNumber: se numara numai canalele,
#   fara marcaje si dosare, buchet dupa buchet); in „Toate canalele” nu exista numar;
# - emisiunea de acum (cu progresul) si cea urmatoare: eEPGCache.lookupEvent, cel mult MAX_EPG canale pe cerere; cu
#   „Tradu EPG” titlul vine tradus NUMAI daca traducerea e deja in memorie (Components/HdsTraducereEpg.dinMemorie):
#   lista de canale (pana la 100 de titluri pe cerere) nu porneste traduceri noi, ca sa nu consume cota;
# - sigla: numai daca fisierul exista in caile lui Components/Renderer/Picon.py, cu acelasi nume;
# - cautarea dupa nume si filtrele: aceleasi grupe si aceleasi reguli ca pe televizor (Components/HdsIndexCanale.py:
#   SAU in grup, SI intre grupe), aplicate listei alese; numerele de langa optiuni se numara pe lista aleasa.
#
# Pornirea unui canal merge pe drumul listei de pe televizor, ca istoricul, „ultimul canal” si locul din lista sa fie
# aceleasi ca dupa OK in lista: dintr-un buchet ca zapToNumber (clearPath, enterPath, setCurrentSelection, zap), din
# „Toate canalele” ca rezultatul cautarii de pe televizor (hdsPunePeLista, zap). Selectia se verifica inainte de zap():
# setCurrent pe un canal care lipseste din lista muta cursorul la capatul ei. Radio cu „mod radio separat” oprit: lista
# TV porneste postul numai cu playService (ChannelSelection.hdsLaCanal); daca lista radio e deschisa pe televizor,
# postul se pune in ea ca la OK acolo.
#
# Rute (poarta comuna a HdsJsonResource: reteaua locala, apoi ?token= sau cookie-ul browserului asociat; pornirea cere,
# cu cookie, POST, aceeasi origine si antetul CSRF al panoului):
#   GET  /api/canale-buchete?fila=tv|radio         listele de ales si lista pe care sta televizorul
#   GET  /api/canale-lista?fila=&buchet=&text=&<grup>=v1,v2&de_la=&cate=  randurile (pe pagini), grupele de filtre
#        (numerele lor: cate canale ar ramane cu optiunea bifata, gen_fatete)
#   GET  /api/canale-lista?fila=&buchet=toate&grupe=1      „Toate canalele” pe grupe: antetele (locul, numele, numarul)
#        si grupa canalului de pe televizor (numai fara text si fara filtre)
#   GET  /api/canale-lista?fila=&buchet=toate&grupa=<cheie>&de_la=&cate=  randurile unei grupe (pagini pana la
#        MAX_PAGINA_GRUPA)
#   GET  /api/canale-epg?refs=r1,r2,...             emisiunea de acum si urmatoarea, cel mult MAX_EPG canale
#   GET  /api/canale-acum                           canalul de pe televizor
#   POST /api/canale-porneste?fila=&buchet=&ref=    porneste canalul pe televizor
#   POST /api/canale-favorit?fila=&buchet=&ref=&vrea=1|0  canalul in Favorite (1) sau scos (0): steluta randului
#   GET  /api/canale-sigla?p=<nume>                 sigla (PNG), numai un nume gasit pe disc
#   GET  /canale                                    pagina
#
# VEZI LIVE SI PLAYLISTURI: fiecare canal are, langa stea si "Ghid", butonul "Vezi live": un dialog in
# pagina (nu o fereastra noua) cu playerul comun /tv/player.js (imaginea, stratul receptorului peste ea, butoanele sub
# ea, ecran intreg, inchidere si cu Esc). Fereastra, butonul si descarcarea playlistului sunt codul comun cu pagina
# /cautare (vezi_live_web.py, pus in pagina de vezi_live_web.inPagina); aici raman numai mutaTv (televizorul trece pe
# canal prin /api/canale-porneste) si strangerea listei. Playerul verifica intai canalul (/api/tv-verifica) si, daca nu
# se poate reda acum in browser, arata motivul fara sa porneasca nimic; "Descarca playlist (M3U)" ramane (VLC reda si
# MPEG-2). "Exporta playlist (M3U)" ia lista asa cum e aleasa si filtrata acum (paginile /api/canale-lista) si cere
# fisierul la POST /api/tv-m3u (tv_web.py, acces_extern.py): adresele au cheia playlistului, nu jetonul API. Pagina are
# politica continutului paginii /tv (tv_web.CSP_TV): scripturile de pe receptor si redarea prin MediaSource (blob:).
# "Adresa fixa pentru un aparat" (aparate_web.py): lista si filtrele de acum devin sursa unui aparat din casa (cheie
# fara termen, playlist citit din nou la fiecare cerere, ghid XMLTV); fereastra, stilul, scriptul comun (si deschiderea
# ferestrei, aparatDeschide, comuna cu /cautare) si textele traduse vin din aparate_web.inPagina. Siglele aparatelor se
# citesc prin cere_sigla, ca /api/canale-sigla.
# RANDURILE CARE ARATA LA FEL (acelasi nume si aceleasi semne, de pilda acelasi canal pe trei SID-uri ale aceluiasi
# transponder): langa semne vine ce le deosebeste ("d" in rand: pozitia, frecventa si polarizarea, furnizorul sau
# SID-ul; HdsIndexCanale.deosebiri_treptat), socotit pe toate randurile gasite, nu numai pe pagina ceruta.
# Fila se trimite ca „fila”, nu ca „tip”: „tip” e numele unei grupe de filtre (TV, Radio, DAB+, T2, Internet).
#
# FAVORITE: fiecare rand are steluta lui („f”: 1 cand canalul e in Favorite-le filei,
# userbouquet.favourites.tv|radio). Steluta trimite starea ceruta (vrea=1|0), nu „schimba”: o stare deja buna (de
# pilda schimbata intre timp de pe televizor) nu se intoarce. Pune si scoate aceeasi functie ca tasta FAV de pe
# televizor (Components/HdsFavorite.py), pe referinta DIN LISTA aleasa, ca pornirea. Dupa schimbare listele din memorie
# se uita pe loc (semnatura fisierelor poate prinde o schimbare in aceeasi clipa abia la cererea urmatoare), iar lista
# de pe televizor se citeste din nou daca sta pe Favorite (ascultatorul din ChannelSelection).
#
# FIRUL: construirea listelor si numararea filtrelor ruleaza pe firul enigma2 in felii de cel mult BUGET_S (generatoare
# care cedeaza dupa cel mult UNITATE intrari), iar raspunsul pleaca la sfarsit (NOT_DONE_YET). Toate lucrarile au UN
# singur planificator cu UN singur eTimer: o bataie ruleaza o singura felie, apoi ceasul se pune din nou la cel putin
# PAUZA_MS. Motivul: lib/base/ebase.cpp (processOneEvent) ruleaza intr-un while toate ceasurile scadente inainte de
# poll(), iar un eTimer pornit cu 0 ms e scadent pe loc; felii legate prin ceasuri de 0 ms (sau ceasuri separate pentru
# doua lucrari) ar tine firul fara ca tastele si soclurile sa fie citite. Cu un singur ceas pus la 1 ms dupa felie,
# poll() ruleaza intre oricare doua felii, oricate lucrari ar fi. Bariere: cel mult o constructie in curs pe fel (a doua
# cerere asteapta rezultatul primei); termen TERMEN_S (504), cel mult MAX_LUCRARI in lucru (503).
# Cautarea siglelor pe disc si citirea lor ruleaza pe doua fire separate, cu termen pe fiecare lucrare, iar rezultatul
# se preda firului enigma2 printr-un eTimer (reactor.callLater nu trezeste bucla enigma2).
# Indexul cautarii (memoria comuna a modulului HdsIndexCanale, pe care o schimba si ecranul de cautare) se ia ca la
# ecranul de cautare, fara sa tina firul enigma2 (gen_index): cel din memorie, facut din fisierele de acum; cand nu e
# la zi, pregatirea unuia nou porneste in fundal (fisierele pe un fir, masuratorile si pistele in felii scurte), iar
# cand nu exista niciunul pentru fisierele de acum, cererea il asteapta cu pauze. Inainte se incarca dintr-o bucata
# (index_cu_piste), iar prima cerere dupa o schimbare a pistelor sau a masuratorilor tinea firul secunde intregi.
# Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC dau un furnizor fals (M).

import os
import re
import time

TOATE = "toate"
TIPURI = ("tv", "radio")
MAX_EPG = 50
MAX_PAGINA = 200
MAX_PAGINA_GRUPA = 500    # randurile unei grupe din „Toate canalele” (grupa=), pe pagini mai mari: se cer toate odata
IMPLICIT_PAGINA = 100
MAX_TEXT = 40
MAX_NUME = 128
MAX_TITLU = 256
MAX_REF = 600
MAX_SIGLA = 256 * 1024
BUGET_S = 0.020
ASTEAPTA_INDEX_MS = 100   # pauza intre doua priviri dupa indexul pregatit in fundal
JURNAL_FELIE_S = 0.050
PAUZA_MS = 1              # intre doua felii (vezi FIRUL: un ceas de 0 ms nu lasa poll() sa ruleze)
UNITATE = 50              # intrari (randuri, canale) pe un pas de generator
TERMEN_S = 10             # o cerere pe felii care nu termina in atat primeste 504
MAX_LUCRARI = 8           # cereri pe felii in lucru deodata; peste: 503
ASTEAPTA_BARIERA_MS = 10  # cat doarme o cerere care asteapta constructia aceleiasi liste
VIATA_LISTA_S = 60
VIATA_EPG_S = 30
VIATA_SIGLE_S = 600
ASTEAPTA_SIGLE_S = 3
TERMEN_CITIRE_S = 5       # citirea unei sigle pe fir
TERMEN_CAUTARE_S = 60     # cautarea siglelor pe disc (un disc USB adormit se trezeste in cateva secunde)
MAX_LISTE = 8
MAX_SIGLE_MEMORIE = 200

MARCAJ = 64          # eServiceReference.isMarker
DOSAR = 1            # eServiceReference.isDirectory

_REF = re.compile(r"^\d{1,4}:\d{1,5}(:[0-9A-Fa-f]{1,8}){8}:")
_NUME_SIGLA = re.compile(r"^[0-9A-Fa-f]{1,8}(_[0-9A-Fa-f]{1,8}){9}$")
_FISIER_BUCHET = re.compile(r'FROM BOUQUET "([A-Za-z0-9_.\-]{1,120})"')
_ID_BUCHET = re.compile(r"^[A-Za-z0-9_.\-]{1,120}$")
_CONTROL = re.compile(u"[\u0000-\u001f\u007f-\u009f\ud800-\udfff]")


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi daca nu exista (pe PC)."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def ngettext(unu, multe, n, X):
	"""Pluralul tradus prin HdsIndexCanale.ngettext (formele din Plural-Forms ale limbii; netradus, regula romaneasca:
	msgid-urile sunt in romana). Chemat cu numele simplu, ca xgettext sa vada textul (ngettext e cuvant-cheie implicit)."""
	return X.ngettext(unu, multe, n)


def _jurnal(text):
	print("[HdsWebControl] canale: %s" % _CONTROL.sub("?", str(text)))


def curat(text, maxim=MAX_NUME):
	"""Text venit din satelit (nume, titluri EPG): fara caractere de control si surogate, taiat la `maxim`."""
	if text is None:
		return ""
	if isinstance(text, bytes):
		text = text.decode("utf-8", "replace")
	text = _CONTROL.sub("", str(text)).strip()
	return text[:maxim]


# ---------------------------------------------------------------- referintele

def ref_buna(text):
	"""O referinta de serviciu cu forma enigma2 (tip:steaguri:8 campuri hex:...), fara caractere de control."""
	return bool(text) and len(text) <= MAX_REF and _REF.match(text) is not None and _CONTROL.search(text) is None


def _campuri(ref):
	parti = (ref or "").split(":")
	if len(parti) < 11:
		return None
	try:
		return [int(parti[0]), int(parti[1])] + [int(p or "0", 16) for p in parti[2:10]], parti[10]
	except ValueError:
		return None


def steaguri(ref):
	c = _campuri(ref)
	return c[0][1] if c else 0


def ref_epg(ref):
	"""Referinta DVB fara nume si fara cale, cu hex mare (cum o scrie toString), pentru EPG; None la fluxuri."""
	c = _campuri(ref)
	if c is None:
		return None
	campuri, cale = c
	if campuri[0] != 1 or cale or campuri[1] & (MARCAJ | DOSAR):
		return None
	return "1:0:" + ":".join("%X" % v for v in campuri[2:10]) + ":"


def nume_sigla(ref):
	"""Numele fisierului siglei ca in Renderer/Picon.py (referinta fara nume, „:” -> „_”), numai la canalele DVB."""
	c = _campuri(ref)
	if c is None:
		return None
	campuri, cale = c
	if campuri[0] != 1 or cale or campuri[1] & (MARCAJ | DOSAR):
		return None
	return "%d_%d_" % (campuri[0], campuri[1]) + "_".join("%X" % v for v in campuri[2:10])


def fisier_buchet(ref):
	m = _FISIER_BUCHET.search(ref or "")
	return m.group(1) if m else None


def fara_mod(nume):
	"""Numele buchetului fara „ (TV)” / „ (Radio)” (ChannelSelection.removeModeStr)."""
	for coada in (" (TV)", " (Radio)"):
		if nume.endswith(coada):
			return nume[:-len(coada)]
	return nume


# ---------------------------------------------------------------- furnizorul adevarat (numai pe receptor)

def _legaCeas(ceas, functie):
	try:
		ceas.callback.append(functie)
		return None
	except AttributeError:
		return ceas.timeout.connect(functie)


class FirAgatat(Exception):
	"""Firul sta de prea mult timp la o lucrare (de exemplu o montare moarta sub /media): nu se mai pune nimic in coada."""


class TermenDepasit(Exception):
	"""Lucrarea de pe fir nu a terminat la termen; rezultatul ei intarziat se arunca."""


class _Fir(object):
	"""Un fir pentru fisiere, cu o coada. Rezultatele se predau pe firul enigma2 de un eTimer care bate numai cat asteapta
	cineva un rezultat. Fiecare lucrare are un termen: la depasire se preda TermenDepasit, iar rezultatul intarziat se
	arunca. Cat timp firul sta la o lucrare mai mult decat termenul lucrarii noi, aceasta primeste FirAgatat la prima
	bataie, fara sa intre in coada (un fir nu se poate opri din afara)."""

	def __init__(self, nume):
		import collections
		import queue
		self.nume = nume
		self.coada = queue.Queue()
		self.gata = collections.deque()
		self.fir = None
		self.asteapta = {}
		self.numar = 0
		self.curent = None
		self.ceas = None
		self.legatura = None

	def trimite(self, functie, dupa, termen_s):
		import threading
		self.numar += 1
		nr = self.numar
		acum = time.monotonic()
		self.asteapta[nr] = (dupa, acum + termen_s)
		curent = self.curent
		if curent is not None and acum - curent > termen_s:
			self.gata.append((nr, None, FirAgatat(self.nume)))
		else:
			self.coada.put((nr, functie))
			if self.fir is None or not self.fir.is_alive():
				self.fir = threading.Thread(target=self._lucreaza, name="HdsWebCanale-" + self.nume, daemon=True)
				self.fir.start()
		if self.ceas is None:
			from enigma import eTimer
			self.ceas = eTimer()
			self.legatura = _legaCeas(self.ceas, self._verifica)
		if not self.ceas.isActive():
			self.ceas.start(40, False)

	def _lucreaza(self):
		while True:
			nr, functie = self.coada.get()
			self.curent = time.monotonic()
			try:
				rezultat, eroare = functie(), None
			except Exception as e:
				rezultat, eroare = None, e
			self.curent = None
			self.gata.append((nr, rezultat, eroare))

	def _preda(self, dupa, rezultat, eroare):
		try:
			dupa(rezultat, eroare)
		except Exception as e:
			_jurnal("predarea unei lucrari: %s" % e)

	def _verifica(self):
		while self.gata:
			nr, rezultat, eroare = self.gata.popleft()
			x = self.asteapta.pop(nr, None)
			if x is not None:
				self._preda(x[0], rezultat, eroare)
		acum = time.monotonic()
		for nr in [n for n, (_d, termen) in self.asteapta.items() if termen <= acum]:
			dupa, _termen = self.asteapta.pop(nr)
			_jurnal("firul %s: o lucrare a depasit termenul" % self.nume)
			self._preda(dupa, None, TermenDepasit(self.nume))
		if not self.asteapta:
			self.ceas.stop()


class _Ceasuri(object):
	"""eTimer-e de o bataie; fara referinta pastrata, un eTimer e cules de GC si nu mai bate."""

	def __init__(self):
		self.vii = []

	def mai_tarziu(self, functie, ms=0):
		from enigma import eTimer
		ceas = eTimer()
		intrare = [ceas, None]

		def _bate():
			try:
				self.vii.remove(intrare)
			except ValueError:
				pass
			functie()

		intrare[1] = _legaCeas(ceas, _bate)
		self.vii.append(intrare)
		ceas.start(int(ms), True)


class _Furnizor(object):
	"""Modulele imaginii, importate abia la prima cerere."""

	def __init__(self):
		self._fire = {}
		self._ceasuri = _Ceasuri()
		self.planificator_felii = None

	@property
	def X(self):
		from Components import HdsIndexCanale
		return HdsIndexCanale

	def index(self):
		from Screens import HdsCautareCanale
		return HdsCautareCanale.index_cu_piste()

	def index_gata(self):
		"""Indexul de folosit acum, fara lucru pe firul enigma2: cel la zi; altfel porneste pregatirea in fundal (una
		singura odata, ca la ecranul de cautare) si da indexul din memorie daca e facut din fisierele de acum (lamedb,
		buchetele: canalele sunt aceleasi, numai masuratorile sau pistele sunt mai vechi). None cat nu exista niciunul."""
		from Screens import HdsCautareCanale as H
		if not getattr(H, "IN_FUNDAL", False):
			return H.index_cu_piste()
		index = H.index_la_zi()
		if index is not None:
			return index
		H.porneste_pregatirea()
		X = self.X
		return X.din_memorie(X.semnatura(X.DIRECTOR, H._pozitii_feed()))

	def multibuchet(self):
		from Components.config import config
		return bool(config.usage.multibouquet.value)

	def radio_separat(self):
		from Components.config import config
		return bool(config.usage.e1like_radio_mode.value)

	def tipuri_servicii(self, tip):
		from Screens.ChannelSelection import service_types_tv, service_types_radio
		return service_types_radio if tip == "radio" else service_types_tv

	def continut(self, ref):
		from enigma import eServiceCenter, eServiceReference
		lista = eServiceCenter.getInstance().list(eServiceReference(ref))
		if lista is None:
			return []
		return lista.getContent("SN", False) or []

	def nume(self, ref):
		from enigma import eServiceCenter, eServiceReference
		r = eServiceReference(ref)
		info = eServiceCenter.getInstance().info(r)
		return info.getName(r) if info else ""

	def director(self):
		return self.X.DIRECTOR

	def acum(self):
		return time.time()

	def epg(self, refs):
		from enigma import eEPGCache
		cerere = ["RIBDTX"]
		for r in refs:
			cerere.append((r, 0, -1))
			cerere.append((r, 1, -1))
		return eEPGCache.getInstance().lookupEvent(cerere) or []

	def ref_acum(self):
		import NavigationInstance
		nav = NavigationInstance.instance
		if nav is None:
			return None
		ref = nav.getCurrentlyPlayingServiceReference()
		return ref.toString() if ref is not None else None

	def nume_serviciu(self, ref):
		from ServiceReference import ServiceReference
		from enigma import eServiceReference
		return ServiceReference(eServiceReference(ref)).getServiceName()

	def in_standby(self):
		import Screens.Standby
		return Screens.Standby.inStandby is not None

	def lista_tv(self, tip):
		"""Radacina pe care sta acum lista de pe televizor, daca e in modul filei (altfel None)."""
		from Screens.InfoBar import InfoBar
		from Screens.ChannelSelection import MODE_RADIO
		ib = InfoBar.instance
		sl = getattr(ib, "servicelist", None) if ib is not None else None
		if sl is None or not sl.servicePath:
			return None
		if (sl.mode == MODE_RADIO) != (tip == "radio"):
			return None
		return sl.servicePath[-1].toString()

	def zap(self, ref_text, tip, ref_buchet, canal):
		"""Porneste canalul prin lista de pe televizor. -> (True, None) sau (False, motivul)."""
		from enigma import eServiceReference
		from Screens.InfoBar import InfoBar
		from Screens import ChannelSelection as CS
		ib = InfoBar.instance
		sl = getattr(ib, "servicelist", None) if ib is not None else None
		if sl is None:
			return False, _t("Lista de canale a receptorului nu e gata încă.")
		ref = eServiceReference(ref_text)
		if not ref.valid():
			return False, _t("Canalul nu are o referință bună.")
		radio = tip == "radio"
		if radio and not self.radio_separat():
			dlg = getattr(ib.session, "current_dialog", None)
			if isinstance(dlg, CS.ChannelSelectionRadio):
				return self._inListaRadio(dlg, ref, ref_buchet, canal)
			joaca = ib.session.nav.getCurrentlyPlayingServiceReference()
			if joaca is None or joaca != ref:
				ib.session.nav.playService(ref)
			return True, None
		if sl.movemode or sl.bouquet_mark_edit != CS.OFF:
			return False, _t("Lista de canale e în editare pe televizor. Închide editarea, apoi încearcă din nou.")
		if radio:
			if sl.mode != CS.MODE_RADIO:
				sl.setModeRadio()
		elif sl.mode != CS.MODE_TV:
			sl.setModeTv()
		if not self._punePeLista(sl, ref, ref_buchet, canal):
			return False, _t("Canalul nu s-a găsit în lista de pe televizor.")
		sl.zap()
		return True, None

	def _punePeLista(self, sl, ref, ref_buchet, canal):
		from enigma import eServiceReference
		if ref_buchet is None:
			if canal is None:
				return False
			sl.hdsPunePeLista(ref, canal)
		else:
			buchet = eServiceReference(ref_buchet)
			radacina = sl.getRoot()
			if radacina is None or radacina != buchet:
				sl.clearPath()
				if sl.bouquet_root != buchet:
					sl.enterPath(sl.bouquet_root)
				sl.enterPath(buchet)
			sl.setCurrentSelection(ref)
		ales = sl.getCurrentSelection()
		return ales is not None and ales.valid() and ales == ref

	def _inListaRadio(self, dlg, ref, ref_buchet, canal):
		"""Lista radio deschisa pe televizor: postul se pune in ea si porneste, ca la OK acolo."""
		from Components.config import config
		if dlg.movemode:
			return False, _t("Lista de canale e în editare pe televizor. Închide editarea, apoi încearcă din nou.")
		if not self._punePeLista(dlg, ref, ref_buchet, canal):
			return False, _t("Canalul nu s-a găsit în lista de pe televizor.")
		joaca = dlg.session.nav.getCurrentlyPlayingServiceReference()
		if joaca is None or joaca != ref:
			dlg.session.nav.playService(ref)
			config.radio.lastservice.value = ref.toString()
			config.radio.lastservice.save()
		dlg.saveRoot()
		return True, None

	def favorite(self):
		from Components import HdsFavorite
		return HdsFavorite

	def chei_favorite(self, tip):
		"""Cheile canalelor din Favorite-le filei (steluta plina)."""
		F = self.favorite()
		return F.chei(F.ref_favorite(tip))

	def pune_favorit(self, ref, tip, vrea, nume):
		"""Canalul in Favorite (vrea True) sau scos de acolo -> HdsFavorite.Rezultat."""
		return self.favorite().pune(ref, vrea, tip=tip, nume=nume)

	def lista_in_editare(self):
		"""Lista de pe televizor e in mutare sau in editarea buchetelor (tine un buchet deschis)."""
		from Screens.InfoBar import InfoBar
		from Screens import ChannelSelection as CS
		ib = InfoBar.instance
		sl = getattr(ib, "servicelist", None) if ib is not None else None
		return sl is not None and (bool(sl.movemode) or sl.bouquet_mark_edit != CS.OFF)

	def cai_sigle(self):
		"""Caile lui Renderer/Picon.py, in aceeasi ordine, cu dosarul „picon”."""
		try:
			from enigma import eEnv
			prima = eEnv.resolve("${datadir}/enigma2/picon/")
		except Exception:
			prima = "/usr/share/enigma2/picon/"
		return (prima, "/media/cf/picon/", "/media/usb/picon/")

	def mai_tarziu(self, functie, ms=0):
		self._ceasuri.mai_tarziu(functie, ms)

	def in_fir(self, functie, dupa, fel="citire", termen_s=TERMEN_CITIRE_S):
		"""Pe firul `fel` (cautarea siglelor si citirea lor au fire separate: o cautare agatata nu opreste citirile)."""
		fir = self._fire.get(fel)
		if fir is None:
			fir = self._fire[fel] = _Fir(fel)
		fir.trimite(functie, dupa, termen_s)


_FURNIZOR = []


def _m(M=None):
	if M is not None:
		return M
	if not _FURNIZOR:
		_FURNIZOR.append(_Furnizor())
	return _FURNIZOR[0]


# ---------------------------------------------------------------- memoria

_MEMORIE = {"buchete": {}, "liste": {}, "numarari": {}, "fatete": {}, "epg": {}, "sigle": None, "sigle_ora": 0.0,
	"sigle_in_curs": False, "sigle_pornit": 0.0, "sigle_octeti": {}, "canale_index": (None, None)}
MAX_FATETE = 16


def uita():
	"""Goleste toata memoria (probele)."""
	_MEMORIE.update({"buchete": {}, "liste": {}, "numarari": {}, "fatete": {}, "epg": {}, "sigle": None, "sigle_ora": 0.0,
		"sigle_in_curs": False, "sigle_pornit": 0.0, "sigle_octeti": {}, "canale_index": (None, None)})
	_IN_CURS.clear()


def uita_listele():
	"""Buchetele, listele si numararile din memorie (dupa o schimbare facuta de aici in buchete)."""
	_MEMORIE.update({"buchete": {}, "liste": {}, "numarari": {}, "fatete": {}})


def semnatura(director):
	"""Data si marimea fisierelor listelor (lamedb, bouquets.*, userbouquet.*): o lista refacuta cand se schimba."""
	rez = []
	try:
		nume = sorted(os.listdir(director))
	except OSError:
		return ()
	for n in nume:
		if n == "lamedb" or n.startswith("bouquets.") or n.startswith("userbouquet."):
			try:
				st = os.stat(os.path.join(director, n))
				rez.append((n, st.st_mtime, st.st_size))
			except OSError:
				pass
	return tuple(rez)


def _proaspat(vechi, sem, acum, viata):
	"""O intrare din memorie e buna: aceeasi semnatura si, daca `viata` nu e None, mai noua de `viata` secunde."""
	return vechi is not None and vechi[0] == sem and (viata is None or acum - vechi[1] < viata)


def gen_index(M):
	"""Indexul cautarii pentru o cerere, fara sa tina firul enigma2 cat se face (M.index_gata): pe loc cand exista unul
	pentru fisierele de acum, altfel dupa pregatirea in fundal, asteptata cu pauze de ASTEAPTA_INDEX_MS (termenul
	cererii ramane TERMEN_S). Furnizorii falsi ai probelor de pe PC au numai index()."""
	gata = getattr(M, "index_gata", None)
	if gata is None:
		index = M.index()
		yield
		return index
	while True:
		index = gata()
		if index is not None:
			return index
		yield ASTEAPTA_INDEX_MS


def gen_canale_index(index):
	"""({cheie: Canal}, {"tv": n, "radio": n}) din indexul cautarii, facute o data pe index, pe pasi."""
	vechi_index, rez = _MEMORIE["canale_index"]
	if vechi_index is index and rez is not None:
		return rez

	def fa():
		harta = {}
		numar = {"tv": 0, "radio": 0}
		for i, c in enumerate(index.canale):
			if i % UNITATE == UNITATE - 1:
				yield
			k = c.cheie_mas or c.ref
			if k not in harta:
				harta[k] = c
			numar["radio" if c.radio else "tv"] += 1
		_MEMORIE["canale_index"] = (index, (harta, numar))
		return harta, numar

	return (yield from gen_unul_pe_fel(("index", id(index)), fa))


# ---------------------------------------------------------------- construirea listelor (generatoare, pe felii)
# Fiecare bucla peste randuri cedeaza dupa cel mult UNITATE intrari: o felie se opreste la BUGET_S, dar un singur pas
# nu se poate taia (pe receptor Python e de cateva ori mai incet decat pe PC).

class Rand(object):
	__slots__ = ("k", "ref", "nume", "cheie_nume", "n", "marcaj", "canal", "epg", "sigla")

	def __init__(self, k, ref, nume, X, n=None, marcaj=False, canal=None):
		self.k = k
		self.ref = ref
		self.nume = nume
		self.cheie_nume = X.normalizeaza(nume)
		self.n = n
		self.marcaj = marcaj
		self.canal = canal
		self.epg = None if marcaj else ref_epg(ref)
		self.sigla = None if marcaj else nume_sigla(ref)


class Lista(object):
	"""O lista aleasa (un buchet sau TOATE), construita rand cu rand (adauga), cu cautarile ei gata facute."""

	def __init__(self, tip, id_, nume, ref_buchet, index):
		self.tip = tip
		self.id = id_
		self.nume = nume
		self.ref_buchet = ref_buchet
		self.index = index
		self.randuri = []
		self.dupa_ref = {}
		self.dupa_cheie = {}
		self.poz_cheie = {}
		self.canale = 0
		self.refs_epg = set()
		self.grupe = None       # [(cheia grupei, numele, [randuri])], facute o data (gen_grupe)

	def adauga(self, r):
		if not r.marcaj:
			self.dupa_ref.setdefault(r.ref, r)
			self.dupa_cheie.setdefault(r.k, r)
			self.poz_cheie.setdefault(r.k, len(self.randuri))
			self.canale += 1
			if r.epg:
				self.refs_epg.add(r.epg)
		self.randuri.append(r)


def _radacina(M, tip):
	if M.multibuchet():
		return '1:7:1:0:0:0:0:0:0:0:FROM BOUQUET "bouquets.%s" ORDER BY bouquet' % tip
	return '%s FROM BOUQUET "userbouquet.favourites.%s" ORDER BY bouquet' % (M.tipuri_servicii(tip), tip)


def id_buchet(ref, loc):
	"""Id-ul unui buchet in pagina: fisierul lui, sau „b<locul in radacina>” pentru unul fara fisier."""
	return fisier_buchet(ref) or ("b%d" % loc)


def gen_surse(M, tip):
	"""Buchetele filei ca pe televizor, [(ref, nume)]: cu „mai multe buchete”, dosarele din bouquets.tv|radio; altfel
	numai radacina cu Favorite."""
	radacina = _radacina(M, tip)
	if not M.multibuchet():
		# ca pe televizor, unde „Sateliți” are dosarele lor: buchetele DAB+ (Radio) / DVB-T2 (TV) din satelit, cand
		# exista si sunt trecute in bouquets.* (HdsIndexCanale.buchete_fluxuri)
		surse = [(radacina, M.nume(radacina))]
		for ref, nume in surse_fluxuri(M, tip):
			surse.append((ref, nume))
		return surse
	surse = []
	for i, (ref, nume) in enumerate(M.continut(radacina)):
		if i % UNITATE == UNITATE - 1:
			yield
		if steaguri(ref) & DOSAR:
			surse.append((ref, nume))
	return surse


def surse_fluxuri(M, tip):
	"""[(ref, nume)] ale buchetelor DAB+ / DVB-T2 din satelit care se pot deschide in fila `tip`."""
	X = M.X
	f = getattr(X, "buchete_fluxuri", None)
	if f is None:
		return []
	try:
		return [(X.ref_buchet_flux(fisier), X.nume_buchet_flux(fel)) for fel, fisier in f(tip, M.director())]
	except Exception as e:
		_jurnal("buchetele DAB+ / DVB-T2: %s" % e)
		return []


def fel_buchet_gol(M, lista):
	"""'dab' / 't2' cand lista aleasa e buchetul DAB+ / DVB-T2 din satelit si nu are niciun post, altfel None."""
	if lista is None or lista.canale or not lista.ref_buchet:
		return None
	f = getattr(M.X, "fel_buchet_flux", None)
	return f(lista.ref_buchet) if f is not None else None


def gen_buchete(M, tip, viata=VIATA_LISTA_S):
	"""Buchetele filei, cu continutul si numerele lor, ca lista de pe televizor. Memorie pana se schimba fisierele si,
	daca `viata` nu e None, cel mult `viata` secunde (o lista editata pe televizor e in memorie inainte sa fie scrisa)."""
	sem = (semnatura(M.director()), M.multibuchet())
	vechi = _MEMORIE["buchete"].get(tip)
	if _proaspat(vechi, sem, M.acum(), viata):
		return vechi[2]
	return (yield from gen_unul_pe_fel(("buchete", tip), lambda: _gen_construieste_buchete(M, tip, sem)))


def _gen_construieste_buchete(M, tip, sem):
	surse = yield from gen_surse(M, tip)
	yield
	buchete = []
	numar = 0
	for i, (ref, nume) in enumerate(surse):
		intrari = []
		canale = 0
		for j, (r, n) in enumerate(M.continut(ref)):
			if j % UNITATE == UNITATE - 1:
				yield
			f = steaguri(r)
			if f & DOSAR and not f & MARCAJ:
				continue
			marcaj = bool(f & MARCAJ)
			if not marcaj:
				numar += 1
				canale += 1
			intrari.append((r, curat(n) or "?", None if marcaj else numar, marcaj))
		id_ = id_buchet(ref, i)
		nume_b = curat(fara_mod(curat(nume)))
		if nume_b == "Favourites":
			nume_b = _t("Favourites")
		buchete.append({"id": id_, "nume": nume_b or id_, "ref": ref, "intrari": intrari, "numar": canale})
		yield
	_MEMORIE["buchete"][tip] = (sem, M.acum(), buchete)
	return buchete


def gen_lista(M, tip, id_, viata=VIATA_LISTA_S):
	"""Lista aleasa (un buchet sau TOATE) -> Lista, sau None daca nu exista in fila. `viata` None: lista din memorie
	oricat de veche, cat timp fisierele nu s-au schimbat (paginile urmatoare ale aceleiasi liste)."""
	index = yield from gen_index(M)
	sem = (semnatura(M.director()), M.multibuchet(), id(index))
	vechi = _MEMORIE["liste"].get((tip, id_))
	if _proaspat(vechi, sem, M.acum(), viata):
		return vechi[2]
	return (yield from gen_unul_pe_fel(("lista", tip, id_),
		lambda: _gen_construieste_lista(M, tip, id_, index, sem, viata)))


def _gen_construieste_lista(M, tip, id_, index, sem, viata):
	X = M.X
	if id_ == TOATE:
		lista = Lista(tip, TOATE, _t("Toate canalele"), None, index)
		radio = tip == "radio"
		for i, c in enumerate(index.canale):
			if i % UNITATE == UNITATE - 1:
				yield
			if bool(c.radio) == radio:
				lista.adauga(Rand(c.cheie_mas or c.ref, c.ref, curat(c.nume_afisat() if hasattr(c, "nume_afisat") else c.nume) or "?", X, canal=c))
	else:
		buchete = yield from gen_buchete(M, tip, viata)
		gasit = None
		for b in buchete:
			if b["id"] == id_:
				gasit = b
				break
		if gasit is None:
			return None
		harta, _numar = yield from gen_canale_index(index)
		lista = Lista(tip, id_, gasit["nume"], gasit["ref"], index)
		for i, (ref, nume, n, marcaj) in enumerate(gasit["intrari"]):
			if i % UNITATE == UNITATE - 1:
				yield
			if marcaj:
				lista.adauga(Rand("", ref, nume, X, marcaj=True))
			else:
				k = X.cheie_din_ref(ref) or ref
				lista.adauga(Rand(k, ref, nume, X, n=n, canal=harta.get(k)))
	liste = _MEMORIE["liste"]
	liste[(tip, id_)] = (sem, M.acum(), lista)
	while len(liste) > MAX_LISTE:
		cea_mai_veche = min(liste, key=lambda k: liste[k][1])
		del liste[cea_mai_veche]
	return lista


def gen_numarare(M, lista):
	"""Grupele de filtre ale listei alese: optiunile indexului, cu numarul de canale DIN LISTA (fix, ca pe televizor:
	nu depinde de ce e ales). Grupele cu o singura optiune nu se arata (cele ale pistelor de la una)."""
	X = M.X
	index = lista.index
	cheie = (lista.tip, lista.id, id(index), index.masurari_marcaj[1], index.piste_aplicate)
	vechi = _MEMORIE["numarari"].get((lista.tip, lista.id))
	if vechi is not None and vechi[0] == cheie and vechi[1] is lista:
		return vechi[2]
	return (yield from gen_unul_pe_fel(("numarare", lista.tip, lista.id, id(lista)),
		lambda: _gen_numara(X, lista, cheie)))


def _gen_numara(X, lista, cheie):
	index = lista.index
	pe_masca = [{} for _g in X.GRUPURI]
	grupe = range(len(X.GRUPURI))
	vazute = set()
	for j, r in enumerate(lista.randuri):
		if j % UNITATE == UNITATE - 1:
			yield
		c = r.canal
		if c is None or id(c) in vazute:
			continue
		vazute.add(id(c))
		masti = c.masti
		for i in grupe:
			m = masti[i]
			if m:
				d = pe_masca[i]
				d[m] = d.get(m, 0) + 1
	grupuri = []
	for i, g in enumerate(X.GRUPURI):
		optiuni = []
		for v, eticheta, _n in index.optiuni.get(g, ()):
			bit = index.biti[g].get(v, 0)
			n = sum(k for m, k in pe_masca[i].items() if m & bit)
			if n:
				optiuni.append((v, eticheta, n))
		prag = 1 if g in X.GRUPURI_PISTE else 2
		if len(optiuni) >= prag:
			titlu = X.semnPiste(X.titlu(g)) if g in X.GRUPURI_PISTE else X.titlu(g)
			grupuri.append((g, titlu, optiuni))
		yield
	_MEMORIE["numarari"][(lista.tip, lista.id)] = (cheie, lista, grupuri)
	return grupuri


def gen_fatete(M, lista, grupuri, sel, text="", X=None):
	"""Numerele optiunilor cu filtrele alese (numaratoarea „fatetata”, HdsIndexCanale.Index.numara_fatetat_treptat):
	optiunea X din grupa G = canalele listei care au X si trec de toate celelalte grupe alese (in G insasi optiunile se
	aduna cu „sau”), adica cate canale ar ramane cu X bifat; cu un nume cautat, numai printre canalele listei care se
	potrivesc cu el (aceeasi regula ca gen_filtreaza); fara nimic bifat si fara text, numerele de pe toata lista.
	Optiunile si grupele raman cele ale listei (o optiune cu 0 se vede, estompata in pagina). Memorie pe (lista,
	selectie, text)."""
	q = X.normalizeaza(text or "") if X is not None else ""
	if not sel and not q:
		return grupuri
	index = lista.index
	cheie = (id(lista), index.masurari_marcaj[1], index.piste_aplicate, q,
		tuple(sorted((g, tuple(sorted(map(str, v)))) for g, v in sel.items())))
	mem = _MEMORIE["fatete"]
	vechi = mem.get(cheie)
	if vechi is not None and vechi[0] is lista:
		return vechi[1]
	canale = getattr(lista, "canale_unice", None) if not q else None
	if q:
		# canalele listei care se potrivesc cu numele cautat (randurile, ca gen_filtreaza), fiecare o data
		canale, vazute = [], set()
		for j, r in enumerate(lista.randuri):
			if j % UNITATE == UNITATE - 1:
				yield
			c = r.canal
			if c is None or r.marcaj or id(c) in vazute:
				continue
			if q in r.cheie_nume or (getattr(c, "alte", None) and c.se_potriveste(q)):
				vazute.add(id(c))
				canale.append(c)
	elif canale is None:
		canale, vazute = [], set()
		for j, r in enumerate(lista.randuri):
			if j % UNITATE == UNITATE - 1:
				yield
			c = r.canal
			if c is not None and id(c) not in vazute:
				vazute.add(id(c))
				canale.append(c)
		lista.canale_unice = canale
	numere = yield from index.numara_fatetat_treptat(canale, sel, UNITATE)
	rez = [(g, titlu, [(v, e, numere.get(g, {}).get(v, 0)) for v, e, _n in optiuni]) for g, titlu, optiuni in grupuri]
	mem[cheie] = (lista, rez)
	while len(mem) > MAX_FATETE:
		del mem[next(iter(mem))]
	return rez


def selectie(argumente_, grupuri):
	"""{grup: set(valori)} numai cu valorile care exista in grupele listei (o valoare necunoscuta se ignora)."""
	sel = {}
	for g, _titlu, optiuni in grupuri:
		text = argumente_.get(g)
		if not text:
			continue
		existente = dict((str(v), v) for v, _e, _n in optiuni)
		for bucata in text.split(",")[:64]:
			v = existente.get(bucata.strip())
			if v is not None:
				sel.setdefault(g, set()).add(v)
	return sel


def gen_filtreaza(lista, text, sel, X, cheie_acum=None):
	"""-> (randurile care se potrivesc, cate canale sunt intre ele, locul primului rand cu `cheie_acum` sau -1).
	Fara text si filtre: toata lista, cu marcajele. Numele se cauta in numele aratat in rand (fara diacritice, spatii,
	semne): intai cele care incep cu textul, apoi celelalte, fiecare in ordinea listei. Filtrele: prin indexul cautarii
	(aceleasi reguli ca pe televizor); un rand fara canal in index nu trece de filtre."""
	q = X.normalizeaza(text or "")
	if not q and not sel:
		return lista.randuri, lista.canale, (lista.poz_cheie.get(cheie_acum, -1) if cheie_acum else -1)
	voie = None
	if sel:
		potrivite = lista.index.filtreaza("", sel)
		yield
		voie = set()
		for i, c in enumerate(potrivite):
			if i % UNITATE == UNITATE - 1:
				yield
			voie.add(id(c))
	inceput, rest = [], []
	acum_inceput = acum_rest = -1
	for poz, r in enumerate(lista.randuri):
		if poz % UNITATE == UNITATE - 1:
			yield
		if r.marcaj:
			continue
		if voie is not None and (r.canal is None or id(r.canal) not in voie):
			continue
		if q:
			if q in r.cheie_nume:
				unde = inceput if r.cheie_nume.startswith(q) else rest
			else:
				# posturile DAB+ / DVB-T2 din satelit se gasesc si dupa fel („DAB+”, „DVB-T2”) si dupa ansamblu, ca pe
				# televizor (HdsIndexCanale.Canal.rang)
				alte = getattr(r.canal, "alte", None) if r.canal is not None else None
				if not alte or not r.canal.se_potriveste(q):
					continue
				unde = inceput if [a for a in alte if a.startswith(q)] else rest
		else:
			unde = inceput
		if cheie_acum and r.k == cheie_acum:
			if unde is inceput and acum_inceput < 0:
				acum_inceput = len(inceput)
			elif unde is rest and acum_rest < 0:
				acum_rest = len(rest)
		unde.append(r)
	gasite = inceput + rest
	if acum_inceput >= 0:
		acum_poz = acum_inceput
	elif acum_rest >= 0:
		acum_poz = len(inceput) + acum_rest
	else:
		acum_poz = -1
	return gasite, len(gasite), acum_poz


# ---------------------------------------------------------------- „Toate canalele” pe grupe, ca lista de pe televizor
# Fara text si fara filtre, „Toate canalele” se arata ca lista „Sateliți” de pe televizor (Screens/ChannelSelection.py,
# hdsUmpleSateliti): un rand-antet pe loc (cablul, terestrul, apoi satelitii de la vest la est), deschis sau inchis, cu
# numarul de canale; dupa ele posturile DVB-T2 / DAB+ din satelit (pe televizor: dosarele lor, dupa sateliti) si, la
# urma, ce nu are loc (fluxurile de internet). Cererea grupe=1 da antetele; grupa=<cheie> da randurile unei grupe, pe
# pagini. Pagina deschide grupa canalului de pe televizor si cere celelalte in fundal.
GRUPA_ALTE = "alte"


def cheie_grupa(c):
	"""Grupa unui canal din indexul cautarii: locul lui ("cablu", "terestru" sau pozitia satelitului, ca text),
	"dab" / "t2" pentru posturile din satelit ale releelor, GRUPA_ALTE pentru restul."""
	if c is None:
		return GRUPA_ALTE
	tip = getattr(c, "tip", None)
	if tip in ("dab", "t2"):
		return tip
	poz = getattr(c, "poz", None)
	if poz is None or poz == "":
		return GRUPA_ALTE
	return str(poz)


def ordine_grupa(cheie, X):
	"""Locul grupei in pagina: cablul, terestrul, satelitii de la vest la est (ca pe televizor), DVB-T2, DAB+, restul."""
	if cheie == X.POZ_CABLU:
		return (0, 0)
	if cheie == X.POZ_TERESTRU:
		return (1, 0)
	if cheie == "t2":
		return (3, 0)
	if cheie == "dab":
		return (4, 0)
	try:
		poz = int(cheie)
	except (TypeError, ValueError):
		return (5, 0)
	return (2, poz - 3600 if poz > 1800 else poz)


def nume_grupa(cheie, c, X):
	if cheie in ("dab", "t2"):
		return X.nume_buchet_flux(cheie)
	if cheie == GRUPA_ALTE or c is None:
		return _t("Alte canale")
	return X.text_pozitie(c.poz) or cheie


def gen_grupe(lista, X):
	"""Grupele listei (numai „Toate canalele”), facute o data pe lista: [(cheie, nume, [randuri])], in ordinea paginii."""
	if lista.grupe is not None:
		return lista.grupe
	pe_cheie = {}
	primul = {}
	for i, r in enumerate(lista.randuri):
		if i % UNITATE == UNITATE - 1:
			yield
		if r.marcaj:
			continue
		k = cheie_grupa(r.canal)
		pe_cheie.setdefault(k, []).append(r)
		primul.setdefault(k, r.canal)
	lista.grupe = [(k, nume_grupa(k, primul[k], X), pe_cheie[k]) for k in sorted(pe_cheie, key=lambda k: ordine_grupa(k, X))]
	return lista.grupe


def filtreaza(lista, text, sel, X):
	"""Randurile care se potrivesc (gen_filtreaza), fara pauze."""
	return ruleaza_tot(gen_filtreaza(lista, text, sel, X))[0]


# ---------------------------------------------------------------- cererile

def argumente(request):
	"""Argumentele cererii ca text scurt: {cheie: text}, fara token; cheile numai litere mici si „_”."""
	rez = {}
	for cheie, valori in list((getattr(request, "args", None) or {}).items())[:24]:
		if isinstance(cheie, bytes):
			cheie = cheie.decode("utf-8", "replace")
		if cheie == "token" or not re.match(r"^[a-z_]{1,12}$", cheie):
			continue
		v = (valori or [b""])[0]
		if isinstance(v, bytes):
			v = v.decode("utf-8", "replace")
		rez[cheie] = str(v)[:(MAX_EPG * 80 if cheie == "refs" else MAX_REF)].strip()
	return rez


def _tip(argumente_):
	tip = argumente_.get("fila") or "tv"
	return tip if tip in TIPURI else None


def _intreg(text, implicit, minim, maxim):
	try:
		return max(minim, min(maxim, int(text)))
	except (TypeError, ValueError):
		return implicit


def _ora(t):
	try:
		return time.strftime("%H:%M", time.localtime(int(t)))
	except (TypeError, ValueError, OverflowError, OSError):
		return ""


def _dinMemorieEpg(titlu):
	"""titlul tradus de traducerea ghidului, numai din memorie (nicio cerere noua), sau titlul"""
	try:
		from Components import HdsTraducereEpg
		return curat(HdsTraducereEpg.dinMemorie("titlu", titlu), MAX_TITLU) or titlu
	except Exception:
		return titlu


def _emisiune(tupla):
	"""(R, I, B, D, T) din lookupEvent -> {"t", "i", "d", "o"} sau None."""
	if not tupla or len(tupla) < 5 or tupla[2] is None or tupla[3] is None:
		return None
	titlu = curat(tupla[4], MAX_TITLU)
	if not titlu:
		return None
	return {"t": _dinMemorieEpg(titlu), "i": int(tupla[2]), "d": int(tupla[3]), "o": _ora(tupla[2])}


def _acum(M):
	"""Canalul de pe televizor: cheia lui (ca randurile) si numele."""
	ref = None
	try:
		ref = M.ref_acum()
	except Exception as e:
		_jurnal("canalul de acum: %s" % e)
	if not ref:
		return {"ref": None, "cheie": None, "nume": ""}
	try:
		nume = curat(M.nume_serviciu(ref))
	except Exception:
		nume = ""
	return {"ref": ref, "cheie": M.X.cheie_din_ref(ref) or ref, "nume": nume}


def _transmise(M):
	"""Cheile (ca ale randurilor) canalelor transmise acum in retea, spre un browser sau un player extern
	(Components/HdsTransmisie.py, Manager.transmise: aceleasi inregistrari care cedeaza la zap, deci acelasi semn ca
	in lista de pe televizor). [] cand nu se poate afla."""
	try:
		from Components import HdsTransmisie
		refs = HdsTransmisie.manager().transmise()
	except Exception:
		return []
	rez = set()
	for r in refs:
		try:
			rez.add(M.X.cheie_din_ref(r) or r)
		except Exception:
			rez.add(r)
	return sorted(rez)


def _cautaSigle(cai):
	"""Pe fir: fisierele .png din caile siglelor (prima cale care are numele castiga, ca in Picon.findPicon)."""
	gasite = {}
	for d in cai:
		try:
			nume = os.listdir(d)
		except OSError:
			continue
		for n in nume:
			if n.endswith(".png") and _NUME_SIGLA.match(n[:-4]) and n[:-4] not in gasite:
				gasite[n[:-4]] = os.path.join(d, n)
	return gasite


def porneste_cautarea_siglelor(M):
	"""Cauta siglele pe disc pe firul „cautare”, cel mult o cautare deodata. O cautare cazuta sau peste termen lasa
	siglele de dinainte (sau niciuna); se reincearca dupa VIATA_SIGLE_S."""
	if _MEMORIE["sigle_in_curs"]:
		return
	_MEMORIE["sigle_in_curs"] = True
	_MEMORIE["sigle_pornit"] = time.monotonic()

	def gata(rezultat, eroare):
		_MEMORIE["sigle_in_curs"] = False
		if eroare is not None:
			_jurnal("cautarea siglelor: %s %s" % (eroare.__class__.__name__, eroare))
			rezultat = _MEMORIE["sigle"]
		else:
			_MEMORIE["sigle_octeti"] = {}
		_MEMORIE["sigle"] = rezultat or {}
		_MEMORIE["sigle_ora"] = M.acum()

	cai = tuple(M.cai_sigle())
	M.in_fir(lambda: _cautaSigle(cai), gata, fel="cautare", termen_s=TERMEN_CAUTARE_S)


def gen_sigle(M):
	"""Siglele stiute. Se asteapta numai prima cautare, cel mult ASTEAPTA_SIGLE_S de la pornirea ei; dupa aceea cererile
	merg fara sigle pana vine rezultatul (o montare moarta nu mai intarzie fiecare cerere). O reimprospatare dupa
	VIATA_SIGLE_S nu se asteapta: raman siglele de dinainte."""
	if _MEMORIE["sigle"] is None or M.acum() - _MEMORIE["sigle_ora"] >= VIATA_SIGLE_S:
		porneste_cautarea_siglelor(M)
	while (_MEMORIE["sigle"] is None and _MEMORIE["sigle_in_curs"]
			and time.monotonic() - _MEMORIE["sigle_pornit"] < ASTEAPTA_SIGLE_S):
		yield 50
	return _MEMORIE["sigle"] or {}


LA_FIR = object()


def cere_sigla(M, nume, dupa):
	"""Octetii siglei `nume` (una gasita de cautare). -> octetii pe loc (din memorie), None (necunoscuta), sau LA_FIR:
	citirea merge pe firul "citire" si raspunsul vine prin dupa(octeti sau None), pe firul enigma2."""
	sigle = _MEMORIE["sigle"] or {}
	if not _NUME_SIGLA.match(nume or "") or nume not in sigle:
		return None
	octeti = _MEMORIE["sigle_octeti"].get(nume)
	if octeti is not None:
		return octeti
	cale = sigle[nume]

	def citeste():
		with open(cale, "rb") as f:
			return f.read(MAX_SIGLA + 1)

	def gata(rezultat, eroare):
		if eroare is not None or not rezultat or len(rezultat) > MAX_SIGLA:
			dupa(None)
			return
		memorie = _MEMORIE["sigle_octeti"]
		if len(memorie) >= MAX_SIGLE_MEMORIE:
			memorie.pop(next(iter(memorie)))
		memorie[nume] = rezultat
		dupa(rezultat)

	M.in_fir(citeste, gata, fel="citire", termen_s=TERMEN_CITIRE_S)
	return LA_FIR


def gen_buchete_raspuns(argumente_, M=None):
	"""GET /api/canale-buchete -> (cod, corp)."""
	M = _m(M)
	tip = _tip(argumente_)
	if tip is None:
		return 400, {"result": False, "message": _t("Fila se alege cu tv sau radio.")}
	buchete = yield from gen_buchete(M, tip)
	index = yield from gen_index(M)
	harta, numar = yield from gen_canale_index(index)
	toate = numar[tip]
	acum = _acum(M)
	# satelitul canalului de pe televizor (valoarea lui din grupa "poz" a filtrelor): pagina deschide "Toate canalele" pe
	# el, ca prima pagina sa vina repede, iar restul listei se cere in fundal
	c_acum = harta.get(acum["cheie"]) if acum["cheie"] else None
	poz_acum = getattr(c_acum, "poz", None) if c_acum is not None and bool(c_acum.radio) == (tip == "radio") else None
	ales = None
	try:
		pe_tv = M.lista_tv(tip)
	except Exception as e:
		_jurnal("lista de pe televizor: %s" % e)
		pe_tv = None
	if pe_tv:
		fisier = fisier_buchet(pe_tv)
		for b in buchete:
			if fisier and fisier_buchet(b["ref"]) == fisier:
				ales = b["id"]
				break
		if ales is None and pe_tv.startswith(M.tipuri_servicii(tip) + " ORDER BY name"):
			ales = TOATE       # lista „Toate” de pe televizor (ChannelSelection.showAllServices)
	if ales is None and acum["cheie"]:
		X = M.X
		for b in buchete:
			for j, x in enumerate(b["intrari"]):
				if j % UNITATE == UNITATE - 1:
					yield
				if not x[3] and (X.cheie_din_ref(x[0]) or x[0]) == acum["cheie"]:
					ales = b["id"]
					break
			if ales is not None:
				break
			yield
	if ales is None:
		# canalul de pe televizor nu e in niciun buchet: lista intreaga, prima din pagina (ordineWeb)
		ales = TOATE
	lista = ordineWeb([{"id": b["id"], "nume": b["nume"], "numar": b["numar"]} for b in buchete], toate)
	return 200, {"result": True, "tip": tip, "buchete": lista, "ales": ales, "multibuchet": bool(M.multibuchet()),
		"poz_acum": str(poz_acum) if poz_acum not in (None, "") else None}


# ordinea listelor in caseta de alegere a paginii: DVB-T2 din satelit dupa canalele obisnuite, fiindca
# se folosesc mai rar; Favorite la urma; la fel la radio:
# "Toate canalele", buchetele omului, posturile din satelit ale releelor (DVB-T2, DAB+), Favorite. Numai ordinea din
# pagina: bouquets.tv / bouquets.radio raman neatinse, deci numerele telecomenzii de pe televizor nu se schimba.
BUCHETE_RELEE = ("userbouquet.hds_t2.tv", "userbouquet.hds_dab.radio")


def ordineWeb(buchete, toate):
	def loc(b):
		if b["id"] in BUCHETE_RELEE:
			return 2
		if b["id"].startswith("userbouquet.favourites."):
			return 3
		return 1
	return [{"id": TOATE, "nume": _t("Toate canalele"), "numar": toate}] + sorted(buchete, key=loc)


def _cheiFavorite(M, tip):
	"""Cheile canalelor din Favorite-le filei; fara ele (o eroare) niciun rand nu are steluta plina."""
	try:
		return M.chei_favorite(tip)
	except Exception as e:
		_jurnal("Favorite: %s" % e)
		return set()


def _semne(c, X):
	"""Semnele randului (rezolutia, accesul, felul, ansamblul), ca text; "" pentru un rand fara canal in index."""
	if c is None:
		return ""
	fel = X.ETICHETA_TIP.get(c.tip, "") if c.tip not in ("tv", "radio") else ""
	# la posturile DAB+ / DVB-T2 din satelit si ansamblul (numele marcajului din buchet), ca in cautarea de pe TV
	return " · ".join(x for x in (c.rez_eticheta, c.eticheta_acces(), fel, getattr(c, "ansamblu", "")) if x)


def _rand_json(r, sigle, X, favorite=None, deosebire=""):
	if r.marcaj:
		return {"m": 1, "nume": r.nume}
	d = {"k": r.k, "ref": r.ref, "nume": r.nume}
	if favorite and r.k in favorite:
		d["f"] = 1
	if r.n is not None:
		d["n"] = r.n
	if r.epg:
		d["e"] = r.epg
	if r.sigla and sigle and r.sigla in sigle:
		d["s"] = r.sigla
	semne = _semne(r.canal, X)
	if semne:
		d["semne"] = semne
	if deosebire:
		d["d"] = deosebire
	dvbi = _eticheta_dvbi(r.ref)
	if dvbi:
		d["dvbi"] = dvbi
	return d


def N_(text):
	"""Marcaj pentru xgettext (po/Makefile.am, --keyword=N_), fara efect: textele se traduc la folosire, cu _t."""
	return text


_ETICHETE_DVBI = {"oprit_tara": N_("oprit în țara ta"), "adresa_moarta": N_("adresă moartă"), "nu_raspunde": N_("nu "
	"răspunde")}


def _eticheta_dvbi(ref):
	"""Eticheta DVB-I a randului, ca in lista de pe televizor (Components/ServiceList.hdsEticheteDvbI):
	"DVB-I" la canalul de satelit care are si varianta de internet; la canalul DVB-I, starea incercarii din casa cand nu
	merge. "" altfel."""
	if not ref:
		return ""
	try:
		from Components import HdsDvbIDate as DD
	except Exception:
		return ""
	if DD.legaturaRef(ref) is not None:
		return "DVB-I"
	url = DD.urlDinRef(ref)
	if url and DD.canalUrl(url) is not None:
		return _t(_ETICHETE_DVBI.get(DD.stareUrl(url)[0], ""))
	return ""


def gen_deosebiri(randuri, X):
	"""Ce deosebeste randurile care arata la fel (acelasi nume si aceleasi semne; pozitia nu se vede in rand, deci intra
	printre deosebiri): HdsIndexCanale.deosebiri_treptat pe toate randurile gasite, in pasi de UNITATE. -> {id(rand):
	text}."""
	f = getattr(X, "deosebiri_treptat", None)
	if f is None:
		return {}
	return (yield from f(randuri, nume=lambda r: r.cheie_nume, vizibil=lambda r: (r.nume, _semne(r.canal, X)),
		canal=lambda r: None if r.marcaj else r.canal, pas=UNITATE))


def gen_lista_raspuns(argumente_, M=None):
	"""GET /api/canale-lista -> (cod, corp)."""
	M = _m(M)
	X = M.X
	tip = _tip(argumente_)
	if tip is None:
		return 400, {"result": False, "message": _t("Fila se alege cu tv sau radio.")}
	id_ = argumente_.get("buchet") or TOATE
	if id_ != TOATE and not _ID_BUCHET.match(id_):
		return 400, {"result": False, "message": _t("Lista aleasă nu există pe receptor."), "camp": "buchet"}
	de_la = _intreg(argumente_.get("de_la"), 0, 0, 1000000)
	grupa = argumente_.get("grupa") or None
	cate = _intreg(argumente_.get("cate"), IMPLICIT_PAGINA, 1, MAX_PAGINA_GRUPA if grupa else MAX_PAGINA)
	# prima pagina: lista proaspata (cel mult VIATA_LISTA_S); paginile urmatoare si randurile unei grupe: aceeasi lista
	# cat timp fisierele nu s-au schimbat, oricat de veche (derularea si deschiderea grupelor nu refac lista)
	lista = yield from gen_lista(M, tip, id_, VIATA_LISTA_S if de_la == 0 and not grupa else None)
	if lista is None:
		return 404, {"result": False, "message": _t("Lista aleasă nu există pe receptor. Reîncarcă pagina."),
			"camp": "buchet"}
	grupuri = yield from gen_numarare(M, lista)
	sigle = yield from gen_sigle(M)
	text = (argumente_.get("text") or "")[:MAX_TEXT]
	sel = selectie(argumente_, grupuri)
	acum = _acum(M)
	pe_grupe = lista.id == TOATE and not X.normalizeaza(text) and not sel
	if pe_grupe and argumente_.get("grupe") == "1":
		return 200, (yield from gen_antete(M, X, lista, tip, acum, grupuri, sel))
	if de_la == 0 and not grupa:
		# numerele din pagina: cate canale ar ramane cu fiecare optiune bifata, tinand cont de celelalte grupe alese
		grupuri = yield from gen_fatete(M, lista, grupuri, sel, text, X)
	if grupa is not None:
		if not pe_grupe:
			return 400, {"result": False, "message": _t("Grupele sunt numai în Toate canalele, fără căutare și fără filtre."),
				"camp": "grupa"}
		grupe = yield from gen_grupe(lista, X)
		gasite = next((randuri for k, _n, randuri in grupe if k == grupa), [])
		canale = len(gasite)
		acum_poz = next((i for i, r in enumerate(gasite) if acum["cheie"] and r.k == acum["cheie"]), -1)
	else:
		gasite, canale, acum_poz = yield from gen_filtreaza(lista, text, sel, X, acum["cheie"])
	bucata = gasite[de_la:de_la + cate]
	favorite = _cheiFavorite(M, tip)
	deosebiri = yield from gen_deosebiri(gasite, X)
	randuri = []
	for i, r in enumerate(bucata):
		if i % UNITATE == UNITATE - 1:
			yield
		randuri.append(_rand_json(r, sigle, X, favorite, deosebiri.get(id(r), "")))
	if canale == 0:
		text_gasite = _t("Niciun canal găsit")
	else:
		# un singur text cu plural (formele fiecarei limbi), nu numarul lipit de un cuvant tradus separat
		text_gasite = ngettext("%d canal găsit", "%d canale găsite", canale, X) % canale
	corp = {
		"result": True,
		"tip": tip,
		"buchet": lista.id,
		"nume": lista.nume,
		"total": len(gasite),
		"canale": canale,
		"numar": X.text_numar(canale),
		"gasite": text_gasite,
		"de_la": de_la,
		"randuri": randuri,
		"gata": de_la + len(bucata) >= len(gasite),
		"acum": acum,
		"acum_poz": acum_poz,
		"transmise": _transmise(M),
		"ora": int(M.acum()),
	}
	if grupa is not None:
		corp["grupa"] = grupa
		return 200, corp
	gol = fel_buchet_gol(M, lista) if de_la == 0 else None
	if gol is not None:
		# buchetul DAB+ / DVB-T2 din satelit gol: ce e, cum se umple si drumul spre cautare (pagina de scanare)
		corp["gol_text"] = X.text_buchet_gol(gol, cuOk=False)
		corp["gol_legatura"] = "/scanare/satelit/dab" if gol == "dab" else "/scanare/satelit/dvbt2"
	if de_la == 0:
		corp["grupuri"] = _grupuri_json(grupuri, sel, X)
		if lista.id != TOATE and X.normalizeaza(text):
			toate = yield from gen_lista(M, tip, TOATE)
			if toate is not None:
				_gasite, corp["in_toate"], _poz = yield from gen_filtreaza(toate, text, sel, X)
	return 200, corp


def _grupuri_json(grupuri, sel, X):
	return [{"g": g, "titlu": titlu, "piste": g in X.GRUPURI_PISTE,
		"optiuni": [{"v": str(v), "eticheta": e, "n": n, "ales": v in sel.get(g, ())} for v, e, n in optiuni]}
		for g, titlu, optiuni in grupuri]


def grupe_neprinse(chei):
	"""Cheile grupelor de satelit (pozitia ca text) pe care acest receptor n-a prins niciodata semnal
	(Components/HdsIstoricSemnal.py), ca semnul de pe antetul din lista Sateliti de pe televizor
	(Screens/ChannelSelection.hds_text_antet). Multime goala cand istoricul e gol sau nu se poate citi."""
	try:
		from Components import HdsIstoricSemnal
		ist = HdsIstoricSemnal.istoric()
	except Exception:
		return set()
	rez = set()
	for k in chei:
		try:
			if ist.prinsa(int(k)) is False:
				rez.add(k)
		except (TypeError, ValueError):
			continue
	return rez


def _text_grupa(X, n, neprins):
	"""Numarul de canale al antetului, cu semnul pozitiei neprinse niciodata (acelasi text ca pe televizor)."""
	text = X.text_numar(n)
	return text + u" · " + _t("niciodată recepționat") if neprins else text


def gen_antete(M, X, lista, tip, acum, grupuri, sel):
	"""GET /api/canale-lista cu grupe=1 („Toate canalele” fara text si fara filtre): antetele grupelor, cu numarul de
	canale, si grupa canalului de pe televizor (pagina o deschide pe ea)."""
	grupe = yield from gen_grupe(lista, X)
	neprinse = grupe_neprinse([k for k, _nume, _randuri in grupe])
	acum_grupa = None
	if acum["cheie"]:
		r = lista.dupa_cheie.get(acum["cheie"])
		if r is not None:
			acum_grupa = cheie_grupa(r.canal)
	return {
		"result": True,
		"tip": tip,
		"buchet": lista.id,
		"nume": lista.nume,
		"total": lista.canale,
		"canale": lista.canale,
		"numar": X.text_numar(lista.canale),
		"gasite": X.text_numar(lista.canale),
		"de_la": 0,
		"randuri": [],
		"gata": True,
		"acum": acum,
		"acum_poz": -1,
		"acum_grupa": acum_grupa,
		"grupe": [{"g": k, "nume": nume, "n": len(randuri), "nt": _text_grupa(X, len(randuri), k in neprinse),
			"neprins": k in neprinse} for k, nume, randuri in grupe],
		"grupuri": _grupuri_json(grupuri, sel, X),
		"ora": int(M.acum()),
	}


def _refCunoscut(ref):
	"""Referinta EPG apare intr-o lista data de server (cele din memorie)."""
	for _sem, _ora_, lista in _MEMORIE["liste"].values():
		if ref in lista.refs_epg:
			return True
	return False


def epg(argumente_, M=None):
	"""GET /api/canale-epg -> (cod, corp): emisiunea de acum si urmatoarea, numai pentru canale din listele date de
	server; memorie VIATA_EPG_S, iar o emisiune terminata se cere din nou."""
	M = _m(M)
	cerute = []
	for r in (argumente_.get("refs") or "").split(","):
		r = r.strip()
		if r and r not in cerute:
			cerute.append(r)
	if not cerute:
		return 400, {"result": False, "message": _t("Nu s-a cerut niciun canal."), "camp": "refs"}
	if len(cerute) > MAX_EPG:
		return 400, {"result": False, "message": _t("Cel mult %d de canale pe cerere.") % MAX_EPG, "camp": "refs"}
	cerute = [r for r in cerute if _refCunoscut(r)]
	acum = M.acum()
	memorie = _MEMORIE["epg"]
	rez = {}
	lipsa = []
	for r in cerute:
		v = memorie.get(r)
		if v is not None and acum - v[0] < VIATA_EPG_S and (v[1] is None or v[1]["i"] + v[1]["d"] > acum):
			rez[r] = {"acum": v[1], "urm": v[2]}
		else:
			lipsa.append(r)
	if lipsa:
		perechi = {}
		try:
			for tupla in M.epg(lipsa):
				if tupla:
					perechi.setdefault(tupla[0], []).append(tupla)
		except Exception as e:
			_jurnal("EPG: %s" % e)
		for r in lipsa:
			doua = perechi.get(r, [])
			e_acum = _emisiune(doua[0]) if len(doua) > 0 else None
			e_urm = _emisiune(doua[1]) if len(doua) > 1 else None
			memorie[r] = (acum, e_acum, e_urm)
			rez[r] = {"acum": e_acum, "urm": e_urm}
		if len(memorie) > 5000:
			for k in [k for k, v in memorie.items() if acum - v[0] >= VIATA_EPG_S]:
				del memorie[k]
	return 200, {"result": True, "ora": int(acum), "epg": rez}


def stare_acum(M=None):
	"""GET /api/canale-acum -> (cod, corp): canalul de pe televizor, emisiunea lui si standby-ul."""
	M = _m(M)
	a = _acum(M)
	emisiune = None
	r = ref_epg(a["ref"]) if a["ref"] else None
	if r:
		try:
			for tupla in M.epg([r]):
				emisiune = _emisiune(tupla)
				break
		except Exception as e:
			_jurnal("EPG acum: %s" % e)
	try:
		standby = bool(M.in_standby())
	except Exception:
		standby = False
	a.update({"result": True, "emisiune": emisiune, "standby": standby, "ora": int(M.acum()),
		"transmise": _transmise(M)})
	return 200, a


def gen_porneste(argumente_, M=None):
	"""POST /api/canale-porneste -> (cod, corp). Canalul trebuie sa fie in lista din care a fost ales."""
	M = _m(M)
	tip = _tip(argumente_)
	if tip is None:
		return 400, {"result": False, "message": _t("Fila se alege cu tv sau radio.")}
	ref = argumente_.get("ref") or ""
	if not ref_buna(ref):
		return 400, {"result": False, "message": _t("Canalul nu are o referință bună."), "camp": "ref"}
	id_ = argumente_.get("buchet") or TOATE
	if id_ != TOATE and not _ID_BUCHET.match(id_):
		return 400, {"result": False, "message": _t("Lista aleasă nu există pe receptor."), "camp": "buchet"}
	gasit = yield from gen_gaseste(M, tip, id_, ref)
	if gasit is None:
		return 404, {"result": False, "message": _t("Lista aleasă nu există pe receptor. Reîncarcă pagina."),
			"camp": "buchet"}
	if not gasit:
		return 400, {"result": False, "message": _t("Canalul nu e în lista aleasă. Reîncarcă pagina."), "camp": "ref"}
	ref_lista, nume, ref_buchet, canal = gasit
	if M.in_standby():
		return 409, {"result": False, "message": _t("Receptorul e în standby. Pornește-l, apoi alege canalul.")}
	ok, motiv = M.zap(ref_lista, tip, ref_buchet, canal)
	if not ok:
		return 409, {"result": False, "message": motiv or _t("Canalul nu a pornit.")}
	_jurnal("pornit din web: %s" % nume)
	return 200, {"result": True, "message": _t("Pornește pe televizor: %s") % nume, "acum": _acum(M)}


def gen_favorit(argumente_, M=None):
	"""POST /api/canale-favorit -> (cod, corp): canalul in Favorite-le filei (vrea=1) sau scos de acolo (vrea=0), prin
	aceeasi functie ca tasta FAV de pe televizor. Canalul trebuie sa fie in lista din care a fost ales; se foloseste
	referinta DIN LISTA, nu textul primit."""
	M = _m(M)
	tip = _tip(argumente_)
	if tip is None:
		return 400, {"result": False, "message": _t("Fila se alege cu tv sau radio.")}
	ref = argumente_.get("ref") or ""
	if not ref_buna(ref):
		return 400, {"result": False, "message": _t("Canalul nu are o referință bună."), "camp": "ref"}
	id_ = argumente_.get("buchet") or TOATE
	if id_ != TOATE and not _ID_BUCHET.match(id_):
		return 400, {"result": False, "message": _t("Lista aleasă nu există pe receptor."), "camp": "buchet"}
	vrea = argumente_.get("vrea")
	if vrea not in ("0", "1"):
		return 400, {"result": False, "message": _t("Nu s-a cerut ce să se facă."), "camp": "vrea"}
	gasit = yield from gen_gaseste(M, tip, id_, ref)
	if gasit is None:
		return 404, {"result": False, "message": _t("Lista aleasă nu există pe receptor. Reîncarcă pagina."),
			"camp": "buchet"}
	if not gasit:
		return 400, {"result": False, "message": _t("Canalul nu e în lista aleasă. Reîncarcă pagina."), "camp": "ref"}
	ref_lista, nume, _ref_buchet, _canal = gasit
	try:
		in_editare = M.lista_in_editare()
	except Exception as e:
		_jurnal("lista de pe televizor: %s" % e)
		in_editare = False
	if in_editare:
		return 409, {"result": False,
			"message": _t("Lista de canale e în editare pe televizor. Închide editarea, apoi încearcă din nou.")}
	rez = M.pune_favorit(ref_lista, tip, vrea == "1", nume)
	mesaj = rez.mesaj()   # tradus in Components/HdsFavorite.py (_t), acelasi text ca pe televizor
	if not rez.ok:
		return 409, {"result": False, "message": mesaj}
	uita_listele()
	_jurnal("Favorite din web: %s %s" % (nume, rez.fapta))
	return 200, {"result": True, "f": 1 if rez.in_buchet else 0, "message": mesaj}


def gen_gaseste(M, tip, id_, ref):
	"""Canalul de pornit din lista aleasa, fara sa refaca lista intreaga -> (ref din lista, nume, ref_buchet, canal);
	None daca lista nu exista, False daca canalul nu e in ea. Se porneste referinta DIN LISTA, nu textul primit.
	Lista din memorie se foloseste cat timp fisierele nu s-au schimbat, oricat de veche (selectia se verifica oricum pe
	lista de pe televizor inainte de zap); altfel se citeste numai buchetul ales, sau harta indexului la TOATE.
	`canal` (din index) numai la TOATE: il cere drumul cautarii de pe televizor; dintr-un buchet drumul e al lui
	zapToNumber si nu il foloseste."""
	X = M.X
	k = X.cheie_din_ref(ref) or ref
	vechi = _MEMORIE["liste"].get((tip, id_))
	if vechi is not None and vechi[0][:2] == (semnatura(M.director()), M.multibuchet()):
		lista = vechi[2]
		rand = lista.dupa_ref.get(ref) or lista.dupa_cheie.get(k)
		if rand is None:
			return False
		return rand.ref, rand.nume, lista.ref_buchet, (rand.canal if lista.ref_buchet is None else None)
	yield
	if id_ == TOATE:
		index = yield from gen_index(M)
		harta, _numar = yield from gen_canale_index(index)
		c = harta.get(k)
		if c is None or bool(c.radio) != (tip == "radio"):
			return False
		return c.ref, curat(c.nume_afisat() if hasattr(c, "nume_afisat") else c.nume) or "?", None, c
	surse = yield from gen_surse(M, tip)
	ref_buchet = None
	for i, (r, _n) in enumerate(surse):
		if id_buchet(r, i) == id_:
			ref_buchet = r
			break
	if ref_buchet is None:
		return None
	yield
	dupa_cheie = None
	for j, (r, n) in enumerate(M.continut(ref_buchet)):
		if j % UNITATE == UNITATE - 1:
			yield
		if steaguri(r) & (MARCAJ | DOSAR):
			continue
		if r == ref:
			return r, curat(n) or "?", ref_buchet, None
		if dupa_cheie is None and (X.cheie_din_ref(r) or r) == k:
			dupa_cheie = (r, curat(n) or "?", ref_buchet, None)
	return dupa_cheie or False


# ---------------------------------------------------------------- executorul pe felii

class _Planificator(object):
	"""Lucrarile pe felii ale unui furnizor, cu un singur ceas. O bataie ruleaza o singura felie (a primei lucrari
	treze; lucrarea trece apoi la coada, deci lucrarile merg pe rand), apoi ceasul se pune din nou la cel putin PAUZA_MS
	sau la trezirea celei mai apropiate lucrari care doarme. Un ceas pus mai devreme il inlocuieste pe cel vechi: bataia
	veche gaseste alt numar si nu face nimic, deci doua felii nu ruleaza niciodata in aceeasi trecere prin ceasuri."""

	def __init__(self, M):
		self.M = M
		self.lucrari = []
		self.bataie = 0
		self.la = None

	def numar(self):
		return sum(1 for l in self.lucrari if l.viu())

	def adauga(self, lucru, primul=False):
		if primul:
			self.lucrari.insert(0, lucru)
		else:
			self.lucrari.append(lucru)
		self._pune(0)

	def _pune(self, peste_s):
		ms = max(PAUZA_MS, int(peste_s * 1000 + 0.999))
		la = time.monotonic() + ms / 1000.0
		if self.la is not None and self.la <= la:
			return              # un ceas la fel de devreme e deja pus
		self.bataie += 1
		bataie = self.bataie
		self.la = la
		self.M.mai_tarziu(lambda: self._bate(bataie), ms)

	def _bate(self, bataie):
		if bataie != self.bataie:
			return              # inlocuit de un ceas pus mai devreme
		self.la = None
		self.lucrari = [l for l in self.lucrari if l.viu()]
		acum = time.monotonic()
		for l in self.lucrari:
			if l.treaza_la <= acum:
				self.lucrari.remove(l)
				self.lucrari.append(l)
				l.felie()
				break
		self.lucrari = [l for l in self.lucrari if l.viu()]
		if self.lucrari:
			self._pune(min(l.treaza_la for l in self.lucrari) - time.monotonic())


def _planificator(M):
	p = getattr(M, "planificator_felii", None)
	if p is None:
		p = _Planificator(M)
		M.planificator_felii = p
	return p


_IN_CURS = {}


def gen_unul_pe_fel(cheie, fabrica):
	"""Bariera: cel mult o constructie in curs pe `cheie`; o a doua cerere de acelasi fel asteapta rezultatul primei
	(acelasi raspuns). Daca prima e abandonata (browserul a plecat, termen), urmatoarea o ia de la capat."""
	while True:
		stare = _IN_CURS.get(cheie)
		if stare is None:
			break
		while not stare["gata"] and _IN_CURS.get(cheie) is stare:
			yield ASTEAPTA_BARIERA_MS
		if stare["gata"]:
			return stare["rez"]
	stare = {"gata": False, "rez": None}
	_IN_CURS[cheie] = stare
	try:
		rez = yield from fabrica()
		stare["rez"] = rez
		stare["gata"] = True
		return rez
	finally:
		if _IN_CURS.get(cheie) is stare:
			del _IN_CURS[cheie]


class PeBucati(object):
	"""Ruleaza un generator pe firul enigma2 in felii de cel mult BUGET_S, prin planificatorul furnizorului (intre doua
	felii bucla ajunge la poll()). Un pas care da un numar cere o pauza de atatea ms (asteapta un fir sau o bariera).
	Dupa termen_s: 504, iar generatorul se inchide. La sfarsit: gata(cod, corp)."""

	def __init__(self, gen, gata, M, termen_s=TERMEN_S, primul=False):
		self.gen = gen
		self.gata = gata
		self.M = M
		self.termen_s = termen_s
		self.primul = primul
		self.oprit = False
		self.terminat = False
		self.treaza_la = 0.0
		self.inceput = time.monotonic()
		self.felii = 0
		self.maxim_s = 0.0

	def viu(self):
		return not self.oprit and not self.terminat

	def porneste(self):
		_planificator(self.M).adauga(self, self.primul)

	def opreste(self, *_a):
		self.oprit = True
		self._inchide()

	def _inchide(self):
		try:
			self.gen.close()
		except Exception:
			pass

	def felie(self):
		if not self.viu():
			return
		inceput = time.monotonic()
		if inceput - self.inceput > self.termen_s:
			self._inchide()
			_jurnal("o cerere a depasit %d s" % self.termen_s)
			self._termina(504, {"result": False, "message": _t("Receptorul nu a terminat la timp. Încearcă din nou.")})
			return
		self.treaza_la = 0.0
		try:
			while True:
				pas = next(self.gen)
				if pas:
					self.treaza_la = time.monotonic() + pas / 1000.0
					break
				if time.monotonic() - inceput >= BUGET_S:
					break
		except StopIteration as sfarsit:
			self._masoara(inceput)
			rezultat = sfarsit.value if sfarsit.value is not None else (500, {"result": False})
			self._termina(rezultat[0], rezultat[1])
			return
		except Exception as e:
			self._masoara(inceput)
			_jurnal("eroare: %s" % e)
			self._termina(500, {"result": False, "message": _t("Eroare pe receptor.")})
			return
		self._masoara(inceput)

	def _masoara(self, inceput):
		durata = time.monotonic() - inceput
		self.felii += 1
		self.maxim_s = max(self.maxim_s, durata)
		if durata > JURNAL_FELIE_S:
			_jurnal("o felie a tinut %d ms" % int(durata * 1000))

	def _termina(self, cod, corp):
		if not self.viu():
			return
		self.terminat = True
		if isinstance(corp, dict):
			corp["lucru"] = {"felii": self.felii, "felie_max_ms": round(self.maxim_s * 1000, 1)}
		self.gata(cod, corp)


def _masoaraDirect(nume, inceput):
	"""O cerere facuta dintr-o bucata (EPG, canalul de acum) care a tinut firul enigma2 peste JURNAL_FELIE_S."""
	durata = time.monotonic() - inceput
	if durata > JURNAL_FELIE_S:
		_jurnal("cererea %s a tinut %d ms" % (nume, int(durata * 1000)))


def ruleaza_tot(gen):
	"""Generatorul pana la capat, fara pauze (probele de pe PC)."""
	try:
		while True:
			next(gen)
	except StopIteration as sfarsit:
		return sfarsit.value


# ---------------------------------------------------------------- resursele

def rute(baza, resource, NOT_DONE_YET=None, M=None):
	"""Resursele: ({nume: resursa de sub /api}, resursa paginii). `baza` e HdsJsonResource din plugin.py."""

	def _trimite(obiect, request, cod, corp):
		try:
			date = obiect._raspunde(request, corp, cod)
			request.write(date)
			request.finish()
		except Exception as e:
			_jurnal("raspunsul nu a plecat (browser plecat?): %s" % e)

	class _PeFelii(baza):
		"""Raspunsul se face pe felii; browserul care inchide conexiunea opreste lucrul."""
		primul = False

		def fa(self, a, Mx):
			raise NotImplementedError

		def _porneste(self, request):
			Mx = _m(M)
			if _planificator(Mx).numar() >= MAX_LUCRARI:
				return self._eroare(request, _t("Receptorul are prea multe cereri în lucru. Încearcă din nou."), 503)
			lucru = PeBucati(self.fa(argumente(request), Mx), lambda cod, corp: _trimite(self, request, cod, corp), Mx,
				primul=self.primul)
			try:
				request.notifyFinish().addErrback(lucru.opreste)
			except Exception:
				pass
			lucru.porneste()
			return NOT_DONE_YET

	class BucheteResource(_PeFelii):
		"""GET /api/canale-buchete: numai citire."""

		def fa(self, a, Mx):
			return gen_buchete_raspuns(a, Mx)

		def render_GET(self, request):
			return self._porneste(request)

	class ListaResource(_PeFelii):
		"""GET /api/canale-lista: numai citire."""

		def fa(self, a, Mx):
			return gen_lista_raspuns(a, Mx)

		def render_GET(self, request):
			return self._porneste(request)

	class PornesteResource(_PeFelii):
		"""POST /api/canale-porneste: schimba canalul pe televizor; trece inaintea listelor in lucru."""
		schimbaCeva = True
		primul = True

		def fa(self, a, Mx):
			return gen_porneste(a, Mx)

		def render_POST(self, request):
			return self._porneste(request)

		def render_GET(self, request):
			return self._porneste(request)   # numai cu ?token= (scripturi); din browser poarta cere POST

	class FavoritResource(_PeFelii):
		"""POST /api/canale-favorit: schimba Favorite pe receptor; trece inaintea listelor in lucru."""
		schimbaCeva = True
		primul = True

		def fa(self, a, Mx):
			return gen_favorit(a, Mx)

		def render_POST(self, request):
			return self._porneste(request)

		def render_GET(self, request):
			return self._porneste(request)   # numai cu ?token= (scripturi); din browser poarta cere POST

	class EpgResource(baza):
		"""GET /api/canale-epg: numai citire; un singur apel lookupEvent de cel mult MAX_EPG canale."""

		def render_GET(self, request):
			inceput = time.monotonic()
			try:
				cod, corp = epg(argumente(request), M)
				return self._raspunde(request, corp, cod)
			except Exception as e:
				_jurnal("EPG: %s" % e)
				return self._eroare(request, _t("Eroare pe receptor."), 500)
			finally:
				_masoaraDirect("EPG", inceput)

	class AcumResource(baza):
		"""GET /api/canale-acum: numai citire."""

		def render_GET(self, request):
			inceput = time.monotonic()
			try:
				cod, corp = stare_acum(M)
				return self._raspunde(request, corp, cod)
			except Exception as e:
				_jurnal("acum: %s" % e)
				return self._eroare(request, _t("Eroare pe receptor."), 500)
			finally:
				_masoaraDirect("acum", inceput)

	class SiglaResource(baza):
		"""GET /api/canale-sigla?p=<nume>: PNG-ul unei sigle gasite pe disc; citirea pe fir."""

		def render_GET(self, request):
			Mx = _m(M)
			nume = argumente(request).get("p") or ""

			def dupa(rezultat):
				try:
					if rezultat is None:
						request.write(self._eroare(request, _t("Sigla nu există pe receptor."), 404))
					else:
						request.write(self._png(request, rezultat))
					request.finish()
				except Exception as e:
					_jurnal("sigla nu a plecat (browser plecat?): %s" % e)

			octeti = cere_sigla(Mx, nume, dupa)
			if octeti is LA_FIR:
				return NOT_DONE_YET
			if octeti is None:
				return self._eroare(request, _t("Sigla nu există pe receptor."), 404)
			return self._png(request, octeti)

		def _png(self, request, octeti):
			request.setResponseCode(200)
			request.setHeader(b"content-type", b"image/png")
			request.setHeader(b"cache-control", b"private, max-age=86400")
			request.setHeader(b"x-content-type-options", b"nosniff")
			return octeti

	class PaginaResource(resource.Resource):
		"""GET /canale: pagina „Canale”."""
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	api = {
		b"canale-buchete": BucheteResource(),
		b"canale-lista": ListaResource(),
		b"canale-epg": EpgResource(),
		b"canale-acum": AcumResource(),
		b"canale-porneste": PornesteResource(),
		b"canale-favorit": FavoritResource(),
		b"canale-sigla": SiglaResource(),
	}
	return api, PaginaResource()


def pagina(request):
	"""Aceeasi poarta ca /cautare: reteaua locala, apoi ?token= sau cookie-ul browserului asociat; un browser
	neconectat primeste pagina de asociere. Pagina porneste canale, deci cu cookie primeste tokenul CSRF."""
	from . import plugin as P
	if not P._esteAdresaLocala(P._adresaClient(request)):
		request.setResponseCode(403)
		request.setHeader(b"content-type", b"text/plain; charset=utf-8")
		return _t("Acces permis doar din rețeaua locală.").encode("utf-8")
	P._anteteHtml(request)
	if P.PARAM_JETON in request.args and P._jetonValid(request):
		config_pagina = P._configPanou("", P._jetonConfigurat(), "")
	else:
		secret, browser = P._sesiuneDinCerere(request)
		if browser is None:
			return P._PAGINA_ASOCIERE.encode("utf-8")
		config_pagina = P._configPanou(P.csrfPentru(secret), "", browser.get("nume", ""))
	# playerul "Vezi live": aceeasi politica a continutului ca pagina /tv (scripturi de pe receptor, MediaSource)
	try:
		from . import tv_web
		request.setHeader(b"content-security-policy", tv_web.CSP_TV)
	except Exception as eroare:
		print("[HdsWebControl] canale: politica playerului: %s" % eroare)
	return pagina_text(P._STIL_COMUN, config_pagina).encode("utf-8", "replace")


def _aparate():
	"""aparate_web (fereastra aparatelor); pe PC, cand fisierul e incarcat singur, din acelasi dosar."""
	try:
		from . import aparate_web
		return aparate_web
	except ImportError:
		import importlib.util
		import sys
		if "aparate_web" in sys.modules:
			return sys.modules["aparate_web"]
		spec = importlib.util.spec_from_file_location("aparate_web",
			os.path.join(os.path.dirname(os.path.abspath(__file__)), "aparate_web.py"))
		modul = importlib.util.module_from_spec(spec)
		sys.modules["aparate_web"] = modul
		spec.loader.exec_module(modul)
		return modul


def _vezi_live():
	"""vezi_live_web (fereastra "Vezi live" si playlisturile, comune cu /cautare); pe PC, din acelasi dosar."""
	try:
		from . import vezi_live_web
		return vezi_live_web
	except ImportError:
		import importlib.util
		import sys
		if "vezi_live_web" in sys.modules:
			return sys.modules["vezi_live_web"]
		spec = importlib.util.spec_from_file_location("vezi_live_web",
			os.path.join(os.path.dirname(os.path.abspath(__file__)), "vezi_live_web.py"))
		modul = importlib.util.module_from_spec(spec)
		sys.modules["vezi_live_web"] = modul
		spec.loader.exec_module(modul)
		return modul


def pagina_text(stil, config_pagina):
	return _vezi_live().inPagina(_aparate().inPagina(_traducePagina(PAGINA))).replace("__STIL_COMUN__",
		stil).replace("__CONFIG__",
		config_pagina)


PAGINA = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Canale</title>
<style>__STIL_COMUN__
  body{font-size:16px;}
  main{max-width:1200px;margin:0 auto;}
  .sus{display:flex;flex-wrap:wrap;align-items:baseline;gap:4px 16px;margin:0 0 12px;}
  h1{font-size:1.25rem;margin:0;}
  .pe-tv{flex:1 1 260px;min-width:0;color:var(--text-slab);font-size:.92rem;line-height:1.4;overflow-wrap:anywhere;}
  .pe-tv b{color:var(--text);}
  /* bara de sus (filele, lista, cautarea, „Filtre” si randul filtrelor deschis) ramane lipita sub antetul cadrului
     cand se deruleaza canalele; --canale-sus = inaltimea antetului, masurata din script */
  .bara-sus{position:sticky;top:var(--canale-sus,0px);z-index:40;margin:0 -16px 10px calc(-1 * var(--st,16px));padding:8px 16px 2px var(--st,16px);background:var(--fundal,#10141a);box-shadow:0 8px 10px -8px rgba(0,0,0,.55);}
  .comenzi{display:grid;grid-template-columns:1fr;gap:8px;margin:0 0 8px;}
  .file{display:grid;grid-template-columns:1fr 1fr;border:1px solid var(--bordura);border-radius:10px;overflow:hidden;}
  .file button{min-height:44px;background:#0f1216;color:var(--text);border:0;font:inherit;cursor:pointer;}
  .file button[aria-selected=true]{background:var(--albastru);color:#fff;font-weight:bold;}
  select,input[type=search]{min-height:44px;width:100%;padding:8px 12px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);font:inherit;}
  .cauta{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px;}
  .buton{min-height:44px;padding:8px 14px;border-radius:8px;border:1px solid var(--bordura);background:#242a33;color:var(--text);font:inherit;cursor:pointer;}
  .buton[aria-expanded=true]{border-color:#f5b83d;}
  .nrf{display:inline-block;min-width:1.4em;margin-left:6px;padding:0 5px;border-radius:9px;background:#f5b83d;color:#10162a;font-size:.8rem;font-weight:bold;}
  .nrf:empty{display:none;}
  .bara{display:flex;flex-wrap:wrap;gap:8px 12px;align-items:center;justify-content:space-between;margin:0 0 8px;}
  .numar{color:#f5b83d;font-weight:bold;}
  .asezare{display:block;}
  #panouFiltre{display:none;background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:12px;margin:0 0 8px;overflow-y:auto;}
  #panouFiltre.deschis{display:block;}
  #grupuri{display:flex;flex-wrap:wrap;gap:10px 12px;margin:0 0 10px;}
  .grup{position:relative;flex:1 1 170px;min-width:150px;max-width:260px;}
  .grup summary{list-style:none;display:flex;flex-direction:column;gap:2px;min-height:44px;padding:6px 30px 6px 10px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);cursor:pointer;position:relative;}
  .grup summary::-webkit-details-marker{display:none;}
  .grup summary::after{content:"";position:absolute;right:12px;top:50%;width:7px;height:7px;margin-top:-6px;border-right:2px solid var(--text-slab);border-bottom:2px solid var(--text-slab);transform:rotate(45deg);}
  .grup[open] summary::after{margin-top:-2px;transform:rotate(-135deg);}
  .grup .titlu{font-size:.75rem;color:var(--text-slab);text-transform:uppercase;letter-spacing:.04em;}
  .grup .valoare{font-size:.92rem;white-space:nowrap;overflow:hidden;}
  .grup.ales summary{border-color:#f5b83d;box-shadow:0 0 0 1px #f5b83d inset;}
  /* lista unei grupe: peste continut, asezata din script sub grupa (sau deasupra ei, cand jos nu e loc), in ecran */
  .grup .optiuni{position:fixed;left:0;top:0;z-index:45;max-height:320px;overflow:auto;padding:4px;background:var(--panou);border:1px solid var(--bordura);border-radius:8px;box-shadow:0 8px 24px rgba(0,0,0,.45);min-width:220px;}
  .grup .optiuni label.zero{opacity:.45;}
  .grup .optiuni label{position:relative;display:flex;align-items:center;gap:10px;min-height:44px;padding:4px 8px;border-radius:6px;cursor:pointer;}
  /* casuta adevarata acopera tot randul (tinta de 44 px), cea desenata are 20 px */
  .grup .optiuni input{position:absolute;inset:0;width:100%;height:100%;margin:0;opacity:0;cursor:pointer;}
  .grup .optiuni .casuta{flex:0 0 auto;width:20px;height:20px;border:2px solid var(--text-slab);border-radius:5px;box-sizing:border-box;}
  .grup .optiuni input:checked+.casuta{background:#f5b83d;border-color:#f5b83d;box-shadow:inset 0 0 0 3px var(--panou);}
  .grup .optiuni small{color:var(--text-slab);margin-left:auto;}
  @media (pointer:coarse){ #grupuri{gap:12px 14px;} .grup summary{min-height:48px;} }
  @media (max-width:599px){ .grup{max-width:none;flex-basis:100%;} }
  .lista{list-style:none;margin:0;padding:0;}
  .lista li{margin:0 0 6px;}
.lista li.cu-ghid{display:flex;gap:6px;align-items:stretch;}
.lista li.cu-ghid .canal{flex:1;min-width:0;}
.stea{display:flex;align-items:center;justify-content:center;min-width:52px;min-height:44px;padding:0 10px;border:1px solid var(--bordura);border-radius:10px;background:#242a33;color:var(--text-slab);font:inherit;font-size:1.5rem;line-height:1;cursor:pointer;}
.stea[aria-pressed=true]{color:#f5b83d;border-color:#f5b83d;}
.stea:disabled{opacity:.5;cursor:wait;}
.stea:focus-visible{outline:2px solid #7fb8ff;outline-offset:2px;}
  /* in telefon (sub 600 px) steaua, "Ghid" si "Vezi live" trec pe un rand sub canal: langa el luau doua treimi din
     rand si numele ramanea intr-o coloana ingusta, rupt in mijlocul cuvintelor; mai mult loc intre canale decat intre
     canal si butoanele lui, ca sa se vada al cui e randul de butoane */
  @media (max-width:599px){
    .lista li.cu-ghid{flex-wrap:wrap;gap:4px;margin-bottom:14px;}
    .lista li.cu-ghid .canal{flex:1 1 100%;}
    .lista li.cu-ghid .stea{flex:0 0 auto;}
    .lista li.cu-ghid .ghid{flex:1 1 0;min-width:0;}
  }
  .marcaj{padding:12px 4px 4px;color:var(--text-slab);font-size:.85rem;text-transform:uppercase;letter-spacing:.04em;overflow-wrap:anywhere;}
  .canal{display:flex;gap:10px;align-items:flex-start;width:100%;min-height:56px;padding:10px 12px;background:var(--panou);border:1px solid var(--bordura);border-radius:10px;color:var(--text);font:inherit;text-align:left;cursor:pointer;}
  .canal:focus-visible,.buton:focus-visible,.grup summary:focus-visible,.grup .optiuni input:focus-visible+.casuta,.file button:focus-visible{outline:2px solid #7fb8ff;outline-offset:2px;}
  .canal.pornit{border-color:var(--verde);box-shadow:inset 4px 0 0 var(--verde);}
  .canal.trimis{opacity:.6;}
  .nr{flex:0 0 auto;min-width:1.9em;text-align:right;color:var(--text-slab);font-variant-numeric:tabular-nums;padding-top:1px;}
  .sigla{flex:0 0 auto;width:56px;height:34px;object-fit:contain;background:#0f1216;border-radius:4px;}
  .corp{flex:1 1 auto;min-width:0;display:block;}
  .linie{display:flex;flex-wrap:wrap;gap:2px 8px;align-items:baseline;min-width:0;}
  /* numele se rupe numai intre cuvinte; un singur cuvant mai lung decat tot randul se rupe ca ultima scapare */
  .nume{flex:1 1 100%;font-weight:bold;min-width:0;overflow-wrap:break-word;}
  .semne{color:var(--text-slab);font-size:.8rem;white-space:nowrap;}
  .semne.deosebire{color:#f5b83d;font-weight:bold;}
  .eticheta{background:var(--verde);color:#fff;border-radius:6px;padding:1px 7px;font-size:.78rem;white-space:nowrap;}
  .eticheta.transmis{background:#46cee2;color:#0b1020;font-weight:bold;}
  .eticheta.dvbi{background:#374ea1;color:#fff;}
  .eticheta.transmis::before{content:"";display:inline-block;width:1.15em;height:1.15em;margin-right:4px;vertical-align:-.2em;background:linear-gradient(to bottom,#46cee2 0 30%,transparent 30% 70%,#46cee2 70%),radial-gradient(circle closest-side,#0b1020 0 22%,transparent 24% 44%,#0b1020 46% 60%,transparent 62% 78%,#0b1020 80% 94%,transparent 96%);}
  .em{display:flex;gap:8px;min-width:0;font-size:.9rem;line-height:1.35;margin-top:3px;}
  .em.urm{color:var(--text-slab);}
  .em .o{flex:0 0 auto;font-variant-numeric:tabular-nums;color:var(--text-slab);}
  .em .t{min-width:0;overflow:hidden;white-space:nowrap;}
  .progres{display:block;height:4px;background:#2a2f38;border-radius:2px;margin:5px 0 1px;overflow:hidden;}
  .progres i{display:block;height:100%;width:0;background:#f5b83d;}
  .nota{color:var(--text-slab);font-size:.85rem;margin:8px 0 0;line-height:1.45;}
  #capat{height:1px;}
  .eroare{color:#ffb4a8;}
  .ascuns{display:none !important;}
  .gol-flux{margin:12px 0;padding:14px 16px;border:1px solid var(--bordura);border-radius:8px;background:#1b2029;}
  .gol-flux p{margin:0 0 12px;white-space:pre-line;line-height:1.45;}
  .gol-flux a.buton{display:inline-flex;align-items:center;text-decoration:none;}
  .lista li.grupa{margin:0 0 8px;}
  .toate-grupele{margin:0 0 8px;}
  .toate-grupele .buton{width:100%;text-align:left;}
  .antet{display:flex;align-items:center;gap:12px;width:100%;min-height:52px;padding:8px 14px;background:#1b2029;border:1px solid var(--bordura);border-radius:10px;color:var(--text);font:inherit;font-weight:bold;text-align:left;cursor:pointer;}
  .antet .semn{flex:0 0 auto;width:9px;height:9px;margin:0 4px 0 2px;border-right:2px solid #f5b83d;border-bottom:2px solid #f5b83d;transform:rotate(-45deg);}
  .antet[aria-expanded=true]{border-color:#f5b83d;}
  .antet[aria-expanded=true] .semn{transform:rotate(45deg);margin-top:-5px;}
  .antet .nume-grupa{flex:1 1 auto;min-width:0;overflow-wrap:anywhere;}
  .antet .nr-grupa{flex:0 0 auto;color:var(--text-slab);font-weight:normal;font-size:.88rem;}
  .antet:focus-visible{outline:2px solid #7fb8ff;outline-offset:2px;}
  .grupa-canale{margin:6px 0 0 12px;}
  .grupa-incarca{color:var(--text-slab);font-size:.85rem;padding:6px 4px;}
  #mesaj{position:fixed;left:calc(16px + var(--cadru-stanga,0px));right:16px;bottom:calc(16px + var(--cadru-jos,0px));max-width:560px;margin:0 auto;background:#242a33;border:1px solid var(--bordura);border-radius:10px;padding:12px 14px;line-height:1.4;box-shadow:0 6px 24px rgba(0,0,0,.4);z-index:5;}
  @media (min-width:600px){
    .nume{flex:0 1 auto;}
    .eticheta{margin-left:auto;}
    .eticheta.transmis:not(.ascuns) + .eticheta{margin-left:0;}
    .nr{min-width:2.6em;}
    .comenzi{grid-template-columns:220px minmax(0,1fr);}
    .cauta{grid-column:1 / -1;}
  }
  @media (min-width:900px){
    .comenzi{grid-template-columns:200px minmax(0,1fr) minmax(0,1.3fr);}
    .cauta{grid-column:auto;}
  }
__APARATE_STIL__
__LIVE_STIL__
</style>
</head>
<body>
<main>
<div class="sus">
  <h1>Canale</h1>
  <div class="pe-tv" id="peTv" aria-live="polite"></div>
</div>
<div class="bara-sus" id="baraSus">
<div class="comenzi">
  <div class="file" role="tablist" aria-label="Felul canalelor">
    <button type="button" role="tab" id="filaTv" aria-selected="true">TV</button>
    <button type="button" role="tab" id="filaRadio" aria-selected="false">Radio</button>
  </div>
  <select id="buchet" aria-label="Lista de canale"></select>
  <div class="cauta">
    <input id="text" type="search" maxlength="40" placeholder="Caută după nume" autocomplete="off" aria-label="Caută după nume">
    <button type="button" class="buton" id="butonFiltre" aria-expanded="false" aria-controls="panouFiltre">Filtre<span class="nrf" id="nrFiltre"></span></button>
  </div>
</div>
<aside id="panouFiltre" aria-label="Filtre">
  <div id="grupuri"></div>
  <button type="button" class="buton" id="stergeFiltre">Șterge filtrele</button>
  <p class="nota">În aceeași grupă opțiunile bifate se adună cu «sau», între grupe cu «și». Numărul arată câte canale ar rămâne cu opțiunea bifată.</p>
</aside>
</div>
<div class="asezare">
  <section>
    <div class="bara">
      <span class="numar" id="numar">Se citește lista...</span>
      <span>
        <button type="button" class="buton ascuns" id="inToate"></button>
        <button type="button" class="buton ascuns" id="laAcum">Canalul de pe televizor</button>
        <button type="button" class="buton" id="exportM3u" title="Lista așa cum e aleasă și filtrată acum, pentru VLC, Kodi sau alt player din casă">__L_exporta__</button>
        <button type="button" class="buton" id="aparatFix">__A_din_canale__</button>
        <a class="buton" id="laPlaylisturi" href="/playlisturi">__A_playlisturi__</a>
      </span>
    </div>
    <div class="gol-flux ascuns" id="golFlux"><p id="golFluxText"></p><a class="buton" id="golFluxLeg" href="/scanare">Caută acum</a></div>
    <ol class="lista" id="lista"></ol>
    <div id="capat"></div>
    <p class="nota" id="subsol"></p>
  </section>
</div>
</main>
<div id="mesaj" class="ascuns" role="status" aria-live="polite"></div>
__LIVE_DIALOG__
__APARATE_DIALOG__
<script src="/tv/player.js"></script>
<script>
var CFG = __CONFIG__;
var PAGINA = 100, PAGINA_GRUPA = 500;
var S = {transmise: [], tip: "tv", buchet: null, text: "", ales: {}, randuri: [], gata: true, urm: 0, gen: 0, incarca: false,
  filtreEl: {}, semnFiltre: null,
  epg: {}, el: {}, coada: [], epgInCurs: false, ofset: 0, acum: null, acumPoz: -1, pornire: false, grupuri: [],
  fundal: 0, grupat: false, grupe: [], deschise: {}, grupaAcum: null, elGrupe: {}, spreAcum: false, coadaGrupe: [],
  grupaInCurs: false};
// emisiunile se cer numai pentru randurile care ajung aproape de ecran (o grupa inchisa sau toate grupele deschise nu
// cer sute de canale deodata)
var VEDERE = window.IntersectionObserver ? new IntersectionObserver(function(intrari){
  var cer = [];
  intrari.forEach(function(x){
    if(!x.isIntersecting){ return; }
    VEDERE.unobserve(x.target);
    var e = x.target.getAttribute("data-e");
    if(e && !S.epg.hasOwnProperty(e)){ cer.push(e); }
  });
  cereEpg(cer);
}, {rootMargin: "600px"}) : null;
// paginile listei tinute minte in browser (cheia = cererea), ca trecerea la toata lista sa nu mai astepte receptorul
var MEMORIE = {}, MEMORIE_MS = 120000;
function dinMemorie(q){ var x = MEMORIE[q]; return (x && Date.now() - x.t < MEMORIE_MS) ? x.d : null; }
function tineMinte(q, d){ if(d && d.result){ MEMORIE[q] = {t: Date.now(), d: d}; } }
var ceasText = null, ceasMesaj = null, ceasFiltre = null;
function $(id){ return document.getElementById(id); }
function adresa(cale){
  if(!CFG.jeton){ return cale; }
  return cale + (cale.indexOf("?") === -1 ? "?" : "&") + "token=" + encodeURIComponent(CFG.jeton);
}
function cerere(cale, metoda, date){
  var optiuni = {method: metoda || "GET", cache: "no-store", credentials: "same-origin", headers: {}};
  if(CFG.csrf){ optiuni.headers["X-HDS-CSRF"] = CFG.csrf; }
  if(date){
    optiuni.headers["Content-Type"] = "application/x-www-form-urlencoded";
    optiuni.body = date.toString();
  }
  return fetch(adresa(cale), optiuni).then(function(r){
    if(r.status === 401 && !CFG.jeton){ location.replace("/"); throw new Error("browser deconectat"); }
    return r.json().catch(function(){ return {result: false, message: "Receptorul a răspuns neașteptat (HTTP " + r.status + ")."}; });
  });
}
function el(tag, clasa, text){
  var e = document.createElement(tag);
  if(clasa){ e.className = clasa; }
  if(text !== undefined && text !== null){ e.textContent = text; }
  return e;
}
function gol(e){ while(e.firstChild){ e.removeChild(e.firstChild); } }
function acumReceptor(){ return Date.now() / 1000 + S.ofset; }
function potriveste(ora){ if(ora){ S.ofset = ora - Date.now() / 1000; } }
function mesaj(text, eroare){
  var m = $("mesaj");
  m.textContent = text || "";
  m.classList.toggle("eroare", !!eroare);
  m.classList.toggle("ascuns", !text);
  if(ceasMesaj){ clearTimeout(ceasMesaj); }
  if(text){ ceasMesaj = setTimeout(function(){ m.classList.add("ascuns"); }, 4000); }
}
function parametri(de_la){
  var q = new URLSearchParams();
  q.set("fila", S.tip);
  q.set("buchet", S.buchet || "toate");
  if(S.text){ q.set("text", S.text); }
  Object.keys(S.ales).forEach(function(g){ if(S.ales[g].length){ q.set(g, S.ales[g].join(",")); } });
  q.set("de_la", de_la);
  q.set("cate", PAGINA);
  return q;
}
function numarFiltre(){
  var n = 0;
  Object.keys(S.ales).forEach(function(g){ n += S.ales[g].length; });
  $("nrFiltre").textContent = n ? String(n) : "";
}
function arataFila(){
  $("filaTv").setAttribute("aria-selected", S.tip === "tv" ? "true" : "false");
  $("filaRadio").setAttribute("aria-selected", S.tip === "radio" ? "true" : "false");
}
function incarcaBuchete(){
  arataFila();
  $("numar").textContent = "Se citește lista...";
  return cerere("/api/canale-buchete?fila=" + S.tip).then(function(d){
    if(!d.result){ $("numar").textContent = d.message || "Listele nu s-au putut citi."; return; }
    var s = $("buchet"); gol(s);
    d.buchete.forEach(function(b){
      var o = el("option", "", b.nume + " (" + b.numar + ")"); o.value = b.id; s.appendChild(o);
    });
    // implicit "Toate canalele", pe grupe ca lista "Sateliti" de pe televizor: grupa canalului de pe televizor
    // deschisa, cu canalul marcat si adus in vedere; celelalte grupe inchise, cerute in fundal
    S.buchet = "toate";
    s.value = "toate";
    incarcaLista();
  }).catch(function(){ $("numar").textContent = "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."; });
}
function cuFiltre(){ return Object.keys(S.ales).some(function(g){ return S.ales[g].length; }); }
// "Toate canalele" fara text si fara filtre = pe grupe; altfel lista plata, peste toate canalele listei alese
function eGrupat(){ return S.buchet === "toate" && !S.text && !cuFiltre(); }
function incarcaLista(){
  S.gen += 1;
  S.randuri = []; S.gata = false; S.urm = 0; S.el = {}; S.coada = []; S.elGrupe = {}; S.coadaGrupe = [];
  S.grupaInCurs = false;
  if(VEDERE){ VEDERE.disconnect(); }
  gol($("lista"));
  $("subsol").textContent = "";
  $("numar").textContent = "Se citește lista...";
  S.grupat = eGrupat();
  if(S.grupat){ incarcaGrupele(S.gen); } else { pagina(0, S.gen); }
}
function incarcaGrupele(gen){
  S.incarca = true;
  var q = new URLSearchParams();
  q.set("fila", S.tip); q.set("buchet", "toate"); q.set("grupe", "1");
  return cerere("/api/canale-lista?" + q.toString()).then(function(d){
    if(gen !== S.gen){ return; }
    S.incarca = false;
    S.gata = true;
    if(!d.result){ $("numar").textContent = d.message || "Lista nu s-a putut citi."; return; }
    potriveste(d.ora);
    primaPagina(d);
    S.grupe = d.grupe || [];
    S.grupaAcum = d.acum_grupa || null;
    $("laAcum").classList.toggle("ascuns", !S.grupaAcum);
    deseneazaGrupele();
    if(!Object.keys(S.deschise).some(function(k){ return S.deschise[k]; }) && S.grupaAcum){
      S.deschise[S.grupaAcum] = true;
      S.spreAcum = true;
    }
    S.grupe.forEach(function(g){ if(S.deschise[g.g]){ deschideGrupa(g.g); } });
    arataToate();
    preincarca(S.tip);
  }).catch(function(){
    if(gen !== S.gen){ return; }
    S.incarca = false;
    $("numar").textContent = "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea.";
  });
}
function deseneazaGrupele(){
  var l = $("lista");
  if(S.grupe.length > 1){
    var li = el("li", "toate-grupele");
    var b = el("button", "buton"); b.type = "button"; b.id = "toateGrupele";
    b.addEventListener("click", comutaToate);
    li.appendChild(b);
    l.appendChild(li);
  }
  S.grupe.forEach(function(g){
    var li = el("li", "grupa");
    var b = el("button", "antet"); b.type = "button"; b.setAttribute("aria-expanded", "false");
    b.appendChild(el("span", "semn"));
    b.appendChild(el("span", "nume-grupa", g.nume));
    b.appendChild(el("span", "nr-grupa", g.nt || String(g.n)));
    var ol = el("ol", "lista grupa-canale ascuns");
    b.addEventListener("click", function(){ comutaGrupa(g.g); });
    li.appendChild(b); li.appendChild(ol); l.appendChild(li);
    S.elGrupe[g.g] = {g: g, b: b, ol: ol, incarcat: false, cerut: false};
  });
  arataToate();
}
function toateDeschise(){ return S.grupe.length > 0 && S.grupe.every(function(g){ return S.deschise[g.g]; }); }
function arataToate(){
  var b = $("toateGrupele");
  if(b){ b.textContent = toateDeschise() ? "Închide ceilalți sateliți" : "Deschide toate canalele pe toți sateliții"; }
}
function comutaGrupa(k){
  if(S.deschise[k]){ inchideGrupa(k); } else { deschideGrupa(k); }
  arataToate();
}
function comutaToate(){
  if(toateDeschise()){
    S.grupe.forEach(function(g){ if(g.g !== S.grupaAcum){ inchideGrupa(g.g); } });
  } else {
    S.grupe.forEach(function(g){ if(!S.deschise[g.g]){ deschideGrupa(g.g); } });
  }
  arataToate();
}
function inchideGrupa(k){
  var o = S.elGrupe[k];
  S.deschise[k] = false;
  if(!o){ return; }
  o.b.setAttribute("aria-expanded", "false");
  o.ol.classList.add("ascuns");
}
function deschideGrupa(k){
  var o = S.elGrupe[k];
  S.deschise[k] = true;
  if(!o){ return; }
  o.b.setAttribute("aria-expanded", "true");
  o.ol.classList.remove("ascuns");
  if(o.incarcat){ if(k === S.grupaAcum && S.spreAcum){ aduAcum(); } return; }
  if(!o.cerut){
    o.cerut = true;
    o.ol.appendChild(el("li", "grupa-incarca", "Se citesc canalele..."));
    S.coadaGrupe.push(k);
    pompaGrupe();
  }
}
// randurile unei grupe, pagina cu pagina, o grupa odata (receptorul primeste cel mult o cerere de grupa deodata);
// paginile cerute deja in fundal vin din memoria browserului
function cerereGrupa(tip, k, de_la){
  var q = new URLSearchParams();
  q.set("fila", tip); q.set("buchet", "toate"); q.set("grupa", k); q.set("de_la", de_la); q.set("cate", PAGINA_GRUPA);
  var cheie = q.toString(), m = dinMemorie(cheie);
  return (m ? Promise.resolve(m) : cerere("/api/canale-lista?" + cheie)).then(function(d){
    if(!m){ tineMinte(cheie, d); }
    return d;
  });
}
function pompaGrupe(){
  if(S.grupaInCurs || !S.coadaGrupe.length){ return; }
  var k = S.coadaGrupe.shift(), o = S.elGrupe[k], gen = S.gen, de_la = 0;
  if(!o){ pompaGrupe(); return; }
  S.grupaInCurs = true;
  function gata(){ S.grupaInCurs = false; pompaGrupe(); }
  function urmatoarea(){
    cerereGrupa(S.tip, k, de_la).then(function(d){
      if(gen !== S.gen){ return; }
      if(!d.result){
        gol(o.ol); o.ol.appendChild(el("li", "grupa-incarca eroare", d.message || "Grupa nu s-a putut citi."));
        o.cerut = false; gata(); return;
      }
      potriveste(d.ora);
      if(de_la === 0){ gol(o.ol); }
      deseneaza(d.randuri, o.ol);
      de_la += d.randuri.length;
      if(!d.gata && d.randuri.length){ urmatoarea(); return; }
      o.incarcat = true;
      if(k === S.grupaAcum && S.spreAcum && S.deschise[k]){ aduAcum(); }
      gata();
    }).catch(function(){
      if(gen !== S.gen){ return; }
      o.cerut = false;
      gol(o.ol); o.ol.appendChild(el("li", "grupa-incarca eroare", "Receptorul nu răspunde."));
      gata();
    });
  }
  urmatoarea();
}
function aduAcum(){
  S.spreAcum = false;
  var o = S.acum && S.el[S.acum] && S.el[S.acum].filter(function(x){ return x.b.offsetParent !== null; })[0];
  if(o){ o.b.scrollIntoView({block: "center"}); o.b.focus({preventScroll: true}); }
}
function pagina(de_la, gen){
  S.incarca = true;
  var q = parametri(de_la).toString(), m = dinMemorie(q);
  return (m ? Promise.resolve(m) : cerere("/api/canale-lista?" + q)).then(function(d){
    if(!m){ tineMinte(q, d); }
    if(gen !== S.gen){ return; }
    S.incarca = false;
    if(!d.result){ $("numar").textContent = d.message || "Lista nu s-a putut citi."; S.gata = true; return; }
    potriveste(d.ora);
    if(de_la === 0){ primaPagina(d); }
    deseneaza(d.randuri);
    S.urm = de_la + d.randuri.length;
    S.gata = d.gata;
    if(S.gata){ $("subsol").textContent = d.canale ? "Sfârșitul listei." : ""; }
    maiDeparte();
  }).catch(function(){
    if(gen !== S.gen){ return; }
    S.incarca = false;
    $("numar").textContent = "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea.";
  });
}
function primaPagina(d){
  S.numarLista = d.canale || 0;
  $("numar").textContent = (S.text || Object.keys(S.ales).some(function(g){ return S.ales[g].length; })) ? d.gasite : d.numar;
  if(d.grupuri){ S.grupuri = d.grupuri; construiesteGrupuri(d.grupuri); }
  var b = $("inToate");
  if(d.in_toate !== undefined && d.buchet !== "toate"){
    b.textContent = "Caută în toate canalele (" + d.in_toate + ")";
    b.classList.remove("ascuns");
  } else { b.classList.add("ascuns"); }
  S.acumPoz = d.acum_poz;
  $("laAcum").classList.toggle("ascuns", !(d.acum_poz >= 0));
  $("golFlux").classList.toggle("ascuns", !d.gol_text);
  if(d.gol_text){ $("golFluxText").textContent = d.gol_text; $("golFluxLeg").href = d.gol_legatura; }
  if(d.acum){ marcheaza(d.acum.cheie); }
  if(d.transmise){ marcheazaTransmise(d.transmise); }
}
// grupele lui "Toate canalele" cerute in fundal, una dupa alta, rar, ca receptorul sa nu fie incarcat; deschiderea
// unei grupe (si "Deschide toate canalele pe toti satelitii") vine apoi din memoria browserului. Se opreste cand se
// schimba fila.
function preincarca(tip){
  var rand = ++S.fundal, i = 0, de_la = 0;
  function urmatoarea(){
    if(rand !== S.fundal || tip !== S.tip || i >= S.grupe.length){ return; }
    var k = S.grupe[i].g, o = S.elGrupe[k];
    if(de_la === 0 && o && (o.incarcat || o.cerut)){ i += 1; setTimeout(urmatoarea, 0); return; }
    cerereGrupa(tip, k, de_la).then(function(d){
      if(!d || !d.result){ return; }
      if(d.gata || !d.randuri.length){ i += 1; de_la = 0; } else { de_la += d.randuri.length; }
      setTimeout(urmatoarea, 300);
    }).catch(function(){});
  }
  setTimeout(urmatoarea, 500);
}
function maiDeparte(){
  if(S.grupat || S.gata || S.incarca){ return; }
  var r = $("capat").getBoundingClientRect();
  if(r.top < window.innerHeight + 800){ pagina(S.urm, S.gen); }
}
// aceleasi grupe si optiuni ca pe ecran (s-au schimbat numai numerele, dupa o bifa): numerele se pun pe loc, iar lista
// deschisa ramane deschisa
function semnFiltre(grupuri){ return grupuri.map(function(g){ return g.g + ":" + g.optiuni.map(function(x){ return x.v; }).join(","); }).join("|"); }
function construiesteGrupuri(grupuri){
  var semn = semnFiltre(grupuri);
  if(semn === S.semnFiltre && $("grupuri").childNodes.length){
    // bifele vin tot de la receptor (si „Șterge filtrele” le scoate pe toate)
    var alese = {};
    grupuri.forEach(function(g){
      alese[g.g] = [];
      g.optiuni.forEach(function(x){
        if(x.ales){ alese[g.g].push(x.v); }
        var f = S.filtreEl[g.g + "|" + x.v];
        if(!f){ return; }
        f.cb.checked = !!x.ales;
        f.nr.textContent = String(x.n);
        f.l.classList.toggle("zero", x.n === 0 && !x.ales);
      });
    });
    S.ales = alese;
    grupuri.forEach(function(g){ if(S.filtreEl[g.g]){ S.filtreEl[g.g](); } });
    numarFiltre();
    $("stergeFiltre").disabled = !Object.keys(alese).some(function(k){ return alese[k].length; });
    return;
  }
  S.semnFiltre = semn;
  S.filtreEl = {};
  var c = $("grupuri"); gol(c);
  var ales = {};
  // o grupa = o lista derulanta cu casute: in grupa "sau" (mai multe bifate), intre grupe "si"
  grupuri.forEach(function(g){
    var d = el("details", "grup");
    var sum = el("summary");
    sum.appendChild(el("span", "titlu", g.titlu));
    var val = el("span", "valoare hds-derulant", "Selectează...");
    sum.appendChild(val);
    d.appendChild(sum);
    var o = el("div", "optiuni");
    function arata(){
      var l = S.ales[g.g] || [], nume = [];
      g.optiuni.forEach(function(x){ if(l.indexOf(x.v) !== -1){ nume.push(x.eticheta); } });
      val.textContent = !nume.length ? "Selectează..." : (nume.length <= 2 ? nume.join(", ") : nume.length + " alese");
      d.classList.toggle("ales", nume.length > 0);
    }
    g.optiuni.forEach(function(x){
      if(x.ales){ (ales[g.g] = ales[g.g] || []).push(x.v); }
      var l = el("label");
      var cb = el("input"); cb.type = "checkbox"; cb.checked = !!x.ales;
      l.appendChild(cb);
      l.appendChild(el("span", "casuta"));
      l.appendChild(el("span", "", x.eticheta));
      var nr = el("small", "", String(x.n));
      l.appendChild(nr);
      // o optiune cu 0 (nu ar ramane niciun canal) se vede, estompata
      l.classList.toggle("zero", x.n === 0 && !x.ales);
      S.filtreEl[g.g + "|" + x.v] = {l: l, nr: nr, cb: cb};
      cb.addEventListener("change", function(){
        var lista = S.ales[g.g] = S.ales[g.g] || [];
        var i = lista.indexOf(x.v);
        if(cb.checked && i === -1){ lista.push(x.v); }
        if(!cb.checked && i !== -1){ lista.splice(i, 1); }
        arata();
        numarFiltre();
        $("stergeFiltre").disabled = !Object.keys(S.ales).some(function(k){ return S.ales[k].length; });
        if(ceasFiltre){ clearTimeout(ceasFiltre); }
        ceasFiltre = setTimeout(incarcaLista, 400);
      });
      o.appendChild(l);
    });
    d.appendChild(o);
    S.filtreEl[g.g] = arata;
    // o singura lista deschisa odata
    d.addEventListener("toggle", function(){
      if(!d.open){ return; }
      Array.prototype.forEach.call(c.querySelectorAll("details.grup[open]"), function(x){ if(x !== d){ x.open = false; } });
      aseazaLista(sum, o);
    });
    c.appendChild(d);
    S.ales[g.g] = ales[g.g] || [];
    arata();
  });
  S.ales = ales;
  numarFiltre();
  $("stergeFiltre").disabled = !Object.keys(ales).length;
  if(!grupuri.length){ c.appendChild(el("p", "nota", "Lista aleasă nu are ce filtra.")); }
}
function cadruJos(){ return parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--cadru-jos")) || 0; }
// lista unei grupe peste continut: sub grupa, sau deasupra ei cand jos nu e loc; niciodata in afara ecranului (nici sub
// bara de jos a telefonului din teme)
function aseazaLista(sum, o){
  var r = sum.getBoundingClientRect(), H = window.innerHeight - cadruJos(), W = window.innerWidth;
  var lat = Math.min(Math.max(r.width, 220), W - 16);
  o.style.width = lat + "px";
  o.style.left = Math.max(8, Math.min(r.left, W - lat - 8)) + "px";
  var jos = H - r.bottom - 12, sus = r.top - 12;
  if(jos >= 200 || jos >= sus){
    o.style.top = (r.bottom + 4) + "px"; o.style.bottom = "auto"; o.style.maxHeight = Math.max(120, Math.min(320, jos)) + "px";
  } else {
    o.style.top = "auto"; o.style.bottom = (window.innerHeight - r.top + 4) + "px"; o.style.maxHeight = Math.max(120, Math.min(320, sus)) + "px";
  }
}
function inchideListeleFiltrelor(){
  Array.prototype.forEach.call(document.querySelectorAll("details.grup[open]"), function(x){ x.open = false; });
}
// randul filtrelor deschis nu iese din ecran: se deruleaza in el
function aseazaPanoul(){
  var p = $("panouFiltre");
  if(!p.classList.contains("deschis")){ return; }
  var r = p.getBoundingClientRect();
  p.style.maxHeight = Math.max(160, window.innerHeight - cadruJos() - r.top - 8) + "px";
}
// bara de sus se lipeste sub antetul cadrului (inaltimea lui difera dupa tema si latime)
function aseazaBara(){
  var a = document.querySelector(".hds-antet");
  var h = a ? Math.round(a.getBoundingClientRect().height) : 0;
  document.documentElement.style.setProperty("--canale-sus", h + "px");
  aseazaPanoul();
}
window.addEventListener("scroll", inchideListeleFiltrelor, {passive: true});
window.addEventListener("resize", function(){ inchideListeleFiltrelor(); aseazaBara(); });
$("panouFiltre").addEventListener("scroll", inchideListeleFiltrelor, {passive: true});
// un clic in afara listelor de filtre le inchide
document.addEventListener("click", function(e){
  Array.prototype.forEach.call(document.querySelectorAll("details.grup[open]"), function(x){ if(!x.contains(e.target)){ x.open = false; } });
});
// ---------------------------------------------------------------- Vezi live si playlisturile M3U (vezi_live_web.py)
__LIVE_JS__
// "Vezi live" pe un canal pe care transmisia nu-l poate lua fara televizor (receptor cu motor sau cu un singur tuner de
// satelit, canal de pe alta frecventa): televizorul trece pe el ca la clic pe rand (/api/canale-porneste, din lista
// aleasa; antena se poate roti, ca la orice zap), apoi imaginea urmeaza televizorul (player.js)
function mutaTv(ref){
  var q = new URLSearchParams();
  q.set("fila", S.tip); q.set("buchet", S.buchet || "toate"); q.set("ref", ref);
  return cerere("/api/canale-porneste", "POST", q).then(function(d){
    if(d.result && d.acum){ marcheaza(d.acum.cheie); arataAcum(d.acum, null); setTimeout(citesteAcum, 1500); }
    return d;
  });
}
function textAles(){
  // numele listei alese si filtrele bifate, pentru numele fisierului si grupul din playlist
  var s = $("buchet"), parti = [];
  var b = s && s.selectedIndex >= 0 ? s.options[s.selectedIndex].textContent : "", k = b.lastIndexOf(" (");
  if(k > 0){ b = b.slice(0, k); }
  S.grupuri.forEach(function(g){
    (g.optiuni || []).forEach(function(x){ if((S.ales[g.g] || []).indexOf(x.v) !== -1){ parti.push(x.eticheta); } });
  });
  if(S.text){ parti.push(S.text); }
  return {lista: b, filtre: parti};
}
function exportaPlaylist(){
  var buton = $("exportM3u");
  buton.disabled = true;
  mesaj(TL.se_strange);
  var refs = [], vazute = {}, q = parametri(0), numar = "";
  q.set("cate", "200");
  function pas(de_la){
    q.set("de_la", de_la);
    return cerere("/api/canale-lista?" + q.toString()).then(function(d){
      if(!d.result){ throw new Error(d.message || TL.nu_s_a_facut); }
      if(de_la === 0){ numar = d.numar || ""; }
      (d.randuri || []).forEach(function(r){ if(r.ref && !r.m && !vazute[r.ref]){ vazute[r.ref] = 1; refs.push(r.ref); } });
      if(!d.gata && (d.randuri || []).length && refs.length < MAX_EXPORT){ return pas(de_la + d.randuri.length); }
    });
  }
  pas(0).then(function(){
    var t = textAles();
    // numarul listei, cand intra toata in playlist
    return liveDescarca(refs, t.lista || "HD Satelit", [t.lista].concat(t.filtre).filter(Boolean).join(" ") || "canale",
      refs.length < MAX_EXPORT ? numar : "");
  }).catch(function(e){ mesaj(e.message || TL.nu_s_a_facut, true); })
    .then(function(){ buton.disabled = false; });
}
$("exportM3u").addEventListener("click", exportaPlaylist);
// ---------------------------------------------------------------- adresa fixa pentru un aparat (aparate_web.py)
// lista si filtrele de acum devin sursa unui aparat din casa; adresele (cu cheia) se arata o singura data
var TA = __APARATE_TEXTE__, MAX_CANALE_APARAT = __APARATE_MAX__;
__APARATE_JS__
function deschideAparat(){
  if(S.tip !== "tv"){ mesaj(TA.numai_tv, true); return; }
  var t = textAles();
  aparatDeschide({eticheta: [t.lista].concat(t.filtre).filter(Boolean).join(", "), numar: S.numarLista,
    inapoi: $("aparatFix"), campuri: function(){
      var filtre = {};
      Object.keys(S.ales).forEach(function(g){ if(S.ales[g].length){ filtre[g] = S.ales[g]; } });
      return {sursa: "filtru", buchet: S.buchet || "toate", text: S.text || "", filtre: JSON.stringify(filtre)};
    }});
}
$("aparatFix").addEventListener("click", deschideAparat);
function randEmisiune(clasa){
  var d = el("span", "em " + clasa + " ascuns");
  d.appendChild(el("span", "o"));
  // titlul emisiunii care nu incape se deruleaza (hds-derulant, cadru_web.py): la randul de pe televizor, cu mouse-ul
  // sau cu focusul (butonul canalului are hds-derulant-rand)
  d.appendChild(el("span", "t hds-derulant"));
  return d;
}
function deseneaza(randuri, tinta){
  var l = tinta || $("lista");
  var cer = [];
  randuri.forEach(function(r){
    var i = S.randuri.length;
    S.randuri.push(r);
    var li = el("li");
    if(r.m){ li.className = "marcaj"; li.textContent = r.nume; l.appendChild(li); return; }
    var b = el("button", "canal hds-derulant-rand"); b.type = "button";
    b.appendChild(el("span", "nr", r.n ? String(r.n) : ""));
    if(r.s){
      var img = el("img", "sigla"); img.alt = ""; img.loading = "lazy"; img.decoding = "async";
      img.src = adresa("/api/canale-sigla?p=" + encodeURIComponent(r.s));
      img.addEventListener("error", function(){ img.remove(); });
      b.appendChild(img);
    }
    var corp = el("span", "corp");
    var linie = el("span", "linie");
    linie.appendChild(el("span", "nume", r.nume));
    if(r.semne){ linie.appendChild(el("span", "semne", r.semne)); }
    // ce il deosebeste de randurile care arata la fel (frecventa si polarizarea, furnizorul sau SID-ul)
    if(r.d){ linie.appendChild(el("span", "semne deosebire", r.d)); }
    // semnul canalelor transmise acum in retea (TV in browser, player extern), ca in lista de pe televizor
    var tr = el("span", "eticheta transmis ascuns", "În rețea");
    tr.title = "Canalul e transmis acum în rețea (TV în browser sau un player extern)";
    linie.appendChild(tr);
    // DVB-I: canalul de satelit are si varianta de internet; la un canal DVB-I, starea lui din casa
    if(r.dvbi){ linie.appendChild(el("span", "eticheta dvbi", r.dvbi)); }
    var et = el("span", "eticheta ascuns", "Pe televizor");
    linie.appendChild(et);
    corp.appendChild(linie);
    var acum = randEmisiune("acum");
    var progres = el("span", "progres ascuns"); var umplut = el("i"); progres.appendChild(umplut);
    var urm = randEmisiune("urm");
    corp.appendChild(acum); corp.appendChild(progres); corp.appendChild(urm);
    b.appendChild(corp);
    b.addEventListener("click", function(){ porneste(r, b); });
    li.appendChild(b);
    var st = null;
    if(r.ref){
      // steluta: canalul in Favorite sau scos de acolo (aceeasi functie ca tasta FAV de pe televizor)
      st = el("button", "stea"); st.type = "button";
      st.addEventListener("click", function(){ favorit(r, st, li); });
      li.appendChild(st);
      // ghidul canalului (ghid_web.py): emisiunile si inregistrarea lor, pentru canalul acestui rand
      var g = el("a", "ghid", "Ghid");
      g.href = adresa("/ghid?ref=" + encodeURIComponent(r.ref));
      g.setAttribute("aria-label", "Ghidul canalului " + (r.nume || ""));
      li.className = "cu-ghid";
      li.appendChild(g);
      // imaginea live a acestui canal, in fereastra de pe pagina (playerul comun, vezi_live_web.py); in titlul ferestrei
      // si ce il deosebeste de randurile care arata la fel
      li.appendChild(liveButon({ref: r.ref, nume: r.d ? r.nume + " (" + r.d + ")" : r.nume}, {mutaTv: mutaTv}));
    }
    l.appendChild(li);
    var obiect = {b: b, et: et, tr: tr, acum: acum, urm: urm, progres: progres, umplut: umplut, r: r, i: i, st: st, li: li};
    if(st){ puneStea(obiect, r.f); }
    (S.el[r.k] = S.el[r.k] || []).push(obiect);
    if(S.acum && r.k === S.acum){ marcheazaUnul(obiect, true); }
    if(S.transmise.indexOf(r.k) !== -1){ tr.classList.remove("ascuns"); }
    if(r.e){
      if(S.epg.hasOwnProperty(r.e)){ arataEpg(obiect); }
      else if(VEDERE){ li.setAttribute("data-e", r.e); VEDERE.observe(li); }
      else { cer.push(r.e); }
    }
  });
  cereEpg(cer);
}
function marcheazaUnul(o, da){
  o.b.classList.toggle("pornit", da);
  o.et.classList.toggle("ascuns", !da);
  if(da){ o.b.setAttribute("aria-current", "true"); } else { o.b.removeAttribute("aria-current"); }
}
function marcheaza(cheie){
  if(S.acum === cheie){ return; }
  if(S.acum && S.el[S.acum]){ S.el[S.acum].forEach(function(o){ marcheazaUnul(o, false); }); }
  S.acum = cheie;
  if(cheie && S.el[cheie]){ S.el[cheie].forEach(function(o){ marcheazaUnul(o, true); }); }
}
function marcheazaTransmise(l){
  l = l || [];
  if(l.join("|") === S.transmise.join("|")){ return; }
  S.transmise = l;
  Object.keys(S.el).forEach(function(k){
    var da = l.indexOf(k) !== -1;
    S.el[k].forEach(function(o){ if(o.tr){ o.tr.classList.toggle("ascuns", !da); } });
  });
}
function puneEmisiune(nod, e){
  if(!e){ nod.classList.add("ascuns"); return; }
  nod.firstChild.textContent = e.o;
  // acelasi titlu nu se pune din nou (ghidul se reciteste la 30 s): derularea lui nu porneste iar de la capat
  if(nod.lastChild.textContent !== e.t){ nod.lastChild.textContent = e.t; }
  nod.classList.remove("ascuns");
}
function procent(e){
  if(!e || !e.d){ return -1; }
  var p = (acumReceptor() - e.i) / e.d;
  return Math.max(0, Math.min(1, p));
}
function arataEpg(o){
  var d = S.epg[o.r.e];
  var a = d ? d.acum : null;
  puneEmisiune(o.acum, a);
  puneEmisiune(o.urm, d ? d.urm : null);
  var p = procent(a);
  o.progres.classList.toggle("ascuns", p < 0);
  if(p >= 0){ o.umplut.style.width = (p * 100).toFixed(1) + "%"; }
}
function cereEpg(refs){
  refs.forEach(function(r){ if(S.coada.indexOf(r) === -1){ S.coada.push(r); } });
  pompaEpg();
}
function pompaEpg(){
  if(S.epgInCurs || !S.coada.length){ return; }
  var grupa = S.coada.splice(0, 50);
  var gen = S.gen;
  S.epgInCurs = true;
  cerere("/api/canale-epg?refs=" + encodeURIComponent(grupa.join(","))).then(function(d){
    if(!d.result){ return; }
    potriveste(d.ora);
    grupa.forEach(function(r){ S.epg[r] = d.epg[r] || null; });
    if(gen !== S.gen){ return; }
    Object.keys(S.el).forEach(function(k){
      S.el[k].forEach(function(o){ if(o.r.e && grupa.indexOf(o.r.e) !== -1){ arataEpg(o); } });
    });
  }).catch(function(){}).then(function(){ S.epgInCurs = false; pompaEpg(); });
}
function reimprospateazaEpg(){
  if(document.visibilityState !== "visible"){ return; }
  var acum = acumReceptor(), cer = [];
  Object.keys(S.el).forEach(function(k){
    S.el[k].forEach(function(o){
      if(!o.r.e){ return; }
      var d = S.epg[o.r.e];
      if(d && d.acum && d.acum.i + d.acum.d <= acum && cer.indexOf(o.r.e) === -1 && cer.length < 200){
        delete S.epg[o.r.e]; cer.push(o.r.e);
      }
      if(S.epg.hasOwnProperty(o.r.e)){ arataEpg(o); }
    });
  });
  cereEpg(cer);
}
function porneste(r, b){
  if(S.pornire){ return; }
  S.pornire = true;
  b.classList.add("trimis");
  var q = new URLSearchParams();
  q.set("fila", S.tip); q.set("buchet", S.buchet || "toate"); q.set("ref", r.ref);
  cerere("/api/canale-porneste", "POST", q).then(function(d){
    mesaj(d.message || (d.result ? "Pornește pe televizor." : "Canalul nu a pornit."), !d.result);
    if(d.result && d.acum){ marcheaza(d.acum.cheie); arataAcum(d.acum, null); setTimeout(citesteAcum, 1500); }
  }).catch(function(){ mesaj("Receptorul nu răspunde.", true); })
    .then(function(){ S.pornire = false; b.classList.remove("trimis"); });
}
function puneStea(o, f){
  o.r.f = f ? 1 : 0;
  o.st.textContent = f ? "\\u2605" : "\\u2606";
  o.st.setAttribute("aria-pressed", f ? "true" : "false");
  o.st.title = f ? "Scoate din Favorite" : "Adaugă la Favorite";
  o.st.setAttribute("aria-label", (f ? "Scoate din Favorite: " : "Adaugă la Favorite: ") + (o.r.nume || ""));
}
function favorit(r, st, li){
  if(st.disabled){ return; }
  var vrea = r.f ? 0 : 1;
  if(!vrea && !window.confirm("Scoți " + (r.nume || "canalul") + " din Favorite?")){ return; }
  st.disabled = true;
  var q = new URLSearchParams();
  q.set("fila", S.tip); q.set("buchet", S.buchet || "toate"); q.set("ref", r.ref); q.set("vrea", String(vrea));
  cerere("/api/canale-favorit", "POST", q).then(function(d){
    mesaj(d.message || (d.result ? "Gata." : "Favorite nu s-au schimbat."), !d.result);
    if(!d.result){ return; }
    // acelasi canal poate sta de doua ori in lista: toate stelutele lui
    (S.el[r.k] || []).forEach(function(o){ if(o.st){ puneStea(o, d.f); } });
    if(!d.f && S.buchet === "userbouquet.favourites." + S.tip){
      // in lista Favorite randul scos dispare
      (S.el[r.k] || []).forEach(function(o){ if(o.li && o.li.parentNode){ o.li.parentNode.removeChild(o.li); } });
    }
  }).catch(function(){ mesaj("Receptorul nu răspunde.", true); })
    .then(function(){ st.disabled = false; });
}
function arataAcum(a, emisiune){
  var p = $("peTv"); gol(p);
  if(!a || !a.nume){ return; }
  p.appendChild(document.createTextNode("Pe televizor: "));
  p.appendChild(el("b", "", a.nume));
  if(emisiune){ p.appendChild(document.createTextNode(" · " + emisiune.o + " " + emisiune.t)); }
  if(a.standby){ p.appendChild(document.createTextNode(" · în standby")); }
}
function citesteAcum(){
  return cerere("/api/canale-acum").then(function(d){
    if(!d.result){ return; }
    potriveste(d.ora);
    arataAcum(d, d.emisiune);
    marcheaza(d.cheie);
    marcheazaTransmise(d.transmise);
  }).catch(function(){});
}
function laAcum(){
  if(S.grupat){
    // grupa canalului de pe televizor se deschide (daca era inchisa), apoi canalul vine in vedere
    if(!S.grupaAcum){ return; }
    S.spreAcum = true;
    deschideGrupa(S.grupaAcum);
    arataToate();
    return;
  }
  if(S.acumPoz < 0){ return; }
  var gen = S.gen;
  function incearca(){
    if(gen !== S.gen){ return; }
    if(S.randuri.length > S.acumPoz){
      var o = S.el[S.acum] && S.el[S.acum][0];
      if(o){ o.b.scrollIntoView({block: "center"}); o.b.focus({preventScroll: true}); }
      return;
    }
    if(S.gata){ return; }
    if(S.incarca){ setTimeout(incearca, 150); return; }
    pagina(S.urm, gen).then(incearca);
  }
  incearca();
}
$("filaTv").addEventListener("click", function(){ if(S.tip !== "tv"){ S.tip = "tv"; S.ales = {}; S.deschise = {}; S.fundal += 1; incarcaBuchete(); } });
$("filaRadio").addEventListener("click", function(){ if(S.tip !== "radio"){ S.tip = "radio"; S.ales = {}; S.deschise = {}; S.fundal += 1; incarcaBuchete(); } });
$("buchet").addEventListener("change", function(){ S.buchet = $("buchet").value; incarcaLista(); });
$("text").addEventListener("input", function(){
  if(ceasText){ clearTimeout(ceasText); }
  ceasText = setTimeout(function(){ var t = $("text").value.trim(); if(t !== S.text){ S.text = t; incarcaLista(); } }, 250);
});
$("butonFiltre").addEventListener("click", function(){
  var p = $("panouFiltre"), deschis = !p.classList.contains("deschis");
  try { localStorage.setItem("hds_canale_filtre", deschis ? "1" : "0"); } catch(e) {}
  inchideListeleFiltrelor();
  p.classList.toggle("deschis", deschis);
  $("butonFiltre").setAttribute("aria-expanded", deschis ? "true" : "false");
  aseazaPanoul();
});
$("stergeFiltre").addEventListener("click", function(){ S.ales = {}; numarFiltre(); incarcaLista(); });
$("inToate").addEventListener("click", function(){ S.buchet = "toate"; $("buchet").value = "toate"; incarcaLista(); });
$("laAcum").addEventListener("click", laAcum);
window.addEventListener("scroll", maiDeparte, {passive: true});
window.addEventListener("resize", maiDeparte);
if(window.IntersectionObserver){
  new IntersectionObserver(function(e){ if(e[0].isIntersecting){ maiDeparte(); } }, {rootMargin: "800px"}).observe($("capat"));
}
document.addEventListener("visibilitychange", function(){ if(document.visibilityState === "visible"){ citesteAcum(); reimprospateazaEpg(); } });
setInterval(function(){ if(document.visibilityState === "visible"){ citesteAcum(); } }, 5000);
setInterval(reimprospateazaEpg, 30000);
// randul filtrelor: inchis implicit, pe toate latimile; deschis sau inchis cum l-a lasat omul (in browser)
(function(){
  var deschis = false;
  try { deschis = localStorage.getItem("hds_canale_filtre") === "1"; } catch(e) {}
  $("panouFiltre").classList.toggle("deschis", deschis);
  $("butonFiltre").setAttribute("aria-expanded", deschis ? "true" : "false");
})();
aseazaBara();
if(window.ResizeObserver && document.querySelector(".hds-antet")){ new ResizeObserver(aseazaBara).observe(document.querySelector(".hds-antet")); }
incarcaBuchete();
citesteAcum();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------- traducerea paginilor
# Textele sabloanelor de mai sus, traduse la cerere in limba receptorului (traducere_pagini.py). Un text
# nou sau schimbat in sablon se scrie si aici (proba textelor paginilor web il cere).
TEXTE_PAGINA = {
	"html": (
		N_("Canale"),
		N_("Radio"),
		N_("Filtre<span class=\"nrf\" id=\"nrFiltre\"></span>"),
		N_("Șterge filtrele"),
		N_("În aceeași grupă opțiunile bifate se adună cu «sau», între grupe cu «și». Numărul arată câte "
			"canale ar rămâne cu opțiunea bifată."),
		N_("Se citește lista..."),
		N_("Canalul de pe televizor"),
		N_("Caută acum"),
		N_("Felul canalelor"),
		N_("Lista de canale"),
		N_("Caută după nume"),
		N_("Filtre"),
		N_("Lista așa cum e aleasă și filtrată acum, pentru VLC, Kodi sau alt player din casă"),
	),
	"js": (
		N_("browser deconectat"),
		N_("Receptorul a răspuns neașteptat (HTTP"),
		N_("Se citește lista..."),
		N_("Listele nu s-au putut citi."),
		N_("Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."),
		N_("Lista nu s-a putut citi."),
		N_("Închide ceilalți sateliți"),
		N_("Deschide toate canalele pe toți sateliții"),
		N_("Se citesc canalele..."),
		N_("Grupa nu s-a putut citi."),
		N_("Receptorul nu răspunde."),
		N_("Sfârșitul listei."),
		N_("Caută în toate canalele ("),
		N_("Selectează..."),
		N_("alese"),
		N_("Lista aleasă nu are ce filtra."),
		N_("În rețea"),
		N_("Canalul e transmis acum în rețea (TV în browser sau un player extern)"),
		N_("Pe televizor"),
		N_("Ghid"),
		N_("Ghidul canalului"),
		N_("Pornește pe televizor."),
		N_("Canalul nu a pornit."),
		N_("Scoate din Favorite"),
		N_("Adaugă la Favorite"),
		N_("Scoate din Favorite:"),
		N_("Adaugă la Favorite:"),
		N_("Scoți"),
		N_("din Favorite?"),
		N_("Gata."),
		N_("Favorite nu s-au schimbat."),
		N_("Pe televizor:"),
		N_("· în standby"),
	),
}


def _traducePagina(sablon, fel="pagina"):
	"""Sablonul in limba receptorului; fara pachetul HdsWebControl (probele de pe PC), sablonul ca atare."""
	try:
		from .traducere_pagini import traduce
	except ImportError:
		return sablon
	return traduce(sablon, TEXTE_PAGINA, fel)
# ---------------------------------------------------------------- sfarsitul traducerii paginilor
