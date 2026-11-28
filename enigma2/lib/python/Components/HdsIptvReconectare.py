# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsIptvReconectare (0.7.5): canalul de internet care mergea si s-a oprit (internetul a cazut cateva secunde, routerul s-a repornit,
# serverul a inchis fluxul) porneste singur din nou, fara ca omul sa schimbe canalul de doua ori.
#
# Doua straturi, fara sa se calce pe picioare:
# - releul (Components/HdsIptvAdrese.py) reface singur legatura cu serverul de cel mult 6 ori la rand (0,5..4 s, ~16 s); playerul vede
#   numai o pauza. Cand releul renunta, inchide fluxul si playerul (servicemp3) da evEOF; o eroare GStreamer da evUser+10/11/12/16.
# - aici: la evEOF sau la o eroare pe un canal care A MERS, canalul se porneste din nou (acelasi canal, numai daca omul n-a schimbat
#   canalul si receptorul nu e in standby), dupa 2, 5, 10, 20, 30, 60, 60, 60 s (~4 minute: cat dureaza o repornire de router), iar
#   dupa 60 s de redare buna numaratoarea o ia de la capat. Si o imagine care sta pe loc 30 s (mai mult decat releul, ca sa nu se
#   bata intre ele) fara pauza ceruta de om se socoteste cadere.
# Nu se reporneste: un film (cheia „v...” sau o lungime cunoscuta: la sfarsitul unui film EOF e firesc), canalele de satelit.
#
# PORNIREA CU RABDARE (IPT8, 0.7.8; LinuxSat 164215 #145): un canal care inca n-a dat nicio imagine si cade (servicemp3 renunta
# la 15 s fara antete, la 25 s fara PLAYING, sau furnizorul raspunde gol cat canalul lui inca porneste) se porneste singur din
# nou, in tacere, dupa PASI_PORNIRE_S, pana la PORNIRE_S de la alegerea canalului. Numai caderile trecatoare (evEOF, eroarea
# fluxului fara alt motiv, felurile TRECATOARE din sUser+15); un format sau un decodor refuzat (evUser+10/11/12, restul felurilor)
# spune pe loc, ca inainte. Cat e programata o pornire, mesajele de esec (Components/HdsJurnalZapFlux, InfoBarFilmRefuz) si
# semnul "n-a pornit" (Components/HdsIptvRedare.py) asteapta; dupa termen raman ca inainte. Numaratoarea nu se reia la pornirea
# noastra, ci numai la o pornire care nu e a noastra (alt canal, trezirea, intoarcerea din player).
# Fereastra de incarcare a lui HdsIptvRedare apare singura la repornire („Se conectează la server...”): nimic de confirmat (regula 1f).
#
# Emisiunile din arhiva (Screens/HdsIptvArhiva.py, cheia a<id>-...) nu se pornesc din nou: cand una se termina (evEOF dupa ce a mers),
# receptorul trece singur, dupa INAPOI_LA_DIRECT_S, pe canalul ei in direct (numai daca omul n-a schimbat intre timp; cu arhiva oprita
# in setari, nu). Fara asta ecranul ramanea pe ultimul cadru.
#
# Canalele de internet care NU sunt din sursele noastre (IRC, 15.11.2026): liste .m3u puse in buchete, buchetele facute de
# XStreamity sau Bouquet Maker, orice referinta 4097/5001/5002 cu adresa unui flux. Inainte reconectarea le ocolea (eCanalViu cere
# o cale a releului nostru), iar un flux care a mers si s-a oprit ramanea pe ultimul cadru. Acum se pornesc din nou la fel, cu
# aceleasi conditii: au mers, nu sunt film (lungime cunoscuta, extensia unui fisier, /movie/ sau /series/ din Xtream), nu vin de pe
# receptor (127.0.0.1: Radio online si releele locale au reconectarea lor). Fara releul nostru nu exista numaratoarea octetilor:
# imaginea pe loc se judeca numai dupa pozitia data de player. Cu ServiceApp (exteplayer3, gstplayer) pornirea se vede din
# evUpdatedInfo (ServiceApp nu trimite evUser+17), numai cand chiar ServiceApp reda (5001/5002, sau 4097 cu "inlocuieste
# servicemp3"). Playerul propriu al unui plugin (ecranul de redare din XStreamity) nu e bara canalelor: acolo nu ajungem.
#
# Optional: config.usage.hds_iptv_reconectare (Da din fabrica; setup.xml hds_iptv_functii, web /setari?id=hds_iptv_functii). Oprita:
# niciun ceas pornit, nimic urmarit. Partea de sus (Decizie) nu cere enigma2: se probeaza pe PC
# (depozitul de unelte, teste/test_iptv_ipi_075.py).

import re
import time

from Components import HdsIptvSurse as I

_ARHIVA = re.compile(r"^a\d{1,12}-\d{12}-\d{1,4}$")   # aceeasi forma ca HdsIptvClient.cheieArhiva (fara importul clientului aici)

PASI_S = (2, 5, 10, 20, 30, 60, 60, 60)   # asteptarea inaintea fiecarei porniri din nou
SANATOS_S = 60.0                           # atata redare buna sterge numaratoarea
OPRIT_S = 30.0                             # imaginea pe loc atat (releul renunta dupa ~16 s): cadere
VERIFICA_MS = 2000                         # cat de des se uita la imagine, numai cat merge un canal de internet urmarit
INAPOI_LA_DIRECT_S = 3                     # dupa sfarsitul unei emisiuni din arhiva, canalul ei in direct
PASI_PORNIRE_S = (2, 3, 5, 5, 8, 10)       # canalul care n-a dat inca imagine: asteptarea inaintea fiecarei porniri din nou
PORNIRE_S = 45.0                           # cat timp de la alegerea canalului se mai incearca (alte imagini: 30 s ale souphttpsrc)
# felurile din sUser+15 (lib/service/servicemp3.cpp, refuza) dupa care un canal care n-a pornit inca se mai incearca: eroarea
# fluxului fara alt motiv (souphttpsrc fara raspuns), sursa (legatura), formatul nedescoperit (typefind fara octeti: raspuns gol)
TRECATOARE = ("", "eroare", "fisier", "format")


def trecator(cod=None, fel=""):
	"""Caderea dinaintea primei imagini se mai incearca? cod None = evEOF, 16 = alta eroare: dupa felul din sUser+15 (un evEOF venit
	dupa un refuz al aceleiasi porniri, de pilda sourceTimeout la 25 s dupa "negociere", ramane refuz); 10, 11, 12 = sunetul sau
	imaginea refuzate, un element lipsa: nu."""
	if cod in (10, 11, 12):
		return False
	return (fel or "") in TRECATOARE


def eCanalViu(cale):
	"""(sid, cheie) pentru un canal de internet viu al omului, altfel None. Filmele din lista („v<id>.<ext>”) si emisiunile din arhiva
	(„a<id>-<AAAALLZZHHMM>-<minute>”, Screens/HdsIptvArhiva.py) nu: au sfarsit."""
	sid, cheie = I.desparteCale(cale)
	if sid is None or not cheie or cheie.startswith("v") or _ARHIVA.match(cheie):
		return None
	return sid, cheie


SCHEME_FLUX = ("http", "https", "rtsp", "rtmp", "rtmps", "rtp", "udp", "mms", "hls")
# extensiile unui fisier (film, serial, muzica): acolo sfarsitul e firesc, nu o cadere
_EXT_FISIER = re.compile(r"\.(mkv|mp4|m4v|avi|mov|wmv|webm|mpg|mpeg|vob|iso|divx|xvid|3gp|ogv|flv|mp3|flac|ogg|m4a|wav|wma|aac)$", re.I)
# filmele si serialele din Xtream (http://gazda/movie/u/p/1.mkv, /series/...): film, chiar si fara extensie
_VOD_XTREAM = re.compile(r"/(movie|series)/", re.I)
SERVICEAPP_TIPURI = (5001, 5002)            # referintele redate numai de ServiceApp (gstplayer, exteplayer3)
SERVICEAPP_SO = "/usr/lib/enigma2/python/Plugins/SystemPlugins/ServiceApp/serviceapp.so"
SERVICEAPP_INLOCUIESTE = "/etc/enigma2/serviceapp_replaceservicemp3"   # ServiceApp reda si 4097 (citit la pornirea interfetei)


def eFluxDinAfara(cale):
	"""True pentru adresa unui flux viu de pe internet care nu e din sursele noastre (o lista .m3u din buchete, XStreamity,
	Bouquet Maker). Nu: caile releului nostru (eCanalViu), adresele de pe receptor (127.0.0.1, localhost: Radio online si
	releele locale au reconectarea lor), fisierele (extensia unui film sau a unei melodii, /movie/ si /series/ din Xtream)."""
	cale = (cale or "").replace("%3a", ":").replace("%3A", ":").strip()
	if "://" not in cale:
		return False
	schema, rest = cale.split("://", 1)
	if schema.lower() not in SCHEME_FLUX:
		return False
	if I.desparteCale(cale)[0] is not None:
		return False
	# antetele dupa # (servicemp3, ServiceApp: adresa#User-Agent=...) si dupa | (adresa|User-Agent=...) nu fac parte din adresa
	adresa = rest.split("#", 1)[0].split("|", 1)[0]
	gazda = adresa.split("/", 1)[0].rsplit("@", 1)[-1]
	if gazda.startswith("["):
		gazda = gazda[1:].split("]", 1)[0]
	else:
		gazda = gazda.split(":", 1)[0]
	gazda = gazda.lower()
	if not gazda or gazda == "localhost" or gazda.startswith("127.") or gazda == "::1":
		return False
	drum = "/" + adresa.split("/", 1)[1] if "/" in adresa else "/"
	drum = drum.split("?", 1)[0]
	if _EXT_FISIER.search(drum) or _VOD_XTREAM.search(drum):
		return False
	return True


def felCanal(ref):
	"""Ce reconectam pentru o referinta: ("canal", (sid, cheie)) pentru canalele surselor noastre, ("afara", None) pentru un flux
	viu din afara lor, None pentru restul (satelit, cablu, filme, arhiva, adrese de pe receptor)."""
	if ref is None:
		return None
	tip = getattr(ref, "type", 1)
	canal = eCanalViu(ref.getPath()) if tip != 1 else None
	if canal is None:
		canal = eCanalViu(ref.toString())
	if canal is not None:
		return "canal", canal
	if tip != 1 and eFluxDinAfara(ref.getPath()):
		return "afara", None
	return None


def seReconecteaza(ref):
	"""Canalul pe care il pornim singuri din nou cand se opreste (cu optiunea pornita). Components/HdsJurnalZapFlux nu mai pune
	atunci mesajul "Canalul s-a oprit singur." peste fereastra de incarcare."""
	try:
		return _activ() and felCanal(ref) is not None
	except Exception:
		return False


def redaServiceApp(tip, exista=None):
	"""True cand referinta de tipul `tip` e redata de ServiceApp (playerul extern). Pentru 4097 numai cand ServiceApp e instalat
	si "inlocuieste servicemp3" e pus; altfel servicemp3 (GStreamer) trimite evUpdatedInfo si cand nu reda nimic inca."""
	if tip in SERVICEAPP_TIPURI:
		return True
	if tip != 4097:
		return False
	import os
	exista = exista or os.path.exists
	return bool(exista(SERVICEAPP_SO) and exista(SERVICEAPP_INLOCUIESTE))


def refInDirect(ref_text):
	"""Referinta canalului in direct al unei emisiuni din arhiva (acelasi player, numerele si calea canalului din lista, numele lui), sau
	None cand ref_text nu e o emisiune din arhiva."""
	sid, cheie = I.desparteCale(ref_text or "")
	if sid is None or not cheie or not _ARHIVA.match(cheie):
		return None
	tip = ref_text.split(":", 1)[0]
	ref = I.refCanal(sid, "l" + cheie[1:cheie.index("-")])
	parti = ref_text.split(":", 10)
	nume = parti[10].split(":", 1)[1].split(" · ", 1)[0].strip() if len(parti) > 10 and ":" in parti[10] else ""
	return (tip if tip.isdigit() else "4097") + ref[ref.index(":"):] + nume


class Decizie(object):
	"""Hotararile, fara nimic din enigma2. `ceas` se da in probe."""

	def __init__(self, ceas=None):
		self.ceas = ceas or time.monotonic
		self.ref = None             # textul referintei canalului urmarit
		self.a_mers = False         # a avut imagine macar o data de cand a fost ales
		self.pornit = False         # are imagine in pornirea de acum
		self.pornit_la = 0.0
		self.incercari = 0
		self.asteapta = False       # o pornire din nou e programata
		self.pozitie = None
		self.octeti = 0
		self.ultima_miscare = 0.0
		self.pornire_t0 = self.ceas()   # alegerea canalului (pornirea care nu e a noastra), pentru PORNIRE_S
		self.pornire_incercari = 0
		self.repornim = False       # pornirea care urmeaza e a noastra (laCeas a dat True)

	def laStart(self, ref, viu):
		"""Un serviciu nou. Aceeasi referinta = pornirea noastra din nou: tinem minte ca a mers si cate incercari au fost."""
		acum = self.ceas()
		if not viu:
			self.__init__(self.ceas)
			return
		if ref != self.ref:
			self.__init__(self.ceas)
			self.ref = ref
		if not self.repornim:
			# alt canal, trezirea, intoarcerea din player: canalul care n-a pornit inca are iar PORNIRE_S
			self.pornire_t0 = acum
			self.pornire_incercari = 0
		self.repornim = False
		self.asteapta = False
		self.pornit = False
		self.pornit_la = acum
		self.pozitie = None
		self.octeti = 0
		self.ultima_miscare = acum

	def laPornit(self):
		if self.ref is None:
			return
		acum = self.ceas()
		self.a_mers = True
		self.pornit = True
		self.pornit_la = acum
		self.ultima_miscare = acum

	def _pasPornire(self, ref_acum, activ, standby, film, trec):
		"""Canalul n-a dat inca imagine: pasul pornirii din nou, sau None (dupa PORNIRE_S, dupa PASI_PORNIRE_S, caderea nu e trecatoare)."""
		if not activ or standby or film or not trec or self.ref is None or ref_acum != self.ref or self.a_mers or self.asteapta:
			return None
		if self.pornire_incercari >= len(PASI_PORNIRE_S):
			return None
		pas = PASI_PORNIRE_S[self.pornire_incercari]
		if self.ceas() + pas - self.pornire_t0 > PORNIRE_S:
			return None
		return pas

	def pornireInCurs(self):
		"""O pornire din nou a unui canal care n-a dat inca imagine e programata."""
		return self.asteapta and not self.a_mers and self.ref is not None

	def poateReporni(self, ref_acum, activ=True, standby=False, film=False, trec=True):
		"""Fara sa schimbe nimic: canalul care n-a dat inca imagine se porneste singur din nou dupa caderea de acum (sau e deja
		programat). Pentru mesajele de pe ecran, oricare ar fi ordinea ascultatorilor."""
		return self.pornireInCurs() or self._pasPornire(ref_acum, activ, standby, film, trec) is not None

	def laEsec(self, ref_acum, activ=True, standby=False, film=False, trec=True):
		"""Playerul a spus EOF sau o eroare. -> secundele de asteptare pana la pornirea din nou, sau None (nimic de facut).
		trec: caderea e trecatoare (trecator()); conteaza numai cat canalul n-a dat inca imagine."""
		if not self.a_mers:
			pas = self._pasPornire(ref_acum, activ, standby, film, trec)
			if pas is not None:
				self.pornire_incercari += 1
				self.asteapta = True
			return pas
		if not activ or standby or film or self.ref is None or ref_acum != self.ref or self.asteapta:
			return None
		if self.pornit and self.ceas() - self.pornit_la >= SANATOS_S:
			self.incercari = 0
		if self.incercari >= len(PASI_S):
			return None
		pas = PASI_S[self.incercari]
		self.incercari += 1
		self.asteapta = True
		self.pornit = False
		return pas

	def laCeas(self, ref_acum, activ=True, standby=False):
		"""A venit ora pornirii din nou. -> True daca se porneste (acelasi canal, optiunea pornita, receptorul treaza)."""
		if not self.asteapta:
			return False
		self.asteapta = False
		self.repornim = bool(activ and not standby and self.ref is not None and ref_acum == self.ref)
		return self.repornim

	def pas(self, pozitie, octeti, pauza=False):
		"""La VERIFICA_MS cat canalul are imagine. -> True cand imaginea sta pe loc de OPRIT_S (fara pauza ceruta de om).
		Se uita la pozitia imaginii; cand playerul n-o spune, la octetii primiti de releu."""
		if self.ref is None or not self.pornit or self.asteapta:
			return False
		acum = self.ceas()
		if pauza:
			self.ultima_miscare = acum
			return False
		if pozitie is not None:
			if pozitie != self.pozitie:
				self.pozitie = pozitie
				self.ultima_miscare = acum
		elif not octeti or octeti != self.octeti:
			# fara pozitie si fara numaratoarea releului (HLS adus direct) nu se poate judeca: nu se socoteste cadere
			self.octeti = octeti
			self.ultima_miscare = acum
		return acum - self.ultima_miscare >= OPRIT_S


# ------------------------------------------------------------------ pe receptor

def _activ():
	try:
		from Components.config import config
		return bool(config.usage.hds_iptv_reconectare.value)
	except (AttributeError, KeyError, ImportError):
		return True


def _arhivaActiva():
	try:
		from Components.config import config
		return bool(config.usage.hds_iptv_arhiva.value)
	except (AttributeError, KeyError, ImportError):
		return True


def _standby():
	try:
		from Screens import Standby
		return Standby.inStandby is not None
	except ImportError:
		return False


_legaturi = []   # legaturile barelor deschise (bara canalelor, playerul de filme), pentru pornireaContinua


def _jurnal(mesaj):
	"""Randul in hds-zap.log (modulul "reconectare"), ca la asistenta sa se vada pornirile din nou; si in jurnalul interfetei."""
	print("[HdsIptvReconectare] %s" % mesaj)
	try:
		from Components import HdsJurnal
		HdsJurnal.info("zap", "reconectare", mesaj)
	except Exception:
		pass


def _legaturaActiva():
	"""Legatura barei care primeste acum evenimentele serviciului (varful stivei din ServiceEventTracker), altfel ultima."""
	vii = [l for l in _legaturi if not l.inchisa]
	if not vii:
		return None
	try:
		from Components.ServiceEventTracker import ServiceEventTracker
		varf = ServiceEventTracker.InfoBarStack[-1] if ServiceEventTracker.InfoBarStack else None
		for l in vii:
			if l.infobar is varf:
				return l
	except Exception:
		pass
	return vii[-1]


def pornireaContinua(cod=None, fel=None):
	"""Pentru mesajele de esec de pe ecran (Components/HdsJurnalZapFlux, Screens/InfoBarGenerics.InfoBarFilmRefuz): canalul de acum
	n-a dat inca imagine si il pornim singuri din nou dupa caderea asta (cod None = evEOF, altfel N din evUser+N; fel din sUser+15,
	citit din player cand nu se da). True = mesajul asteapta. Nu arunca niciodata."""
	try:
		l = _legaturaActiva()
		return l is not None and l.pornireaContinua(cod, fel)
	except Exception as e:
		print("[HdsIptvReconectare] pornireaContinua: %s" % type(e).__name__)
		return False


def pornireInCurs(infobar=None):
	"""O pornire din nou a canalului care n-a dat inca imagine e deja programata (laEsec a hotarat). Pentru Components/HdsIptvRedare,
	al carui ascultator vine dupa al nostru (Screens/InfoBarGenerics._hdsLeagaIptvPe). Nu arunca niciodata."""
	try:
		l = None
		if infobar is not None:
			for x in _legaturi:
				if x.infobar is infobar and not x.inchisa:
					l = x
		if l is None:
			l = _legaturaActiva()
		return l is not None and l.decizie.pornireInCurs()
	except Exception:
		return False


class Legatura(object):
	"""Pe bara canalelor (Screens/InfoBarGenerics._hdsLeagaIptvPe), langa fereastra de incarcare. Oprita: nu face nimic."""

	def __init__(self, infobar):
		self.inchisa = False
		# pornirea cu rabdare numai pe bara canalelor: in playerul de filme refuzul are fereastra lui, care asteapta OK
		self.pe_canal = getattr(infobar, "leavePlayerConfirmed", None) is None
		_legaturi.append(self)
		if hasattr(infobar, "onClose"):
			infobar.onClose.append(self._inchide)
		self.session = infobar.session
		self.infobar = infobar
		self.decizie = Decizie()
		self.serviciu = None        # eServiceReference de pornit din nou
		self.cheie = None
		self.serviceapp = False     # canalul urmarit e redat de ServiceApp (evUpdatedInfo = a pornit)
		self.ceas_repornire = None
		self.ceas_veghe = None
		self.arhiva = None          # (referinta emisiunii din arhiva, a mers) cat se reda una
		self.ceas_direct = None

	def _ref(self):
		ref = self.session.nav.getCurrentlyPlayingServiceReference()
		return ref if ref is not None and ref.valid() else None

	def _refText(self):
		ref = self._ref()
		return ref.toString() if ref is not None else None

	def _film(self):
		"""O lungime cunoscuta inseamna fisier (un film din lista M3U): acolo EOF e sfarsitul firesc."""
		try:
			service = self.session.nav.getCurrentService()
			seek = service and service.seek()
			lungime = seek.getLength() if seek else None
			return bool(lungime and not lungime[0] and lungime[1] > 0)
		except Exception:
			return False

	def _veghe(self, porneste):
		if porneste:
			if self.ceas_veghe is None:
				from enigma import eTimer
				self.ceas_veghe = eTimer()
				self.ceas_veghe.callback.append(self._pas)
			self.ceas_veghe.start(VERIFICA_MS, False)
		elif self.ceas_veghe is not None:
			self.ceas_veghe.stop()

	def laStart(self):
		ref = self._ref()
		text = ref.toString() if ref is not None else ""
		self.arhiva = [text, False] if refInDirect(text) else None
		if not _activ():
			self.decizie.laStart(None, False)
			self._veghe(False)
			return
		fel = felCanal(ref)
		if fel is None:
			self.decizie.laStart(None, False)
			self.serviciu = None
			self._veghe(False)
			return
		from enigma import eServiceReference
		self.serviciu = eServiceReference(ref.toString())
		# un flux din afara surselor noastre nu trece prin releu: fara numaratoarea octetilor (stareFlux)
		self.cheie = fel[1]
		self.serviceapp = redaServiceApp(getattr(ref, "type", 0))
		self.decizie.laStart(ref.toString(), True)

	def laInfo(self):
		"""evUpdatedInfo. ServiceApp nu trimite evUser+17 si nici evVideoSizeChanged la orice flux: evUpdatedInfo vine la ~1 s dupa
		ce playerul extern a pornit redarea, deci inseamna "a pornit". Cu servicemp3 nu (acolo vine si din etichetele fluxului,
		inainte de prima imagine)."""
		if self.decizie.ref is None or self.decizie.pornit or self.decizie.asteapta or not self.serviceapp:
			return
		self.laPornit()

	def laPornit(self):
		if self.arhiva is not None:
			self.arhiva[1] = True
		if self.decizie.ref is None:
			return
		self.decizie.laPornit()
		self._veghe(True)

	def _inchide(self):
		self.inchisa = True
		if self in _legaturi:
			_legaturi.remove(self)

	def _felRefuz(self):
		"""Felul refuzului spus de servicemp3 in sUser+15 ("eroare", "format", "video"...), sau "" (ServiceApp, niciun motiv)."""
		try:
			from enigma import iServiceInformation
			service = self.session.nav.getCurrentService()
			info = service and service.info()
			motiv = info.getInfoString(iServiceInformation.sUser + 15) if info else ""
			return (motiv or "").split("|", 1)[0]
		except Exception:
			return ""

	def _trecator(self, cod, fel=None):
		"""trecator() pentru pornirea de acum, plus: numai pe bara canalelor, iar la sursele noastre releul n-a spus deja motivul
		(refuzul serverului, conexiunile ocupate, contul: are fereastra lui, HdsIptvLucru.eroareRedare, si o pornire din nou ar
		cere iar contului care tocmai a refuzat)."""
		if not self.pe_canal or not trecator(cod, self._felRefuz() if fel is None else fel):
			return False
		if self._protejatDrm():
			# DRM1: fluxul DVB-I e criptat cu DRM (incercarea din casa): o pornire din nou nu-l face sa mearga
			return False
		if self.cheie:
			try:
				from Components import HdsIptvAdrese as A
				f = A.stareFlux(*self.cheie) or {}
				if f.get("motiv") or f.get("eroare_sursa"):
					return False
			except Exception:
				pass
		return True

	def _protejatDrm(self):
		"""Canalul de acum e un canal DVB-I gasit criptat cu DRM (Components/HdsDvbIDate.protejatDrm)."""
		try:
			ref = self._ref()
			if ref is None:
				return False
			from Components import HdsDvbIDate as D
			# adresa din referinta, ca la buchet (HdsDvbIDate.urlDinRef); altfel calea data de nucleu
			url = D.urlDinRef(ref.toString()) if hasattr(ref, "toString") else ""
			return D.protejatDrm(url) or D.protejatDrm(ref.getPath())
		except Exception:
			return False

	def pornireaContinua(self, cod=None, fel=None):
		"""Vezi pornireaContinua() de sus: aceeasi judecata ca laEsec, fara sa schimbe nimic."""
		if self.decizie.ref is None or not _activ():
			return False
		if self.decizie.pornireInCurs():
			return True
		return self.decizie.poateReporni(self._refText(), True, _standby(), self._film(), self._trecator(cod, fel))

	def laEsec(self, cod=None):
		"""evEOF (cod None) sau evUser+cod (10, 11, 12, 16)."""
		if self.arhiva is not None and self.arhiva[1]:
			self._spreDirect()
			return
		if self.decizie.ref is None:
			return
		self._caderea("evEOF" if cod is None else "eroarea %d" % cod, self._trecator(cod))

	def _spreDirect(self):
		"""Emisiunea din arhiva s-a terminat (sau a cazut dupa ce a mers): peste INAPOI_LA_DIRECT_S, canalul ei in direct."""
		if self.ceas_direct is None:
			from enigma import eTimer
			self.ceas_direct = eTimer()
			self.ceas_direct.callback.append(self._direct)
		self.ceas_direct.start(INAPOI_LA_DIRECT_S * 1000, True)

	def _direct(self):
		a = self.arhiva
		if a is None or self._refText() != a[0] or _standby() or not _arhivaActiva():
			return
		direct = refInDirect(a[0])
		if not direct:
			return
		print("[HdsIptvReconectare] emisiunea din arhiva s-a terminat: canalul in direct")
		from enigma import eServiceReference
		self.session.nav.playService(eServiceReference(direct))

	def _caderea(self, de_ce, trec=True):
		d = self.decizie
		a_mers = d.a_mers
		pas = d.laEsec(self._refText(), _activ(), _standby(), self._film(), trec)
		if pas is None:
			if d.ref is not None and a_mers and not d.asteapta:
				print("[HdsIptvReconectare] %s: nu se mai porneste din nou (incercari %d)" % (de_ce, d.incercari))
			elif d.ref is not None and not a_mers and not d.asteapta and _activ():
				_jurnal("%s inainte de prima imagine, dupa %d s de la alegere: %s" % (de_ce, int(d.ceas() - d.pornire_t0),
					"nu se mai incearca (mesajul ramane)" if trec else "refuzul ramane (nu se mai incearca)"))
			return
		if not a_mers:
			_jurnal("%s inainte de prima imagine, dupa %d s de la alegere: canalul porneste din nou peste %d s (incercarea %d)" % (
				de_ce, int(d.ceas() - d.pornire_t0), pas, d.pornire_incercari))
		else:
			print("[HdsIptvReconectare] %s: canalul porneste din nou peste %d s (incercarea %d)" % (de_ce, pas, d.incercari))
		self._veghe(False)
		if self.ceas_repornire is None:
			from enigma import eTimer
			self.ceas_repornire = eTimer()
			self.ceas_repornire.callback.append(self._reporneste)
		self.ceas_repornire.start(pas * 1000, True)

	def _reporneste(self):
		if not self.decizie.laCeas(self._refText(), _activ(), _standby()) or self.serviciu is None:
			self.decizie.repornim = False
			return
		try:
			self.session.nav.playService(self.serviciu, checkParentalControl=False, forceRestart=True, adjust=False)
		except TypeError:
			self.session.nav.playService(self.serviciu, forceRestart=True)

	def _pas(self):
		if self.decizie.ref is None or not _activ():
			self._veghe(False)
			return
		pozitie, pauza = None, False
		try:
			service = self.session.nav.getCurrentService()
			seek = service and service.seek()
			rez = seek.getPlayPosition() if seek else None
			pozitie = rez[1] if rez and not rez[0] else None
			pauza = getattr(self.infobar, "seekstate", (0,))[0] == 1
		except Exception:
			pass
		octeti = 0
		if pozitie is None and self.cheie:
			try:
				from Components import HdsIptvAdrese as A
				octeti = (A.stareFlux(*self.cheie) or {}).get("octeti") or 0
			except Exception:
				octeti = 0
		if self.decizie.pas(pozitie, octeti, pauza):
			self._caderea("imaginea sta pe loc de %d s" % OPRIT_S)
