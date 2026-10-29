# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsEditorCanale.py: editorul de canale, partea comuna a ecranelor de pe televizor (Screens/HdsEditorCanale*.py) si a
# paginii web /editor-canale (Plugins/Extensions/HdsWebControl/editor_canale_web.py).
#
# SESIUNEA: o singura editare odata, a televizorului sau a unui browser (zavorul _ZAVOR). Cine vine al doilea primeste
# Ocupat (cine, nume, de cand, cate schimbari nesalvate) si poate prelua sesiunea; sesiunea luata ridica Preluat la
# urmatoarea operatie. Sesiunea web se elibereaza singura dupa VIATA_WEB_S fara bataie, numai fara schimbari nesalvate.
#
# DATELE (Components/HdsEditorCanaleDate.py) se citesc din /etc/enigma2, cu lista de servicii luata din memoria enigma2
# (saveServicelist intr-un fisier din /tmp: are PID-urile invatate de la ultima scriere). Obiectele datelor nu se
# schimba pe loc: o operatie face obiecte noi, deci anularea tine numai obiectele vechi ale celor atinse (pasul: buchetele,
# serviciile, transponderele, listele parentale, asa cum erau inainte). Refacerea e anularea anularii.
#
# SALVAREA (salveaza_fundal), in ordine:
#  1. pe firul enigma2: lista de canale de pe televizor nu e in modul de mutare sau de editare (eDVBServiceList din
#     startEdit tine un eBouquet* in harta pe care reloadBouquets o goleste), apoi lista din memorie scrisa in /tmp;
#  2. pe un fir: unirea cu ce s-a schimbat intre timp pe receptor (o cautare de canale, FAV de pe bara): un serviciu
#     neatins de editor se ia din memorie (PID-urile invatate), unul nou din memorie intra, unul atins de editor ramane al
#     editorului; un buchet neatins nu se scrie; unul atins si schimbat si pe disc ramane al editorului (avertisment);
#     copia de siguranta datata a fisierelor de acum (ultimele MAX_COPII); scrierea sigura (.nou, fsync, rename);
#  3. pe firul enigma2: lib/dvb/db.cpp al imaginii nu goleste serviciile la reloadServicelist si addService nu
#     suprascrie un serviciu existent, deci serviciile sterse sau schimbate se scot intai din memorie (removeService),
#     transponderele sterse cu removeServices; apoi reloadServicelist, reloadBouquets, controlul parental recitit,
#     memoriile indexului de cautare si ale paginilor web uitate, lista de canale a barii citita din nou;
#  4. verificarea: lista din memorie scrisa din nou in /tmp si comparata (pe un fir) cu ce s-a scris.
#
# FIRUL: toate metodele se cheama de pe firul enigma2; lucrul greu (citirea, unirea, scrierea, copiile) merge pe un fir
# separat (_Fir), iar rezultatul se preda inapoi printr-un eTimer. Cat lucreaza firul, sesiunea e ocupata.
#
# Nimic din enigma2 la incarcare: legatura cu nucleul e in clasa Nucleu (importurile in metode); probele de pe PC dau
# alt nucleu (pune_nucleu).

import json
import os
import re
import shutil
import tarfile
import threading
import time

try:
	from Components import HdsEditorCanaleDate as D
except ImportError:  # pe PC, in probe
	import HdsEditorCanaleDate as D
try:
	from Components import HdsEditorCanaleUnelte as U
except ImportError:
	import HdsEditorCanaleUnelte as U

DIRECTOR = D.DIRECTOR
DOSAR_COPII = "/etc/enigma2/hds-copii-canale"
TEMPORAR = "/tmp/hds-editor-lamedb"
MAX_COPII = 10
MAX_ANULARI = 50
VIATA_WEB_S = 120
LOC_MINIM = 2 * 1024 * 1024
FISIERE_COPIE = ("lamedb", "lamedb5", "bouquets.tv", "bouquets.radio", "blacklist", "whitelist")
# buchetele refacute de alte module ale imaginii (schimbarile facute in editor se pot pierde): cautarea DAB+ / DVB-T2
# din satelit (Hds/DabT2), canalele de pe internet (Plugins/SystemPlugins/HdsDvbI), ultima scanare (enigma2)
BUCHETE_AUTOMATE = {"userbouquet.hds_dab.radio": "dabt2", "userbouquet.hds_t2.tv": "dabt2",
	"userbouquet.hdsdvbi.tv": "dvbi", "userbouquet.hdsdvbi.radio": "dvbi",
	"userbouquet.LastScanned.tv": "scanare", "userbouquet.LastScanned.radio": "scanare"}
PREFIXE_COPIE = ("userbouquet.", "subbouquet.", "alternatives.")
TV = "tv"
WEB = "web"


def _t(text):
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


# buchetele Favorite (TV si radio) si numele lor implicite din fisier: aratate _t("Favourites"), ca in lista buchetelor
# (Components/ServiceList.py, NUME_FAVORITE) si in titlu; un nume ales de om ramane al lui; fisierul nu se schimba
FAVORITE = ("userbouquet.favourites.tv", "userbouquet.favourites.radio")
NUME_FAVORITE = ("Favourites (TV)", "Favourites (Radio)", "Favourites", "")


def nume_favorite_aratat(buchet_id, nume_fisier):
	"""Numele aratat al unui buchet Favorite cu numele implicit (tradus), altfel None."""
	if buchet_id in FAVORITE and (nume_fisier or "").strip() in NUME_FAVORITE:
		return _t("Favourites")
	return None


class _FormaSimpla(str):
	"""Pluralul fara Components/HdsPlural: % pune numarul numai unde forma il are (forma de 1 poate fi fara cifra)."""

	def __mod__(self, n):
		return self.replace("%d", str(n))


def ngettext(unu, multe, n):
	"""Pluralul tradus (Components/HdsPlural.ngettext: o Forma, al carei % merge si cand forma de 1 nu are numarul).
	Numele e cel stiut de xgettext (msgid si msgid_plural ajung in enigma2.pot)."""
	try:
		try:
			from Components import HdsPlural as P
		except ImportError:
			import HdsPlural as P
		return P.ngettext(unu, multe, n)
	except Exception:
		return _FormaSimpla(unu if n == 1 else multe)


def _jurnal(text):
	print("[HdsEditorCanale] %s" % text)


# ---------------------------------------------------------------- erorile

class Eroare(Exception):
	"""O operatie care nu se poate face; mesaj() e textul pentru om (tradus)."""

	def __init__(self, mesaj):
		Exception.__init__(self, mesaj)
		self.text = mesaj

	def mesaj(self):
		return self.text


def _cine_text(cine, nume):
	if cine == TV:
		return _t("pe televizor")
	if nume:
		return _t("în interfața web (%s)") % nume
	return _t("în interfața web")


class Ocupat(Eroare):
	def __init__(self, cine, nume="", de_la=0, nesalvate=0, lucreaza=False):
		self.cine, self.nume, self.de_la, self.nesalvate, self.lucreaza = cine, nume, de_la, nesalvate, lucreaza
		if lucreaza:
			text = _t("Editorul lucrează încă (citește sau salvează lista). Încearcă din nou peste câteva secunde.")
		else:
			text = _t("Lista de canale e deschisă acum %s.") % _cine_text(cine, nume)
			if nesalvate:
				text += " " + ngettext("Are o schimbare nesalvată.", "Are %d schimbări nesalvate.", nesalvate) % \
					nesalvate
		Eroare.__init__(self, text)


class Preluat(Eroare):
	def __init__(self, cine, nume=""):
		self.cine, self.nume = cine, nume
		Eroare.__init__(self, _t("Lista de canale a fost preluată %s. Schimbările nesalvate de aici s-au pierdut.")
			% _cine_text(cine, nume))


# ---------------------------------------------------------------- nucleul (numai pe receptor)

class Nucleu(object):
	"""Legatura cu enigma2. Probele dau un nucleu fals cu aceleasi metode."""

	def memorie_lamedb(self, temporar=TEMPORAR):
		"""Lista de servicii din memorie (octeti), sau None. saveServicelist opreste enigma2 (eFatal) cand nu poate
		deschide fisierul: se verifica locul liber si fisierul se face intai de aici."""
		try:
			from enigma import eDVBDB
			db = eDVBDB.getInstance()
			if db is None:
				return None
			try:
				st = os.statvfs(os.path.dirname(temporar) or "/tmp")
				if st.f_bavail * st.f_frsize < LOC_MINIM:
					return None
			except (OSError, AttributeError):
				pass
			with open(temporar, "wb"):
				pass
			try:
				db.saveServicelist(temporar)
				with open(temporar, "rb") as f:
					date = f.read()
			finally:
				try:
					os.remove(temporar)
				except OSError:
					pass
			if not date.startswith(b"eDVB services /") or not date.rstrip(b"\n").endswith(D.SFARSIT.encode("ascii")):
				return None
			return date
		except Exception as e:
			_jurnal("lista din memorie: %r" % (e,))
			return None

	def lista_tv_ocupata(self):
		"""Motivul pentru care listele nu se pot reincarca acum (lista barii in mutare sau editare), sau None."""
		try:
			from Screens.InfoBar import InfoBar
			csel = InfoBar.instance and InfoBar.instance.servicelist
			if csel is None:
				return None
			if getattr(csel, "movemode", False) or getattr(csel, "bouquet_mark_edit", 0):
				return _t("Lista de canale de pe televizor e în modul de mutare sau de editare. Ieși din el și "
					"salvează din nou.")
		except Exception as e:
			_jurnal("lista barii: %r" % (e,))
		return None

	def aplica(self, de_scos, tp_de_scos):
		"""Scoaterea din memorie (servicii, transpondere), apoi reincarcarea listei si a buchetelor."""
		from enigma import eDVBDB, eServiceReference
		db = eDVBDB.getInstance()
		for ref in de_scos:
			try:
				db.removeService(eServiceReference(ref))
			except Exception as e:
				_jurnal("scoaterea %s: %r" % (ref, e))
		for ns, tsid, onid, poz in tp_de_scos:
			try:
				db.removeServices(ns - 0x100000000 if ns >= 0x80000000 else ns, tsid, onid, poz)
			except Exception as e:
				_jurnal("transponderul %08x:%04x:%04x: %r" % (ns, tsid, onid, e))
		db.reloadServicelist()
		db.reloadBouquets()

	def dupa_reincarcare(self):
		"""Controlul parental, memoriile celorlalte module si lista de canale a barii, la zi."""
		try:
			from Components import ParentalControl
			pc = getattr(ParentalControl, "parentalControl", None)
			if pc is not None:
				pc.open()
		except Exception as e:
			_jurnal("controlul parental: %r" % (e,))
		for modul in ("Components.HdsIndexCanale", "Components.HdsFavorite",
				"Plugins.Extensions.HdsWebControl.canale_web"):
			try:
				m = __import__(modul, fromlist=["uita"])
				m.uita()
			except Exception:
				pass
		try:
			from Screens.InfoBar import InfoBar
			csel = InfoBar.instance and InfoBar.instance.servicelist
			if csel is not None:
				csel.bouquetNumOffsetCache = {}
				root = csel.getRoot()
				cur = csel.getCurrentSelection()
				fisier = D.Referinta(root.toString()).fisier() if root is not None and root.valid() else None
				if fisier and not os.path.exists(os.path.join(DIRECTOR, fisier)):
					csel.showFavourites()
				elif root is not None and root.valid():
					csel.setRoot(root)
					if cur is not None and cur.valid():
						csel.servicelist.setCurrent(cur)
		except Exception as e:
			_jurnal("lista barii: %r" % (e,))

	def mod_parental(self):
		try:
			from Components.config import config
			return config.ParentalControl.type.value
		except Exception:
			return "blacklist"

	def ceas(self, functie):
		"""Un ceas care cheama functie() pe firul enigma2 (None pe PC)."""
		try:
			from enigma import eTimer
		except ImportError:
			return None
		c = eTimer()
		try:
			c.callback.append(functie)
		except AttributeError:
			c.timeout.get().append(functie)
		return c


_NUCLEU = [None]


def pune_nucleu(n):
	"""Probele: alt nucleu (None = cel adevarat)."""
	_NUCLEU[0] = n


def _nucleu():
	if _NUCLEU[0] is None:
		_NUCLEU[0] = Nucleu()
	return _NUCLEU[0]


# ---------------------------------------------------------------- firul

class _Fir(object):
	"""functie() pe un fir; la_gata(rezultat) sau la_eroare(Eroare) pe firul enigma2 (printr-un eTimer). Fara eTimer
	(pe PC) totul ruleaza pe loc."""

	def __init__(self, functie, la_gata, la_eroare):
		self.functie, self.la_gata, self.la_eroare = functie, la_gata, la_eroare
		self.rezultat = self.eroare = None
		self.gata = threading.Event()
		self.ceas = _nucleu().ceas(self._verifica)

	def porneste(self):
		if self.ceas is None:
			self._ruleaza()
			self._preda()
			return
		threading.Thread(target=self._ruleaza, name="HdsEditorCanale").start()
		self.ceas.start(30, False)

	def _ruleaza(self):
		try:
			self.rezultat = self.functie()
		except Eroare as e:
			self.eroare = e
		except Exception as e:
			_jurnal("pe fir: %r" % (e,))
			import traceback
			traceback.print_exc()
			self.eroare = Eroare(_t("Lista de canale nu s-a putut citi sau scrie."))
		self.gata.set()

	def _verifica(self):
		if not self.gata.is_set():
			return
		self.ceas.stop()
		self._preda()

	def _preda(self):
		if self.eroare is not None:
			if self.la_eroare is not None:
				self.la_eroare(self.eroare)
			else:
				_jurnal("eroare fara ascultator: %s" % self.eroare.mesaj())
		elif self.la_gata is not None:
			self.la_gata(self.rezultat)


def _pe_fir(tinta, functie, la_gata, la_eroare=None):
	"""Firul pus in tinta._lucru INAINTE de pornire (pe PC la_gata vine pe loc si il face None)."""
	f = _Fir(functie, la_gata, la_eroare)
	tinta._lucru = f
	f.porneste()


# ---------------------------------------------------------------- zavorul

_ZAVOR = {"s": None}
_ASCULTATORI = []


def asculta(functie):
	"""functie(fel, date) dupa "salvat", "intors", "preluat", "inchis"."""
	if functie not in _ASCULTATORI:
		_ASCULTATORI.append(functie)


def nu_mai_asculta(functie):
	try:
		_ASCULTATORI.remove(functie)
	except ValueError:
		pass


def _anunta(fel, date=None):
	for f in list(_ASCULTATORI):
		try:
			f(fel, date)
		except Exception as e:
			_jurnal("un ascultator a cazut: %r" % (e,))


def sesiune():
	s = _ZAVOR["s"]
	if s is not None and s.cine == WEB and s._expirata():
		s._elibereaza("expirat")
		s = None
	return s


def ocupat_de():
	s = sesiune()
	if s is None:
		return None
	return {"cine": s.cine, "nume": s.nume, "de_la": s.de_la, "nesalvate": s.nesalvate(), "id": s.id_client,
		"lucreaza": s.lucreaza()}


def _verifica_liber(cine, id_client):
	s = sesiune()
	if s is None:
		return
	if s.cine == cine and s.id_client == id_client:
		s._elibereaza("redeschis")
		return
	raise Ocupat(s.cine, s.nume, s.de_la, s.nesalvate(), s.lucreaza())


def _citeste_tot(director, memorie, sateliti):
	return D.citeste_dosar(director, memorie, sateliti)


def deschide(cine=TV, nume="", id_client="", director=DIRECTOR, sateliti=D.SATELITI, preia=False):
	"""Sesiunea, pe loc (probe si scripturi; pe 9000 de servicii tine firul o secunda)."""
	if preia:
		_ia_de_la_celalalt(cine, nume)
	_verifica_liber(cine, id_client)
	memorie = _nucleu().memorie_lamedb()
	d = _citeste_tot(director, memorie, sateliti)
	return Sesiune(d, cine, nume, id_client, director)


def deschide_fundal(cine=TV, nume="", la_gata=None, la_eroare=None, id_client="", director=DIRECTOR,
		sateliti=D.SATELITI, preia=False):
	"""Sesiunea, cu citirea pe un fir. Zavorul se ia pe loc (cine vine intre timp vede „lucreaza”)."""
	if preia:
		_ia_de_la_celalalt(cine, nume)
	_verifica_liber(cine, id_client)
	memorie = _nucleu().memorie_lamedb()
	s = Sesiune(D.Date(), cine, nume, id_client, director, gata=False)

	def citeste():
		d = _citeste_tot(director, memorie, sateliti)
		# pe acelasi fir: vederile tuturor serviciilor (cea mai lunga parte a primei liste), cat sesiunea e ocupata
		s._incarca(d)
		s._toate_canalele()
		s._numere()
		return d

	def gata(d):
		if not s.valida():
			return
		s._lucru = None
		if la_gata is not None:
			la_gata(s)

	def eroare(e):
		s._lucru = None
		s._elibereaza("eroare")
		if la_eroare is not None:
			la_eroare(e)

	_pe_fir(s, citeste, gata, eroare)
	return s


def preia(cine=TV, nume=""):
	"""Sesiunea celuilalt se inchide (schimbarile ei nesalvate se pierd); urmeaza deschide*."""
	_ia_de_la_celalalt(cine, nume)


def _ia_de_la_celalalt(cine, nume):
	s = _ZAVOR["s"]
	if s is None:
		return
	if s.lucreaza():
		raise Ocupat(s.cine, s.nume, s.de_la, s.nesalvate(), True)
	s._preluata = (cine, nume)
	s._elibereaza("preluat")


# ---------------------------------------------------------------- vederile (ce primesc ecranele)

class BuchetInfo(object):
	__slots__ = ("id", "nume", "n", "radio", "ascuns", "favorite", "parinte", "blocat", "nume_intreg")


class IntrareInfo(object):
	__slots__ = ("id", "fel", "nume", "ref", "numar", "ascuns", "blocat", "mort", "serviciu", "buchet_id", "numerotat",
		"cheie", "descriere")


class TransponderInfo(object):
	__slots__ = ("cheie", "tp_cheie", "poz", "poz_text", "frecv", "pol", "sr", "text", "tp_text", "n", "fel")


class CanalInfo(object):
	"""Un serviciu din lamedb, cu ce trebuie aratat (pozitia, transponderul, blocarea)."""
	__slots__ = ("ref", "cheie", "nume", "furnizor", "poz", "poz_text", "frecv", "pol", "sr", "sid", "tip", "hd", "acces",
		"ascuns", "blocat", "are_video", "are_sunet", "tp_cheie", "tp_text", "k5", "stype", "steaguri", "ordine")


# ---------------------------------------------------------------- pasii (anularea)

class _Pas(object):
	__slots__ = ("nume", "b", "s", "t", "p")

	def __init__(self, nume):
		self.nume = nume
		self.b = {}      # id buchet -> Buchet sau None (nu exista)
		self.s = {}      # k5 -> Serviciu sau None
		self.t = {}      # cheie transponder -> Transponder sau None
		self.p = None    # (blacklist, whitelist) de dinainte

	def gol(self):
		return not (self.b or self.s or self.t or self.p is not None)


class _InPas(object):
	def __init__(self, s, nume):
		self.s, self.nume = s, nume

	def __enter__(self):
		self.s._verifica()
		self.s._pas = _Pas(self.nume)
		return self.s._pas

	def __exit__(self, tip, val, tb):
		pas = self.s._pas
		self.s._pas = None
		if tip is not None:
			self.s._restabileste(pas)
			return False
		if pas.nume is None or not self.s._a_schimbat(pas):
			self.s._restabileste(pas)
			return False
		if self.s._salvat_poz > len(self.s._anulare):
			self.s._salvat_poz = -1     # starea salvata era pe drumul refacerii, care se pierde acum
		self.s._anulare.append(pas)
		if len(self.s._anulare) > MAX_ANULARI:
			del self.s._anulare[0]
			if self.s._salvat_poz >= 0:
				self.s._salvat_poz -= 1
		self.s._refacere = []
		self.s._schimbat()
		return False


# ---------------------------------------------------------------- sesiunea

class Sesiune(object):

	def __init__(self, date, cine, nume, id_client, director=DIRECTOR, gata=True):
		self.cine, self.nume, self.id_client, self.director = cine, nume, id_client, director
		self.de_la = time.time()
		self.bataie = time.time()
		self._lucru = None
		self._unealta = None    # firul unei unelte (numai citeste): operatiile asteapta, citirile si inchiderea nu
		self._valida = True
		self._preluata = None
		self._pas = None
		self._anulare = []
		self._refacere = []
		self._salvat_poz = 0
		self._versiune = 1
		self._cache = {}        # ce se trage din buchete: se uita la fiecare schimbare
		self._cc = {}           # k5 -> (Serviciu, Transponder, versiunea parentala, CanalInfo): ramane
		self._ctp = {}          # cheie transponder -> (Transponder, (poz, poz_text, frecv, pol, sr, text))
		self._toate = None      # (versiunea lamedb, versiunea parentala, [CanalInfo] dupa nume)
		self._v_par = 0
		self._mod_par = None
		self.d = date
		self._baza = None
		self.ultima_copie = None
		_ZAVOR["s"] = self
		if gata:
			self._incarca(date)

	# ------------------------------------------------ starea

	def _incarca(self, d):
		self.d = d
		self._baza = (d.lamedb.copie(), dict(d.buchete), d.blacklist, d.whitelist)
		self._anulare, self._refacere, self._salvat_poz = [], [], 0
		self._schimbat()

	def _schimbat(self):
		self._versiune += 1
		self._cache = {}

	def _parental_schimbat(self):
		self._v_par += 1
		self._cache.pop("parental", None)

	def versiune(self):
		return self._versiune

	def valida(self):
		return self._valida and _ZAVOR["s"] is self

	def lucreaza(self):
		"""Citirea, salvarea sau intoarcerea la o copie merg pe fir: nimic altceva nu se face pe sesiune."""
		return self._lucru is not None

	def unealta_merge(self):
		"""O unealta (canalele de test, dublurile...) citeste pe fir: citirile merg, operatiile asteapta."""
		return self._unealta is not None

	def atinge(self):
		"""Bataia sesiunii web (pagina e deschisa)."""
		self.bataie = time.time()

	def _expirata(self):
		return (self.cine == WEB and not self.lucreaza() and self.nesalvate() == 0
			and time.time() - self.bataie > VIATA_WEB_S)

	def _elibereaza(self, motiv):
		self._valida = False
		if _ZAVOR["s"] is self:
			_ZAVOR["s"] = None
		_anunta("inchis" if motiv != "preluat" else "preluat", {"cine": self.cine, "motiv": motiv})

	def inchide(self):
		if self.lucreaza():
			raise Ocupat(self.cine, self.nume, self.de_la, self.nesalvate(), True)
		if self._valida:
			self._elibereaza("inchis")

	def _verifica(self, chiar_daca_lucreaza=False):
		if not self.valida():
			if self._preluata:
				raise Preluat(*self._preluata)
			raise Eroare(_t("Sesiunea editorului s-a închis. Deschide din nou editorul."))
		if (self.lucreaza() or self.unealta_merge()) and not chiar_daca_lucreaza:
			raise Ocupat(self.cine, self.nume, self.de_la, self.nesalvate(), True)
		self.bataie = time.time()

	def nesalvate(self):
		if self._salvat_poz < 0:
			return max(1, len(self._anulare))
		return abs(len(self._anulare) - self._salvat_poz)

	def de_anulat(self):
		return self._anulare[-1].nume if self._anulare else None

	def de_refacut(self):
		return self._refacere[-1].nume if self._refacere else None

	# ------------------------------------------------ pasii

	def _in_pas(self, nume):
		return _InPas(self, nume)

	def _tine_b(self, id_):
		p = self._pas
		if p is not None and id_ not in p.b:
			p.b[id_] = self.d.buchete.get(id_)

	def _tine_s(self, k5):
		p = self._pas
		if p is not None and k5 not in p.s:
			p.s[k5] = self.d.lamedb.servicii.get(k5)

	def _tine_t(self, k):
		p = self._pas
		if p is not None and k not in p.t:
			p.t[k] = self.d.lamedb.transpondere.get(k)

	def _tine_p(self):
		p = self._pas
		if p is not None and p.p is None:
			p.p = (self.d.blacklist, self.d.whitelist)

	def _pune_b(self, b):
		self._tine_b(b.id)
		self.d.buchete[b.id] = b

	def _scoate_b(self, id_):
		self._tine_b(id_)
		self.d.buchete.pop(id_, None)

	def _pune_s(self, s):
		self._tine_s(s.k5)
		self.d.lamedb.pune(s)

	def _scoate_s(self, k5):
		self._tine_s(k5)
		self.d.lamedb.scoate(k5)

	def _a_schimbat(self, pas):
		for k, v in pas.b.items():
			if self.d.buchete.get(k) is not v:
				return True
		for k, v in pas.s.items():
			if self.d.lamedb.servicii.get(k) is not v:
				return True
		for k, v in pas.t.items():
			if self.d.lamedb.transpondere.get(k) is not v:
				return True
		return pas.p is not None and pas.p != (self.d.blacklist, self.d.whitelist)

	def _restabileste(self, pas):
		"""Pune inapoi ce a tinut pasul; intoarce pasul invers (pentru refacere)."""
		inv = _Pas(pas.nume)
		for k, v in pas.b.items():
			inv.b[k] = self.d.buchete.get(k)
			if v is None:
				self.d.buchete.pop(k, None)
			else:
				self.d.buchete[k] = v
		for k, v in pas.s.items():
			inv.s[k] = self.d.lamedb.servicii.get(k)
			if v is None:
				self.d.lamedb.scoate(k)
			else:
				self.d.lamedb.pune(v)
		for k, v in pas.t.items():
			inv.t[k] = self.d.lamedb.transpondere.get(k)
			if v is None:
				self.d.lamedb.transpondere.pop(k, None)
			else:
				self.d.lamedb.transpondere[k] = v
		if pas.p is not None:
			inv.p = (self.d.blacklist, self.d.whitelist)
			self.d.blacklist, self.d.whitelist = pas.p
			self._parental_schimbat()
		if pas.t:
			self.d.lamedb.schimbat()
		return inv

	def anuleaza(self):
		self._verifica()
		if not self._anulare:
			return None
		pas = self._anulare.pop()
		self._refacere.append(self._restabileste(pas))
		self._schimbat()
		return pas.nume

	def reface(self):
		self._verifica()
		if not self._refacere:
			return None
		pas = self._refacere.pop()
		self._anulare.append(self._restabileste(pas))
		self._schimbat()
		return pas.nume

	# ------------------------------------------------ citirea: buchetele

	def radacina(self, radio=False):
		return "bouquets.radio" if radio else "bouquets.tv"

	def _b(self, buchet_id):
		b = self.d.buchete.get(buchet_id)
		if b is None:
			raise Eroare(_t("Buchetul nu mai există."))
		return b

	def _parinti(self):
		"""{id buchet: id-ul listei in care sta (prima gasita)}."""
		c = self._cache.get("parinti")
		if c is None:
			c = {}
			for b in self.d.buchete.values():
				for i in b.intrari:
					f = i.fisier
					if f and f not in c and i.fel in ("subbuchet", "alternative"):
						c[f] = b.id
			self._cache["parinti"] = c
		return c

	def _info_buchet(self, b, parinte=None):
		x = BuchetInfo()
		x.id = b.id
		x.nume_intreg = b.nume
		x.nume = D.fara_mod(b.nume) or b.id
		x.n = sum(1 for i in b.intrari if i.fel in ("canal", "flux", "alternative", "altul"))
		x.radio = b.radio
		x.favorite = b.id in FAVORITE
		x.parinte = parinte if parinte is not None else self._parinti().get(b.id)
		x.ascuns = False
		x.blocat = self._blocat_fisier(b.id)
		aratat = nume_favorite_aratat(b.id, b.nume)
		if aratat:
			x.nume = aratat
		return x

	def buchete(self, radio=False):
		rad = self.d.buchete.get(self.radacina(radio))
		rez = []
		if rad is None:
			return rez
		for i in rad.intrari:
			if i.fel != "subbuchet":
				continue
			b = self.d.buchete.get(i.fisier)
			if b is not None:
				x = self._info_buchet(b, rad.id)
				x.ascuns = bool(i.r.steaguri & D.INVIZIBIL)
				rez.append(x)
		return rez

	def buchet(self, buchet_id):
		b = self.d.buchete.get(buchet_id)
		return self._info_buchet(b) if b is not None else None

	def toate_buchetele(self, radio=None):
		"""Toate buchetele legate (si sub-buchetele), pentru „Mută în...” / „Copiază în...": [(BuchetInfo, adancime)]."""
		rez = []
		vazute = set()

		def coboara(id_, adancime):
			b = self.d.buchete.get(id_)
			if b is None:
				return
			for i in b.intrari:
				f = i.fisier
				if i.fel == "subbuchet" and f in self.d.buchete and f not in vazute:
					vazute.add(f)
					rez.append((self._info_buchet(self.d.buchete[f], id_), adancime))
					coboara(f, adancime + 1)

		for r in ((False,) if radio is False else (True,) if radio is True else (False, True)):
			coboara(self.radacina(r), 0)
		return rez

	def nelegate(self, radio=None):
		legate = set(self._parinti())
		legate.update(("bouquets.tv", "bouquets.radio"))
		rez = []
		for b in self.d.buchete.values():
			if b.id in legate:
				continue
			if radio is not None and b.radio != radio:
				continue
			rez.append(self._info_buchet(b, ""))
		return rez

	def _numere(self):
		"""{id intrare: numarul de pe telecomanda} (ca zapToNumber: buchet dupa buchet, fara marcaje si dosare)."""
		c = self._cache.get("numere")
		if c is None:
			c = {}
			for radio in (False, True):
				n = 0
				rad = self.d.buchete.get(self.radacina(radio))
				if rad is None:
					continue
				for i in rad.intrari:
					if i.fel != "subbuchet":
						continue
					b = self.d.buchete.get(i.fisier)
					if b is None:
						continue
					for j in b.intrari:
						if j.fel in ("canal", "flux", "alternative", "altul"):
							n += 1
							c[j.id] = n
			self._cache["numere"] = c
		return c

	def intrari(self, buchet_id):
		b = self._b(buchet_id)
		numere = self._numere()
		rez = []
		for i in b.intrari:
			rez.append(self._info_intrare(i, numere))
		return rez

	def _info_intrare(self, i, numere=None):
		x = IntrareInfo()
		x.id = i.id
		x.ref = i.ref
		x.descriere = i.descriere
		r = i.r
		x.fel = fel = r.fel()
		x.numerotat = bool(r.steaguri & D.NUMEROTAT) and fel == "marcaj"
		x.cheie = r.cheie()
		x.buchet_id = r.fisier() if fel in ("subbuchet", "alternative") else None
		x.serviciu = None
		x.mort = False
		x.ascuns = False
		x.blocat = False
		nume = i.descriere or r.nume
		if fel == "canal":
			sv = self.d.lamedb.dupa_cheie(x.cheie)
			if sv:
				x.serviciu = self._canal(sv[0])
				x.ascuns = x.serviciu.ascuns
				x.blocat = x.serviciu.blocat
				if not nume:
					nume = sv[0].nume
			else:
				x.mort = True
		elif fel in ("subbuchet", "alternative"):
			sub = self.d.buchete.get(x.buchet_id)
			if not nume and sub is not None:
				nume = nume_favorite_aratat(sub.id, sub.nume) or D.fara_mod(sub.nume)
			x.blocat = self._blocat_fisier(x.buchet_id)
			x.ascuns = bool(r.steaguri & D.INVIZIBIL)
		x.nume = nume or ""
		x.numar = (numere if numere is not None else self._numere()).get(i.id)
		return x

	def indici(self, buchet_id, ids):
		"""Id-urile intrarilor (web) -> indicii lor in buchet; cele care nu mai sunt acolo se sar."""
		b = self._b(buchet_id)
		poz = dict((i.id, k) for k, i in enumerate(b.intrari))
		return [poz[x] for x in ids if x in poz]

	def grupa_marcaj(self, buchet_id, indice):
		"""Indicii randurilor de sub marcajul `indice`, pana la marcajul urmator (bifarea grupei)."""
		b = self._b(buchet_id)
		rez = []
		for k in range(indice + 1, len(b.intrari)):
			if b.intrari[k].fel in ("marcaj",):
				break
			rez.append(k)
		return rez

	# ------------------------------------------------ citirea: serviciile

	def _tp(self, s):
		return self.d.lamedb.transpondere.get(s.tp_cheie)

	def _info_tp(self, tp):
		x = self._ctp.get(tp.cheie)
		if x is not None and x[0] is tp:
			return x[1]
		poz = tp.poz
		info = (poz, self._text_poz(poz), tp.frecv, tp.pol, tp.sr, tp.text())
		self._ctp[tp.cheie] = (tp, info)
		return info

	def _canal(self, s):
		tp = self.d.lamedb.transpondere.get(s.tp_cheie)
		x = self._cc.get(s.k5)
		if x is not None and x[0] is s and x[1] is tp and x[2] == self._v_par:
			return x[3]
		v = CanalInfo()
		v.k5 = s.k5
		v.ref = s.ref
		v.cheie = s.cheie
		v.nume = s.nume
		v.ordine = D.cheie_sortare(s.nume)
		v.furnizor = s.furnizor
		if tp is not None:
			v.poz, v.poz_text, v.frecv, v.pol, v.sr, v.tp_text = self._info_tp(tp)
		else:
			v.poz = D.poz_din_ns(s.ns)
			v.poz_text = self._text_poz(v.poz)
			v.frecv, v.pol, v.sr, v.tp_text = None, "", None, ""
		v.tp_cheie = s.tp_cheie
		v.sid = s.sid
		v.stype = s.tip
		v.tip = s.fel_tip
		v.hd = s.hd
		v.acces = "criptat" if s.caids else "fta"
		v.steaguri = s.steaguri
		v.ascuns = s.ascuns
		v.blocat = self._blocat_cheie(s.cheie)
		v.are_video = s.are_video
		v.are_sunet = s.are_sunet
		self._cc[s.k5] = (s, tp, self._v_par, v)
		return v

	def _text_poz(self, poz):
		return D.text_pozitie(poz)

	def nume_satelit(self, poz):
		return self.d.sateliti.get(poz, "") if isinstance(poz, int) else ""

	def serviciu(self, ref):
		k = D.cheie_din_ref(ref)
		if k is None:
			return None
		sv = self.d.lamedb.dupa_cheie(k)
		return self._canal(sv[0]) if sv else None

	def _toate_canalele(self):
		cheie = (id(self.d.lamedb), self.d.lamedb.versiune_date, self._v_par)
		if self._toate is None or self._toate[0] != cheie:
			c = [self._canal(s) for s in self.d.lamedb.servicii.values()]
			c.sort(key=lambda v: v.ordine)
			self._toate = (cheie, c)
		return self._toate[1]

	def toate(self, radio=False):
		if radio is None:
			return list(self._toate_canalele())
		return [v for v in self._toate_canalele() if (v.tip == "radio") == bool(radio)]

	def sateliti(self, radio=False):
		n = {}
		for v in self.toate(radio):
			n[v.poz] = n.get(v.poz, 0) + 1
		return [(p, self._text_poz(p), n[p]) for p in sorted(n, key=D.ordine_pozitie)]

	def din_satelit(self, poz, radio=False):
		return [v for v in self.toate(radio) if v.poz == poz]

	def furnizori(self, radio=False):
		n = {}
		for v in self.toate(radio):
			n[v.furnizor] = n.get(v.furnizor, 0) + 1
		return sorted(n.items(), key=lambda x: D.cheie_sortare(x[0]))

	def din_furnizor(self, nume, radio=False):
		return [v for v in self.toate(radio) if v.furnizor == nume]

	def transpondere(self, poz=None, radio=None):
		"""[TransponderInfo] (toate sau ale unei pozitii), cu numarul serviciilor (TV, radio sau toate)."""
		n = {}
		for v in self.toate(radio):
			n[v.tp_cheie] = n.get(v.tp_cheie, 0) + 1
		rez = []
		for t in self.d.lamedb.transpondere.values():
			p, ptext, frecv, pol, sr, text = self._info_tp(t)
			if poz is not None and p != poz:
				continue
			x = TransponderInfo()
			x.cheie = x.tp_cheie = t.cheie
			x.poz, x.poz_text, x.frecv, x.pol, x.sr, x.text = p, ptext, frecv, pol, sr, text
			x.tp_text = text
			x.n = n.get(t.cheie, 0)
			x.fel = t.fel
			rez.append(x)
		rez.sort(key=lambda x: (D.ordine_pozitie(x.poz), x.frecv or 0, x.pol))
		return rez

	def din_transponder(self, tp_cheie):
		return [v for v in self._toate_canalele() if v.tp_cheie == tuple(tp_cheie)]

	def cauta(self, text, radio=None, chei=None):
		return U.cauta(self.toate(radio), text, chei)

	def in_buchete(self, ref):
		"""[id buchet] in care e canalul (dupa cheie)."""
		k = D.cheie_din_ref(ref)
		harta = self._harta_buchete()
		return list(harta.get(k, ())) if k else [b.id for b in self.d.buchete.values()
			if any(i.ref == ref for i in b.intrari)]

	def _harta_buchete(self):
		"""{cheie canal: [id buchet]} (fara radacini si fara buchetele nelegate, care nu se vad pe televizor: un canal
		numai intr-un buchet nelegat e „în niciun buchet”)."""
		c = self._cache.get("in_buchete")
		if c is None:
			c = {}
			legate = self._parinti()
			for b in self.d.buchete.values():
				if b.id in ("bouquets.tv", "bouquets.radio") or b.id not in legate:
					continue
				for i in b.intrari:
					k = i.cheie
					if k:
						l = c.setdefault(k, [])
						if not l or l[-1] != b.id:
							l.append(b.id)
			self._cache["in_buchete"] = c
		return c

	# ------------------------------------------------ controlul parental

	def _alb(self):
		"""Controlul parental pe lista alba (citit o data pe sesiune: setarea se schimba numai din meniul ei)."""
		if self._mod_par is None:
			try:
				self._mod_par = _nucleu().mod_parental() or "blacklist"
			except Exception:
				self._mod_par = "blacklist"
		return self._mod_par == "whitelist"

	def _lista_parentala(self):
		return self.d.whitelist if self._alb() else self.d.blacklist

	def _parental(self):
		c = self._cache.get("parental")
		if c is None:
			chei, fisiere = set(), set()
			for r in self._lista_parentala():
				f = D.Referinta(r).fisier()
				if f:
					fisiere.add(f)
				else:
					k = D.cheie_din_ref(r)
					if k:
						chei.add(k)
			c = (chei, fisiere)
			self._cache["parental"] = c
		return c

	def _blocat_cheie(self, cheie):
		inauntru = cheie in self._parental()[0]
		return (not inauntru) if self._alb() and self._lista_parentala() else inauntru

	def _blocat_fisier(self, fisier):
		inauntru = fisier in self._parental()[1]
		return (not inauntru) if self._alb() and self._lista_parentala() else inauntru

	def _schimba_parental(self, randuri_noi, sterse):
		"""Randurile adaugate / scoase din lista activa."""
		self._tine_p()
		alb = self._alb()
		lista = list(self.d.whitelist if alb else self.d.blacklist)
		lista = [r for r in lista if r not in sterse]
		for r in randuri_noi:
			if r not in lista:
				lista.append(r)
		if alb:
			self.d.whitelist = tuple(lista)
		else:
			self.d.blacklist = tuple(lista)
		self._parental_schimbat()

	# ------------------------------------------------ operatiile pe buchete

	def _intrare_noua(self, ref, descriere=None):
		return D.Intrare(self.d.id_nou(), ref, descriere)

	def _nume_rand(self, intrare):
		return self._info_intrare(intrare).nume or _t("fără nume")

	def adauga(self, buchet_id, refs, la=None):
		"""Canalele (referinte) puse in buchet inaintea randului `la` (None = la sfarsit); cele deja in buchet se sar."""
		b = self._b(buchet_id)
		existente = set(i.cheie or i.ref for i in b.intrari)
		noi = []
		for ref in refs:
			r = D.Referinta(ref)
			if not r.valida:
				continue
			k = r.cheie() or ref
			if k in existente:
				continue
			existente.add(k)
			s = self.serviciu(ref) if r.cheie() else None
			noi.append(self._intrare_noua(s.ref if s is not None else ref))
		if not noi:
			return 0
		nume = (_t("Adăugat: %s") % self._nume_rand(noi[0])) if len(noi) == 1 else \
			ngettext("Un canal adăugat", "%d canale adăugate", len(noi)) % len(noi)
		with self._in_pas(nume):
			l = list(b.intrari)
			poz = len(l) if la is None else max(0, min(la, len(l)))
			l[poz:poz] = noi
			self._pune_b(b.cu(intrari=l))
		return len(noi)

	def _bloc(self, b, indici):
		ind = sorted(set(k for k in indici if 0 <= k < len(b.intrari)))
		if not ind:
			raise Eroare(_t("Nu e ales niciun rând."))
		return ind

	def muta(self, buchet_id, indici, la):
		b = self._b(buchet_id)
		ind = self._bloc(b, indici)
		bloc = [b.intrari[k] for k in ind]
		rest = [x for k, x in enumerate(b.intrari) if k not in set(ind)]
		la = max(0, min(la, len(rest)))
		nou = rest[:la] + bloc + rest[la:]
		if [x.id for x in nou] == [x.id for x in b.intrari]:
			return None
		nume = (_t("Mutat: %s") % self._nume_rand(bloc[0])) if len(bloc) == 1 else \
			ngettext("Un rând mutat", "%d rânduri mutate", len(bloc)) % len(bloc)
		with self._in_pas(nume):
			self._pune_b(b.cu(intrari=nou))
		return nume

	def muta_sus(self, buchet_id, indici):
		ind = self._bloc(self._b(buchet_id), indici)
		return self.muta(buchet_id, ind, max(0, ind[0] - 1))

	def muta_jos(self, buchet_id, indici):
		ind = self._bloc(self._b(buchet_id), indici)
		return self.muta(buchet_id, ind, ind[0] + 1)

	def _verifica_tinta(self, din_id, bloc, in_id):
		"""Un buchet nu intra in el insusi sau intr-un sub-buchet al lui."""
		pentru = set(i.fisier for i in bloc if i.fel == "subbuchet")
		if not pentru:
			return
		cur = in_id
		vazute = set()
		while cur and cur not in vazute:
			if cur in pentru:
				raise Eroare(_t("Un buchet nu poate fi pus în el însuși."))
			vazute.add(cur)
			cur = self._parinti().get(cur)

	def muta_in(self, din_id, indici, in_id, la=None):
		if din_id == in_id:
			return self.muta(din_id, indici, len(self._b(din_id).intrari) if la is None else la)
		b = self._b(din_id)
		tinta = self._b(in_id)
		ind = self._bloc(b, indici)
		bloc = [b.intrari[k] for k in ind]
		self._verifica_tinta(din_id, bloc, in_id)
		if b.radio != tinta.radio and any(i.fel == "subbuchet" for i in bloc):
			raise Eroare(_t("Un buchet TV nu se poate pune printre cele de radio."))
		existente = set(i.cheie or i.ref for i in tinta.intrari)
		puse = [x for x in bloc if (x.cheie or x.ref) not in existente]
		numeb = self._info_buchet(tinta).nume
		if len(bloc) == 1:
			nume = _t("Mutat în %(buchet)s: %(canal)s") % {"buchet": numeb, "canal": self._nume_rand(bloc[0])}
		else:
			nume = ngettext("Un rând mutat", "%d rânduri mutate", len(bloc)) % len(bloc) + " " + _t("în %s") % numeb
		with self._in_pas(nume):
			ids = set(x.id for x in bloc)
			self._pune_b(b.cu(intrari=[x for x in b.intrari if x.id not in ids]))
			l = list(tinta.intrari)
			poz = len(l) if la is None else max(0, min(la, len(l)))
			l[poz:poz] = puse
			self._pune_b(tinta.cu(intrari=l))
		return nume

	def copiaza(self, din_id, indici, in_id, la=None):
		b = self._b(din_id)
		tinta = self._b(in_id)
		ind = self._bloc(b, indici)
		bloc = [b.intrari[k] for k in ind]
		self._verifica_tinta(din_id, bloc, in_id)
		existente = set(i.cheie or i.ref for i in tinta.intrari) if din_id != in_id else set()
		puse = []
		for x in bloc:
			k = x.cheie or x.ref
			if k in existente and x.fel not in ("marcaj", "spatiu"):
				continue
			existente.add(k)
			puse.append(self._intrare_noua(x.ref, x.descriere))
		if not puse:
			return None
		nume = ngettext("Un rând copiat", "%d rânduri copiate", len(puse)) % len(puse) + " " + _t("în %s") % \
			self._info_buchet(tinta).nume
		with self._in_pas(nume):
			l = list(tinta.intrari)
			poz = len(l) if la is None else max(0, min(la, len(l)))
			l[poz:poz] = puse
			self._pune_b(tinta.cu(intrari=l))
		return nume

	def scoate(self, buchet_id, indici):
		"""„Șterge” din buchet: canalele raman in receptor. Un sub-buchet scos din lista lui ramane nelegat."""
		b = self._b(buchet_id)
		ind = set(self._bloc(b, indici))
		primul = b.intrari[min(ind)]
		nume = (_t("Șters din buchet: %s") % self._nume_rand(primul)) if len(ind) == 1 else \
			ngettext("Un rând șters din buchet", "%d rânduri șterse din buchet", len(ind)) % len(ind)
		with self._in_pas(nume):
			self._pune_b(b.cu(intrari=[x for k, x in enumerate(b.intrari) if k not in ind]))
		return nume

	def scoate_din_toate(self, refs):
		"""Canalele scoase din toate buchetele (raman in receptor)."""
		chei = set(D.cheie_din_ref(r) or r for r in refs)
		n = 0
		with self._in_pas(_t("Scos din toate buchetele")) as pas:
			for b in list(self.d.buchete.values()):
				l = [x for x in b.intrari if (x.cheie or x.ref) not in chei]
				if len(l) != len(b.intrari):
					n += len(b.intrari) - len(l)
					self._pune_b(b.cu(intrari=l))
			if n == 0:
				pas.nume = None
		return n

	def redenumeste(self, buchet_id, indice, nume):
		"""Numele unui rand din buchet: canal (#DESCRIPTION), marcaj (numele din referinta), sub-buchet (#NAME lui)."""
		b = self._b(buchet_id)
		if not 0 <= indice < len(b.intrari):
			raise Eroare(_t("Nu e ales niciun rând."))
		nume = D.curat_nume(nume)
		x = b.intrari[indice]
		fel = x.fel
		if fel == "subbuchet":
			return self.redenumeste_buchet(x.fisier, nume)
		if not nume and fel != "spatiu":
			raise Eroare(_t("Numele nu poate fi gol."))
		vechi = self._nume_rand(x)
		with self._in_pas(_t("Redenumit: %s") % vechi):
			if fel == "marcaj":
				parti = x.ref.split(":", 11)
				ref = ":".join(parti[:10] + [parti[10] if len(parti) > 10 else "", D.codeaza(nume)])
				nou = x.cu(ref=ref, descriere=nume)
			elif fel == "canal":
				s = self.serviciu(x.ref)
				nou = x.cu(descriere=None if s is not None and s.nume == nume else nume)
			else:
				nou = x.cu(descriere=nume)
			l = list(b.intrari)
			l[indice] = nou
			self._pune_b(b.cu(intrari=l))
		return nume

	def redenumeste_serviciu(self, ref, nume):
		"""Numele din lamedb, cu steagul HoldName (scanarea nu-l mai schimba)."""
		k = D.cheie_din_ref(ref)
		sv = self.d.lamedb.dupa_cheie(k) if k else []
		if not sv:
			raise Eroare(_t("Canalul nu mai există în lista receptorului."))
		nume = D.curat_nume(nume)
		if not nume:
			raise Eroare(_t("Numele nu poate fi gol."))
		with self._in_pas(_t("Redenumit: %s") % (sv[0].nume or _t("fără nume"))):
			for s in sv:
				if s.nume != nume:
					self._pune_s(s.cu(nume=nume, steaguri=s.steaguri | D.DX_PASTREAZA_NUMELE))
		return nume

	def redenumeste_buchet(self, buchet_id, nume):
		b = self._b(buchet_id)
		nume = D.curat_nume(nume, 100)
		if not nume:
			raise Eroare(_t("Numele nu poate fi gol."))
		vechi = D.fara_mod(b.nume)
		if nume == nume_favorite_aratat(buchet_id, b.nume):
			return None
		are_mod = b.nume != vechi or buchet_id.startswith("userbouquet.")
		nou = D.cu_mod(nume, b.radio) if are_mod else nume
		if nou == b.nume:
			return None
		with self._in_pas(_t("Buchet redenumit: %s") % (vechi or buchet_id)):
			self._pune_b(b.cu(nume=nou))
			# randurile care il arata cu #DESCRIPTION in parinte (rar): numele nou
			for p in list(self.d.buchete.values()):
				if any(i.fisier == buchet_id and i.descriere for i in p.intrari):
					self._pune_b(p.cu(intrari=[i.cu(descriere=nume) if i.fisier == buchet_id and i.descriere else i
						for i in p.intrari]))
		return nume

	def _numar_marcaj(self, b):
		folosite = set()
		for i in b.intrari:
			if i.fel in ("marcaj", "spatiu"):
				folosite.add(i.r.date[0])
		n = 0
		while n in folosite:
			n += 1
		return n

	def marcaj_nou(self, buchet_id, la, nume, numerotat=False):
		b = self._b(buchet_id)
		nume = D.curat_nume(nume)
		if not nume:
			raise Eroare(_t("Numele nu poate fi gol."))
		x = self._intrare_noua(D.ref_marcaj(nume, self._numar_marcaj(b), numerotat), nume)
		l = list(b.intrari)
		poz = len(l) if la is None else max(0, min(la, len(l)))
		with self._in_pas(_t("Marcaj nou: %s") % nume):
			l.insert(poz, x)
			self._pune_b(b.cu(intrari=l))
		return poz

	def spatiu_nou(self, buchet_id, la):
		b = self._b(buchet_id)
		x = self._intrare_noua(D.ref_spatiu(self._numar_marcaj(b)))
		l = list(b.intrari)
		poz = len(l) if la is None else max(0, min(la, len(l)))
		with self._in_pas(_t("Rând gol nou")):
			l.insert(poz, x)
			self._pune_b(b.cu(intrari=l))
		return poz

	def flux_nou(self, buchet_id, la, adresa, nume, tip=4097):
		"""Un flux (adresa de internet) in buchet."""
		b = self._b(buchet_id)
		adresa = (adresa or "").strip()
		nume = D.curat_nume(nume) or adresa
		if "://" not in adresa or any(c in adresa for c in "\r\n"):
			raise Eroare(_t("Adresa fluxului nu e bună (trebuie să înceapă cu http:// sau https://)."))
		ref = "%d:0:1:0:0:0:0:0:0:0:%s:%s" % (tip, D.codeaza(adresa), D.codeaza(nume))
		if len(("#SERVICE " + ref).encode("utf-8")) > D.LUNGIME_MAXIMA:
			raise Eroare(_t("Adresa fluxului e prea lungă pentru lista de canale."))
		x = self._intrare_noua(ref, nume)
		l = list(b.intrari)
		poz = len(l) if la is None else max(0, min(la, len(l)))
		with self._in_pas(_t("Flux nou: %s") % nume):
			l.insert(poz, x)
			self._pune_b(b.cu(intrari=l))
		return poz

	def buchet_nou(self, nume, radio=False, parinte=None, la=None, refs=None):
		intrari = []
		vazute = set()
		for ref in refs or ():
			r = D.Referinta(ref)
			if not r.valida:
				continue
			k = r.cheie() or ref
			if k in vazute:
				continue
			vazute.add(k)
			intrari.append(self._intrare_noua(ref))
		return self._buchet_nou(nume, radio, parinte, la, intrari, None)

	def _buchet_nou(self, nume, radio, parinte, la, intrari, nume_pas):
		nume = D.curat_nume(nume, 100)
		if not nume:
			raise Eroare(_t("Numele nu poate fi gol."))
		parinte = parinte or self.radacina(radio)
		p = self._b(parinte)
		sub = parinte not in ("bouquets.tv", "bouquets.radio")
		radio = p.radio if sub else radio
		if nume_pas is None:
			nume_pas = (_t("Sub-buchet nou: %s") if sub else _t("Buchet nou: %s")) % nume
		with self._in_pas(nume_pas):
			id_ = self._pune_buchet_nou(nume, radio, parinte, la, intrari)
		return id_

	def _pune_buchet_nou(self, nume, radio, parinte, la, intrari):
		"""Buchetul nou si randul lui in lista parintelui, in pasul deschis de cel care cheama."""
		p = self._b(parinte)
		sub = parinte not in ("bouquets.tv", "bouquets.radio")
		radio = p.radio if sub else radio
		id_ = D.id_buchet_nou(nume, radio, set(self.d.buchete) | set(self._baza[1]))
		self._pune_b(D.Buchet(id_, D.cu_mod(nume, radio), intrari))
		l = list(p.intrari)
		poz = len(l) if la is None else max(0, min(la, len(l)))
		l.insert(poz, self._intrare_noua(D.ref_buchet(id_)))
		self._pune_b(p.cu(intrari=l))
		return id_

	def copiaza_buchet(self, buchet_id, nume=None):
		"""O copie a buchetului (cu marcajele si numele din el), pusa dupa el in aceeasi lista."""
		b = self._b(buchet_id)
		nume = nume or (_t("%s (copie)") % D.fara_mod(b.nume))
		parinte = self._parinti().get(buchet_id) or self.radacina(b.radio)
		p = self._b(parinte)
		poz = [k for k, i in enumerate(p.intrari) if i.fisier == buchet_id]
		intrari = [self._intrare_noua(i.ref, i.descriere) for i in b.intrari if i.fel != "subbuchet"]
		return self._buchet_nou(nume, b.radio, parinte, poz[0] + 1 if poz else None, intrari,
			_t("Buchet copiat: %s") % D.fara_mod(b.nume))

	def sterge_buchet(self, buchet_id):
		if buchet_id in ("bouquets.tv", "bouquets.radio"):
			raise Eroare(_t("Lista buchetelor nu se poate șterge."))
		if buchet_id in ("userbouquet.favourites.tv", "userbouquet.favourites.radio"):
			raise Eroare(_t("Favorite nu se pot șterge. Poți scoate canalele din ele."))
		b = self._b(buchet_id)
		de_sters = set()

		def strange(id_):
			if id_ in de_sters:
				return
			de_sters.add(id_)
			x = self.d.buchete.get(id_)
			if x is None:
				return
			for i in x.intrari:
				if i.fel in ("subbuchet", "alternative") and i.fisier in self.d.buchete:
					# un sub-buchet legat si din alt loc ramane
					altii = [p for p in self.d.buchete.values() if p.id != id_ and p.id not in de_sters
						and any(j.fisier == i.fisier for j in p.intrari)]
					if not altii:
						strange(i.fisier)

		strange(buchet_id)
		with self._in_pas(_t("Buchet șters: %s") % D.fara_mod(b.nume)):
			for p in list(self.d.buchete.values()):
				if p.id in de_sters:
					continue
				l = [i for i in p.intrari if i.fisier not in de_sters]
				if len(l) != len(p.intrari):
					self._pune_b(p.cu(intrari=l))
			for id_ in de_sters:
				self._scoate_b(id_)
		return len(de_sters)

	def leaga_buchet(self, buchet_id, parinte=None, la=None):
		b = self._b(buchet_id)
		parinte = parinte or self.radacina(b.radio)
		p = self._b(parinte)
		if any(i.fisier == buchet_id for i in p.intrari):
			return None
		self._verifica_tinta(None, [D.Intrare(0, D.ref_buchet(buchet_id))], parinte)
		with self._in_pas(_t("Buchet pus în listă: %s") % D.fara_mod(b.nume)):
			l = list(p.intrari)
			poz = len(l) if la is None else max(0, min(la, len(l)))
			l.insert(poz, self._intrare_noua(D.ref_buchet(buchet_id)))
			self._pune_b(p.cu(intrari=l))
		return buchet_id

	def sterge_nelegat(self, buchet_id):
		if buchet_id in self._parinti() or buchet_id in ("bouquets.tv", "bouquets.radio"):
			raise Eroare(_t("Buchetul e în listă; șterge-l din listă."))
		b = self._b(buchet_id)
		with self._in_pas(_t("Buchet șters: %s") % D.fara_mod(b.nume)):
			self._scoate_b(buchet_id)
		return buchet_id

	def ascunde_buchet(self, buchet_id, da=True):
		"""Buchetul ascuns in lista buchetelor (steagul 512 pe randul lui)."""
		parinte = self._parinti().get(buchet_id)
		if parinte is None:
			raise Eroare(_t("Buchetul nu mai există."))
		p = self._b(parinte)
		l = []
		schimbat = False
		for i in p.intrari:
			if i.fisier == buchet_id and i.fel == "subbuchet":
				parti = i.ref.split(":", 2)
				st = int(parti[1])
				st2 = (st | D.INVIZIBIL) if da else (st & ~D.INVIZIBIL)
				if st2 != st:
					i = i.cu(ref="%s:%d:%s" % (parti[0], st2, parti[2]))
					schimbat = True
			l.append(i)
		if not schimbat:
			return None
		nume = (_t("Buchet ascuns: %s") if da else _t("Buchet arătat: %s")) % self._info_buchet(self._b(buchet_id)).nume
		with self._in_pas(nume):
			self._pune_b(p.cu(intrari=l))
		return nume

	def sorteaza(self, buchet_id, dupa="nume", indici=None, invers=False):
		b = self._b(buchet_id)
		nou = U.sorteaza(b.intrari, self._cheie_sortare(dupa), indici, invers)
		if [x.id for x in nou] == [x.id for x in b.intrari]:
			return None
		with self._in_pas(_t("Sortat: %s") % self._info_buchet(b).nume):
			self._pune_b(b.cu(intrari=nou))
		return True

	def _cheie_sortare(self, dupa):
		def cheie(intrare):
			x = self._info_intrare(intrare)
			s = x.serviciu
			if dupa == "pozitie":
				return (D.ordine_pozitie(s.poz) if s else (9, 0), s.frecv or 0 if s else 0, D.cheie_sortare(x.nume))
			if dupa == "furnizor":
				return (D.cheie_sortare(s.furnizor if s else ""), D.cheie_sortare(x.nume))
			if dupa == "frecventa":
				return (s.frecv or 0 if s else 0, s.pol if s else "", D.cheie_sortare(x.nume))
			if dupa == "sid":
				return (s.sid if s else 0, D.cheie_sortare(x.nume))
			if dupa == "pozitie_nume":
				return (D.ordine_pozitie(s.poz) if s else (9, 0), D.cheie_sortare(x.nume))
			if dupa == "furnizor_nume":
				return (D.cheie_sortare(s.furnizor if s else ""), D.cheie_sortare(x.nume))
			return D.cheie_sortare(x.nume)
		return cheie

	# ------------------------------------------------ operatiile pe servicii

	def _servicii_din(self, refs):
		rez = []
		vazute = set()
		for ref in refs:
			k = D.cheie_din_ref(ref)
			if not k or k in vazute:
				continue
			vazute.add(k)
			rez.extend(self.d.lamedb.dupa_cheie(k))
		return rez

	def ascunde(self, refs, da=True):
		sv = [s for s in self._servicii_din(refs) if s.ascuns != bool(da)]
		if not sv:
			return 0
		if len(sv) == 1:
			nume = (_t("Ascuns: %s") if da else _t("Arătat: %s")) % (sv[0].nume or _t("fără nume"))
		else:
			nume = (ngettext("Un canal ascuns", "%d canale ascunse", len(sv)) % len(sv) if da else
				ngettext("Un canal arătat", "%d canale arătate", len(sv)) % len(sv))
		with self._in_pas(nume):
			for s in sv:
				self._pune_s(s.cu(steaguri=(s.steaguri | D.DX_ASCUNS) if da else (s.steaguri & ~D.DX_ASCUNS)))
		return len(sv)

	def blocheaza(self, refs, da=True):
		alb = self._alb()
		chei = set()
		randuri = []
		for ref in refs:
			k = D.cheie_din_ref(ref)
			if not k or k in chei:
				continue
			chei.add(k)
			sv = self.d.lamedb.dupa_cheie(k)
			randuri.append(sv[0].ref if sv else ref)
		if not randuri:
			return 0
		lista = self._lista_parentala()
		de_scos = set(r for r in lista if D.cheie_din_ref(r) in chei)
		pune = bool(da) != alb
		if pune and len(de_scos) >= len(chei):
			return 0
		if not pune and not de_scos:
			return 0
		nume = (ngettext("Un canal blocat", "%d canale blocate", len(randuri)) % len(randuri) if da else
			ngettext("Un canal deblocat", "%d canale deblocate", len(randuri)) % len(randuri))
		with self._in_pas(nume):
			if pune:
				self._schimba_parental(randuri, set())
			else:
				self._schimba_parental((), de_scos)
		return len(randuri)

	def blocheaza_buchet(self, buchet_id, da=True):
		b = self._b(buchet_id)
		alb = self._alb()
		ref = D.ref_buchet(buchet_id)
		lista = self._lista_parentala()
		existente = set(r for r in lista if D.Referinta(r).fisier() == buchet_id)
		pune = bool(da) != alb
		if (pune and existente) or (not pune and not existente):
			return None
		nume = (_t("Buchet blocat: %s") if da else _t("Buchet deblocat: %s")) % D.fara_mod(b.nume)
		with self._in_pas(nume):
			if pune:
				self._schimba_parental([ref], set())
			else:
				self._schimba_parental((), existente)
		return nume

	def sterge_servicii(self, refs):
		"""Din lamedb (toate serviciile cu aceeasi cheie), din toate buchetele si din listele parentale."""
		sv = self._servicii_din(refs)
		chei = set(s.cheie for s in sv) | set(k for k in (D.cheie_din_ref(r) for r in refs) if k)
		if not chei:
			return 0
		n = len(set(s.cheie for s in sv)) or len(chei)
		nume = (_t("Șters din receptor: %s") % (sv[0].nume or _t("fără nume"))) if n == 1 and sv else \
			ngettext("Un canal șters din receptor", "%d canale șterse din receptor", n) % n
		with self._in_pas(nume):
			for s in sv:
				self._scoate_s(s.k5)
			for b in list(self.d.buchete.values()):
				l = [x for x in b.intrari if x.cheie not in chei]
				if len(l) != len(b.intrari):
					self._pune_b(b.cu(intrari=l))
			for alb in (False, True):
				lista = self.d.whitelist if alb else self.d.blacklist
				l = tuple(r for r in lista if D.cheie_din_ref(r) not in chei)
				if l != lista:
					self._tine_p()
					if alb:
						self.d.whitelist = l
					else:
						self.d.blacklist = l
					self._parental_schimbat()
		return n

	def sterge_transponder(self, tp_cheie):
		"""Transponderul si serviciile lui (si randurile lor din buchete); numarul serviciilor sterse."""
		return self.sterge_transpondere([tp_cheie])

	def sterge_transpondere(self, chei_tp, nume=None):
		"""Mai multe transpondere cu serviciile lor, intr-un singur pas de anulare; numarul serviciilor sterse."""
		chei_tp = [tuple(k) for k in chei_tp]
		lipsa = [k for k in chei_tp if k not in self.d.lamedb.transpondere]
		if lipsa or not chei_tp:
			raise Eroare(_t("Transponderul nu mai există."))
		alese = set(chei_tp)
		refs = [s.ref for s in self.d.lamedb.servicii.values() if s.tp_cheie in alese]
		if nume:
			pass
		elif len(alese) == 1:
			tp = self.d.lamedb.transpondere[chei_tp[0]]
			nume = _t("Transponder șters: %s") % (tp.text() or tp.cheie_text())
		else:
			nume = ngettext("Un transponder șters", "%d transpondere șterse", len(alese)) % len(alese)
		with self._in_pas(nume):
			# serviciile, randurile lor din buchete si transponderele, in acelasi pas (se anuleaza impreuna)
			sv = self._servicii_din(refs)
			chei = set(s.cheie for s in sv)
			for s in sv:
				self._scoate_s(s.k5)
			if chei:
				for b in list(self.d.buchete.values()):
					l = [x for x in b.intrari if x.cheie not in chei]
					if len(l) != len(b.intrari):
						self._pune_b(b.cu(intrari=l))
			for k in alese:
				self._tine_t(k)
				self.d.lamedb.transpondere.pop(k, None)
			self.d.lamedb.schimbat()
		return len(refs)

	def buchet_din(self, fel, valoare, radio=False, nume=None):
		"""Buchet facut din toate canalele unui satelit (poz), furnizor (nume) sau transponder (cheie)."""
		if fel == "satelit":
			canale = self.din_satelit(valoare, radio)
			nume = nume or self.nume_satelit(valoare) or self._text_poz(valoare)
		elif fel == "furnizor":
			canale = self.din_furnizor(valoare, radio)
			nume = nume or valoare or _t("Fără furnizor")
		elif fel == "transponder":
			canale = [v for v in self.din_transponder(valoare) if (v.tip == "radio") == bool(radio)]
			tp = self.d.lamedb.transpondere.get(tuple(valoare))
			nume = nume or (tp.text() if tp is not None else _t("Transponder"))
		elif fel == "refs":
			canale = [self.serviciu(r) for r in valoare]
			canale = [c for c in canale if c is not None]
			nume = nume or _t("Buchet nou")
		else:
			raise Eroare(_t("Nu știu din ce să fac buchetul."))
		canale = [c for c in canale if not c.ascuns]
		if not canale:
			raise Eroare(_t("Nu e niciun canal de pus în buchet."))
		return self.buchet_nou(nume, radio, None, None, [c.ref for c in canale])

	# ------------------------------------------------ alternativele (acelasi canal din mai multe locuri)

	def alternative_noi(self, buchet_id, indici, nume=None):
		"""Canalele de pe randurile `indici` devin o grupa de alternative (fisierul alternatives.*, ca lista de pe
		televizor: #NAME fara „ (TV)”, randul 1:134 in buchet), pusa in locul primului; -> indicele randului nou."""
		b = self._b(buchet_id)
		ind = sorted(set(k for k in indici if 0 <= k < len(b.intrari) and b.intrari[k].fel == "canal"))
		if not ind:
			raise Eroare(_t("Alege cel puțin un canal."))
		alese = [b.intrari[k] for k in ind]
		nume = D.curat_nume(nume or self._nume_rand(alese[0]), 100) or _t("Alternative")
		id_ = D.id_buchet_nou(nume, b.radio, set(self.d.buchete) | set(self._baza[1]), prefix="alternatives")
		with self._in_pas(_t("Alternative noi: %s") % nume):
			self._pune_b(D.Buchet(id_, nume, [self._intrare_noua(i.ref, i.descriere) for i in alese]))
			l = [x for k, x in enumerate(b.intrari) if k not in ind]
			l.insert(ind[0], self._intrare_noua(D.ref_buchet(id_, alternative=True)))
			self._pune_b(b.cu(intrari=l))
		return ind[0]

	def _alternativa(self, buchet_id, indice):
		b = self._b(buchet_id)
		if not 0 <= indice < len(b.intrari) or b.intrari[indice].fel != "alternative":
			raise Eroare(_t("Rândul ales nu e o grupă de alternative."))
		return b, b.intrari[indice]

	def alternative_adauga(self, buchet_id, indice, refs):
		"""Canalele (referinte) puse la sfarsitul grupei de alternative de pe randul `indice`; cele deja in ea se
		sar. -> cate s-au pus."""
		b, x = self._alternativa(buchet_id, indice)
		a = self._b(x.fisier)
		existente = set(i.cheie or i.ref for i in a.intrari)
		noi = []
		for ref in refs:
			k = D.cheie_din_ref(ref) or ref
			if k in existente:
				continue
			existente.add(k)
			noi.append(self._intrare_noua(ref))
		if not noi:
			return 0
		with self._in_pas(ngettext("Un canal pus în alternative", "%d canale puse în alternative", len(noi)) %
				len(noi)):
			self._pune_b(a.cu(intrari=list(a.intrari) + noi))
		return len(noi)

	def alternative_desface(self, buchet_id, indice):
		"""Grupa de alternative de pe randul `indice` inlocuita cu canalele ei, in ordine; fisierul ei pleaca daca
		nu mai e folosit in alt buchet. -> numele schimbarii."""
		b, x = self._alternativa(buchet_id, indice)
		a = self.d.buchete.get(x.fisier)
		canale = [self._intrare_noua(i.ref, i.descriere) for i in (a.intrari if a is not None else ()) if
			i.fel == "canal"]
		nume = _t("Alternative desfăcute: %s") % self._nume_rand(x)
		with self._in_pas(nume):
			l = list(b.intrari)
			l[indice:indice + 1] = canale
			self._pune_b(b.cu(intrari=l))
			if a is not None and not any(i.fisier == a.id for c in self.d.buchete.values() for i in c.intrari):
				self._scoate_b(a.id)
		return nume

	# ------------------------------------------------ satelitii, transponderele, steagurile, detaliile (Mod avansat)

	def sterge_sateliti(self, pozitii, pastreaza=False):
		"""Toate serviciile (TV, radio, date) si transponderele pozitiilor date, sau, cu pastreaza=True, ale tuturor
		celorlalte; randurile lor din buchete pleaca si ele. Un singur pas. -> numarul serviciilor sterse."""
		alese = set(pozitii)
		tp = [k for k, t in self.d.lamedb.transpondere.items() if (t.poz in alese) != bool(pastreaza)]
		if not tp:
			raise Eroare(_t("Nu e nimic de șters."))
		n = len(alese)
		nume = (ngettext("Un satelit păstrat, restul șterse", "%d sateliți păstrați, restul șterse", n) % n
			if pastreaza else ngettext("Un satelit șters din receptor", "%d sateliți șterși din receptor", n) % n)
		return self.sterge_transpondere(tp, nume)

	def muta_satelit(self, din_poz, la_poz, copiaza=False):
		"""Transponderele si serviciile unei pozitii de satelit mutate (sau copiate) pe alta pozitie: namespace-ul
		(pozitia in cei 16 biti de sus), pozitia din randul transponderului si, la mutare, referintele din buchete si
		din listele parentale. Un singur pas. -> cate servicii."""
		for p in (din_poz, la_poz):
			if not isinstance(p, int) or not 0 <= p < 3600:
				raise Eroare(_t("Poziția satelitului nu e bună."))
		if din_poz == la_poz:
			return 0
		db = self.d.lamedb
		tp = [t for t in db.transpondere.values() if t.poz == din_poz and t.fel == "s"]
		if not tp:
			raise Eroare(_t("Nu e nimic de șters."))
		noi_ns = {}
		for t in tp:
			ns = (la_poz << 16) | (t.ns & 0xffff)
			if (ns, t.tsid, t.onid) in db.transpondere:
				raise Eroare(_t("Pe poziția nouă sunt deja aceleași transpondere."))
			noi_ns[t.cheie] = ns
		sv = [s for s in db.servicii.values() if s.tp_cheie in noi_ns]
		nume = (_t("Satelit copiat: %s -> %s") if copiaza else _t("Satelit mutat: %s -> %s")) % (
			D.text_pozitie(din_poz), D.text_pozitie(la_poz))
		schimb = {}
		with self._in_pas(nume):
			for t in tp:
				ns = noi_ns[t.cheie]
				nou = D.Transponder(ns, t.tsid, t.onid, t.randuri).cu_campuri(
					{"pozitie": la_poz if la_poz <= 1800 else la_poz - 3600})
				self._tine_t(nou.cheie)
				db.transpondere[nou.cheie] = nou
				if not copiaza:
					self._tine_t(t.cheie)
					db.transpondere.pop(t.cheie, None)
			for s in sv:
				ns = noi_ns[s.tp_cheie]
				n = D.Serviciu(s.sid, ns, s.tsid, s.onid, s.tip, s.nume, s.date, s.rest)
				self._pune_s(n)
				schimb[s.cheie] = n
				if not copiaza:
					self._scoate_s(s.k5)
			if not copiaza and schimb:
				for b in list(self.d.buchete.values()):
					if not any(i.cheie in schimb for i in b.intrari):
						continue
					l = []
					for i in b.intrari:
						n = schimb.get(i.cheie)
						if n is not None:
							parti = i.ref.split(":")
							parti[6] = "%X" % n.ns
							i = self._intrare_noua(":".join(parti), i.descriere)
						l.append(i)
					self._pune_b(b.cu(intrari=l))
				self._tine_p()
				for fel in ("blacklist", "whitelist"):
					l = []
					for r in getattr(self.d, fel):
						n = schimb.get(D.cheie_din_ref(r))
						if n is not None:
							parti = r.split(":")
							parti[6] = "%X" % n.ns
							r = ":".join(parti)
						l.append(r)
					setattr(self.d, fel, tuple(l) if isinstance(getattr(self.d, fel), tuple) else l)
				self._parental_schimbat()
			db.schimbat()
		return len(sv)

	def transponder(self, tp_cheie):
		"""{cheie, fel, poz, text, campuri} pentru foaia de editare (campuri numai la satelit)."""
		t = self.d.lamedb.transpondere.get(tuple(tp_cheie))
		if t is None:
			raise Eroare(_t("Transponderul nu mai există."))
		return {"cheie": t.cheie_text(), "fel": t.fel, "poz": t.poz, "text": t.text(), "campuri": t.campuri(),
			"servicii": sum(1 for s in self.d.lamedb.servicii.values() if s.tp_cheie == t.cheie)}

	def _verifica_campuri(self, v):
		f = v.get("frecventa")
		if f is not None and not 2000000 <= f <= 30000000:
			raise Eroare(_t("Frecvența trebuie dată în MHz, între 2000 și 30000."))
		sr = v.get("sr")
		if sr is not None and not 50000 <= sr <= 70000000:
			raise Eroare(_t("Rata de simbol trebuie dată în kS/s, între 50 și 70000."))
		for nume, a, b in (("pol", 0, 3), ("fec", 0, 15), ("sistem", 0, 1), ("modulatie", 0, 9), ("rolloff", 0, 3),
				("pilot", 0, 2), ("inversiune", 0, 2), ("is_id", -1, 255), ("pls_mod", 0, 3), ("pls_cod", 0, 262143)):
			x = v.get(nume)
			if x is not None and not a <= x <= b:
				raise Eroare(_t("O valoare a transponderului nu e bună: %s.") % nume)

	def schimba_transponder(self, tp_cheie, valori):
		"""Parametrii unui transponder de satelit (frecventa, rata de simbol, polarizarea, FEC, sistemul, modulatia,
		rolloff, pilot, MIS / PLS); cheia si serviciile lui raman. -> numele schimbarii."""
		k = tuple(tp_cheie)
		t = self.d.lamedb.transpondere.get(k)
		if t is None:
			raise Eroare(_t("Transponderul nu mai există."))
		if t.fel != "s":
			raise Eroare(_t("Numai transponderele de satelit se pot schimba aici."))
		valori = dict((n, int(x)) for n, x in valori.items() if n in D.Transponder.CAMPURI_S and x is not None and
			n not in ("pozitie",))
		self._verifica_campuri(valori)
		nou = t.cu_campuri(valori)
		if nou.randuri == t.randuri:
			return None
		nume = _t("Transponder schimbat: %s") % (t.text() or t.cheie_text())
		with self._in_pas(nume):
			self._tine_t(k)
			self.d.lamedb.transpondere[k] = nou
			self.d.lamedb.schimbat()
		return nume

	def transponder_nou(self, poz, valori, tsid, onid):
		"""Un transponder de satelit nou in lamedb (fara servicii: o cautare pe el le aduce). -> cheia ca text."""
		if not isinstance(poz, int) or not 0 <= poz < 3600:
			raise Eroare(_t("Poziția satelitului nu e bună."))
		valori = dict((n, int(x)) for n, x in valori.items() if n in D.Transponder.CAMPURI_S and x is not None)
		for n in ("frecventa", "sr", "pol"):
			if n not in valori:
				raise Eroare(_t("Transponderul nou cere frecvența, rata de simbol și polarizarea."))
		self._verifica_campuri(valori)
		if not (0 <= tsid <= 0xffff and 0 <= onid <= 0xffff):
			raise Eroare(_t("TSID și ONID trebuie să fie între 0 și 65535."))
		ns = poz << 16
		k = (ns, tsid, onid)
		if k in self.d.lamedb.transpondere:
			raise Eroare(_t("Transponderul există deja (aceeași poziție, TSID și ONID)."))
		valori["pozitie"] = poz if poz <= 1800 else poz - 3600
		for n, implicit in (("fec", 0), ("inversiune", 2), ("steaguri", 0), ("sistem", 0), ("modulatie", 1),
				("rolloff", 0), ("pilot", 2)):
			valori.setdefault(n, implicit)
		t = D.Transponder(ns, tsid, onid, []).cu_campuri(valori)
		with self._in_pas(_t("Transponder nou: %s") % t.text()):
			self._tine_t(k)
			self.d.lamedb.transpondere[k] = t
			self.d.lamedb.schimbat()
		return t.cheie_text()

	def curata_steaguri(self, fel):
		"""fel: "ascunse" (toate canalele ascunse aratate), "blocate" (toate deblocate), "noi" (semnul nou gasit
		scos de pe toate). -> cate canale s-au schimbat."""
		sv = list(self.d.lamedb.servicii.values())
		if fel == "ascunse":
			return self.ascunde([s.ref for s in sv if s.ascuns], False)
		if fel == "blocate":
			return self.blocheaza([s.ref for s in sv if self._blocat_cheie(s.cheie)], False) or 0
		if fel == "noi":
			return self.scoate_nou([s.ref for s in sv if s.steaguri & D.DX_NOU])
		raise Eroare(_t("Operația nu e cunoscută."))

	def scoate_nou(self, refs):
		"""Semnul nou gasit (dxNewFound) scos de pe canale. -> cate."""
		sv = [s for s in self._servicii_din(refs) if s.steaguri & D.DX_NOU]
		if not sv:
			return 0
		with self._in_pas(ngettext("Semnul „nou” scos de pe un canal", "Semnul „nou” scos de pe %d canale",
				len(sv)) % len(sv)):
			for s in sv:
				self._pune_s(s.cu(steaguri=s.steaguri & ~D.DX_NOU))
		return len(sv)

	STEAGURI_EDITABILE = (D.DX_NOSDT, D.DX_ASCUNS, D.DX_NODVB, D.DX_PASTREAZA_NUMELE, D.DX_NOU)

	def detalii(self, ref):
		"""Tot ce stie lamedb despre canal: referinta, SID / TSID / ONID / namespace, tipul, furnizorul, steagurile,
		PID-urile tinute minte (c:), CAID-urile, transponderul, buchetele."""
		k = D.cheie_din_ref(ref)
		sv = self.d.lamedb.dupa_cheie(k) if k else []
		if not sv:
			raise Eroare(_t("Canalul nu mai există în lista receptorului."))
		s = sv[0]
		t = self.d.lamedb.transpondere.get(s.tp_cheie)
		c = self._canal(s)
		return {"ref": s.ref, "cheie": s.cheie, "nume": s.nume, "furnizor": s.furnizor, "sid": s.sid, "tsid": s.tsid,
			"onid": s.onid, "ns": "%08x" % s.ns, "tip": s.tip, "steaguri": s.steaguri, "pids": dict(s.cache),
			"caids": ["%04x" % x for x in s.caids], "poz_text": c.poz_text, "tp_text": c.tp_text,
			"tp": t.cheie_text() if t is not None else "", "tp_campuri": t.campuri() if t is not None else {},
			"buchete": [self._info_buchet(self.d.buchete[b]).nume for b in self.in_buchete(s.ref) if b in self.d.buchete],
			"dubluri": len(sv)}

	def schimba_serviciu(self, ref, furnizor=None, steaguri=None, pids=None):
		"""Mod avansat: furnizorul, steagurile (numai cele din STEAGURI_EDITABILE) si PID-urile tinute minte (c:)
		ale unui canal. SID-ul si tipul nu se schimba aici (ar strica referintele din buchete). -> numele schimbarii."""
		k = D.cheie_din_ref(ref)
		sv = self.d.lamedb.dupa_cheie(k) if k else []
		if not sv:
			raise Eroare(_t("Canalul nu mai există în lista receptorului."))
		masca = 0
		for x in self.STEAGURI_EDITABILE:
			masca |= x
		noi = []
		for s in sv:
			f, st, caids, cache, alte = s._desparte()
			if furnizor is not None:
				f = D.curat_nume(furnizor)
			if steaguri is not None:
				st = (st & ~masca) | (int(steaguri) & masca)
			if pids is not None:
				cache = {}
				for cheie, val in pids.items():
					cheie, val = int(cheie), int(val)
					if not (0 <= cheie <= 99 and 0 <= val <= 0xffff):
						raise Eroare(_t("Un PID nu e bun."))
					cache[cheie] = val
			date = D.scrie_date(f, cache, caids, st, alte)
			if date != s.date:
				noi.append(D.Serviciu(s.sid, s.ns, s.tsid, s.onid, s.tip, s.nume, date, s.rest))
		if not noi:
			return None
		nume = _t("Detalii schimbate: %s") % (sv[0].nume or _t("fără nume"))
		with self._in_pas(nume):
			for s in noi:
				self._pune_s(s)
		return nume

	# ------------------------------------------------ randurile buchetelor: scoaterea dintr-un buchet ales, fluxurile

	def scoate_canale(self, buchet_id, refs):
		"""Canalele (dupa cheie) scoase dintr-un singur buchet (raman in receptor si in celelalte)."""
		b = self._b(buchet_id)
		chei = set(D.cheie_din_ref(r) or r for r in refs)
		ind = [k for k, i in enumerate(b.intrari) if (i.cheie or i.ref) in chei]
		if not ind:
			return None
		return self.scoate(buchet_id, ind)

	def schimba_flux(self, buchet_id, indice, adresa=None, tip=None, sid=None, tsid=None, onid=None, ns=None):
		"""Adresa, tipul (1, 4097, 5001, 5002) si numerele DVB ale unui flux (cu ele imaginea ii gaseste sigla dupa
		referinta). Numele ramane (Redenumeste). -> numele schimbarii."""
		b = self._b(buchet_id)
		if not 0 <= indice < len(b.intrari) or b.intrari[indice].fel != "flux":
			raise Eroare(_t("Rândul ales nu e un flux."))
		x = b.intrari[indice]
		parti = x.ref.split(":")
		while len(parti) < 12:
			parti.append("")
		if tip is not None:
			if int(tip) not in (1, 4097, 5001, 5002, 5003, 8193, 8739):
				raise Eroare(_t("Tipul fluxului nu e cunoscut."))
			parti[0] = str(int(tip))
		for i, v in ((3, sid), (4, tsid), (5, onid), (6, ns)):
			if v is not None:
				v = int(v)
				if not 0 <= v <= (0xffffffff if i == 6 else 0xffff):
					raise Eroare(_t("Un număr DVB al fluxului nu e bun."))
				parti[i] = "%X" % v
		if adresa is not None:
			adresa = adresa.strip()
			if "://" not in adresa or any(c in adresa for c in "\r\n"):
				raise Eroare(_t("Adresa fluxului nu e bună (trebuie să înceapă cu http:// sau https://)."))
			parti[10] = D.codeaza(adresa)
		ref = ":".join(parti[:11]) + (":" + ":".join(parti[11:]) if any(parti[11:]) else ":")
		if ref == x.ref:
			return None
		if len(("#SERVICE " + ref).encode("utf-8")) > D.LUNGIME_MAXIMA:
			raise Eroare(_t("Adresa fluxului e prea lungă pentru lista de canale."))
		nume = _t("Flux schimbat: %s") % self._nume_rand(x)
		with self._in_pas(nume):
			l = list(b.intrari)
			l[indice] = self._intrare_noua(ref, x.descriere)
			self._pune_b(b.cu(intrari=l))
		return nume

	# ------------------------------------------------ sortarea in mai multe buchete, ordinea unui model, inlocuirea

	def sorteaza_buchete(self, buchete, dupa="nume", invers=False):
		"""Fiecare buchet dat sortat (pe grupe intre marcaje), intr-un singur pas. -> cate s-au schimbat."""
		noi = []
		for bid in buchete:
			b = self._b(bid)
			nou = U.sorteaza(b.intrari, self._cheie_sortare(dupa), None, invers)
			if [x.id for x in nou] != [x.id for x in b.intrari]:
				noi.append(b.cu(intrari=nou))
		if not noi:
			return 0
		with self._in_pas(ngettext("Un buchet sortat", "%d buchete sortate", len(noi)) % len(noi)):
			for b in noi:
				self._pune_b(b)
		return len(noi)

	def aranjeaza_dupa(self, buchet_id, model_id):
		"""Canalele buchetului puse in ordinea din buchetul-model (cele care nu sunt in model raman dupa ele, in
		ordinea lor); marcajele si celelalte randuri stau pe loc. -> True sau None (nimic schimbat)."""
		b, m = self._b(buchet_id), self._b(model_id)
		ordine = {}
		for k, i in enumerate(m.intrari):
			ordine.setdefault(i.cheie or i.ref, k)
		locuri = [k for k, i in enumerate(b.intrari) if i.fel in ("canal", "flux")]
		canale = [b.intrari[k] for k in locuri]
		canale.sort(key=lambda i: ordine.get(i.cheie or i.ref, len(ordine)))
		l = list(b.intrari)
		for k, i in zip(locuri, canale):
			l[k] = i
		if [x.id for x in l] == [x.id for x in b.intrari]:
			return None
		with self._in_pas(_t("Aranjat după: %s") % self._info_buchet(m).nume):
			self._pune_b(b.cu(intrari=l))
		return True

	def inlocuieste_nume(self, cauta, cu, refs=(), buchete=()):
		"""Textul `cauta` (fara deosebire intre litere mari si mici) inlocuit cu `cu` in numele canalelor date (din
		lamedb, cu HoldName) si ale buchetelor date. Un singur pas. -> cate nume s-au schimbat."""
		if not cauta:
			raise Eroare(_t("Scrie textul de căutat."))
		tipar = re.compile(re.escape(cauta), re.I)
		sv_noi, b_noi = [], []
		for s in self._servicii_din(refs):
			nou = D.curat_nume(tipar.sub(cu.replace("\\", "\\\\"), s.nume))
			if nou and nou != s.nume:
				sv_noi.append(s.cu(nume=nou, steaguri=s.steaguri | D.DX_PASTREAZA_NUMELE))
		for bid in buchete:
			b = self.d.buchete.get(bid)
			if b is None:
				continue
			vechi = D.fara_mod(b.nume)
			nou = D.curat_nume(tipar.sub(cu.replace("\\", "\\\\"), vechi), 100)
			if nou and nou != vechi:
				are_mod = b.nume != vechi or bid.startswith("userbouquet.")
				b_noi.append(b.cu(nume=D.cu_mod(nou, b.radio) if are_mod else nou))
		n = len(sv_noi) + len(b_noi)
		if not n:
			return 0
		with self._in_pas(ngettext("Un nume înlocuit", "%d nume înlocuite", n) % n):
			for s in sv_noi:
				self._pune_s(s)
			for b in b_noi:
				self._pune_b(b)
		return n

	def readu_din_copie(self, copie_id, chei):
		"""Canalele (dupa cheie) din copia de siguranta puse inapoi in lista (cu transponderele lor, daca lipsesc);
		cele care exista deja se sar. Un singur pas. -> cate."""
		d = citeste_copia(copie_id, self.director)
		alese = set(chei)
		sv = [s for s in d.lamedb.servicii.values() if s.cheie in alese and s.k5 not in self.d.lamedb.servicii]
		if not sv:
			return 0
		with self._in_pas(ngettext("Un canal adus înapoi din copie", "%d canale aduse înapoi din copie", len(sv)) %
				len(sv)):
			for s in sv:
				if s.tp_cheie not in self.d.lamedb.transpondere and s.tp_cheie in d.lamedb.transpondere:
					self._tine_t(s.tp_cheie)
					self.d.lamedb.transpondere[s.tp_cheie] = d.lamedb.transpondere[s.tp_cheie]
				self._pune_s(D.Serviciu(s.sid, s.ns, s.tsid, s.onid, s.tip, s.nume, s.date, s.rest))
			self.d.lamedb.schimbat()
		return len(sv)

	def verifica(self):
		"""Grupele uneltei „Verifică lista” (U.verifica)."""
		return U.verifica(self)

	def buchete_din(self, fel, valori, radio=False):
		"""Cate un buchet din fiecare satelit (poz) sau furnizor (nume) ales, intr-un singur pas de anulare:
		[id buchet]. Cei fara niciun canal de pus (toate ascunse) se sar; niciunul = Eroare."""
		if fel not in ("satelit", "furnizor"):
			raise Eroare(_t("Nu știu din ce să fac buchetul."))
		de_facut = []
		for v in valori:
			if fel == "satelit":
				canale = self.din_satelit(v, radio)
				nume = self.nume_satelit(v) or self._text_poz(v)
			else:
				canale = self.din_furnizor(v, radio)
				nume = v or _t("Fără furnizor")
			refs = []
			vazute = set()
			for c in canale:
				if c.ascuns or c.cheie in vazute:
					continue
				vazute.add(c.cheie)
				refs.append(c.ref)
			if refs:
				de_facut.append((D.curat_nume(nume, 100) or _t("Buchet nou"), refs))
		if not de_facut:
			raise Eroare(_t("Nu e niciun canal de pus în buchet."))
		rez = []
		with self._in_pas(ngettext("Un buchet nou", "%d buchete noi", len(de_facut)) % len(de_facut)):
			for nume, refs in de_facut:
				rez.append(self._pune_buchet_nou(nume, radio, self.radacina(radio), None,
					[self._intrare_noua(r) for r in refs]))
		return rez

	def repara_moarte(self, randuri):
		"""Randurile cu .inlocuire (CanalInfo) sunt legate la serviciul nou, restul scoase din buchet."""
		pe_buchet = {}
		for r in randuri:
			pe_buchet.setdefault(r.buchet_id, {})[r.id_intrare] = getattr(r, "inlocuire", None)
		n = 0
		with self._in_pas(ngettext("Un canal care nu mai există, reparat", "%d canale care nu mai există, reparate",
				len(randuri)) % len(randuri)) as pas:
			for bid, harta in pe_buchet.items():
				b = self.d.buchete.get(bid)
				if b is None:
					continue
				l = []
				for i in b.intrari:
					if i.id in harta:
						n += 1
						inl = harta[i.id]
						if inl is not None:
							l.append(i.cu(ref=inl.ref))
						continue
					l.append(i)
				self._pune_b(b.cu(intrari=l))
			if n == 0:
				pas.nume = None
		return n

	# ------------------------------------------------ uneltele

	def canale_test(self, radio=None):
		return U.canale_test(self, radio)

	def _unealta_fundal(self, functie, la_gata, la_eroare):
		"""Unealta pe un fir. Ea numai citeste, deci cat merge sesiunea nu e „ocupata” pentru citiri si inchidere
		(pagina web isi deschide buchetele, omul poate iesi), dar operatiile si alta unealta asteapta (Ocupat).
		Rezultatul vine si dupa inchiderea sesiunii (cererea web care il asteapta trebuie sa primeasca raspuns)."""
		self._verifica()

		def gata(r):
			self._unealta = None
			la_gata(r)

		def eroare(e):
			self._unealta = None
			if la_eroare is not None:
				la_eroare(e)
		f = _Fir(functie, gata, eroare)
		self._unealta = f
		f.porneste()

	def canale_test_fundal(self, la_gata, la_eroare=None, radio=None):
		self._unealta_fundal(lambda: U.canale_test(self, radio), la_gata, la_eroare)

	def dubluri_fundal(self, la_gata, la_eroare=None):
		self._unealta_fundal(lambda: U.dubluri(self), la_gata, la_eroare)

	def referinte_moarte_fundal(self, la_gata, la_eroare=None):
		self._unealta_fundal(lambda: U.referinte_moarte(self), la_gata, la_eroare)

	def probleme_fundal(self, la_gata, la_eroare=None):
		self._unealta_fundal(lambda: U.probleme(self), la_gata, la_eroare)

	def dubluri(self):
		return U.dubluri(self)

	def referinte_moarte(self):
		return U.referinte_moarte(self)

	def probleme(self):
		return U.probleme(self)

	# ------------------------------------------------ importul

	def importa_m3u(self, text, nume, radio=False, pe_grupe=False):
		bucati = U.citeste_m3u(text)
		if not bucati:
			raise Eroare(_t("Fișierul nu are niciun flux."))
		if pe_grupe:
			grupe = {}
			ordine = []
			for g, n, url in bucati:
				if g not in grupe:
					grupe[g] = []
					ordine.append(g)
				grupe[g].append((n, url))
			ids = []
			with self._in_pas(_t("Fluxuri importate: %s") % nume):
				for g in ordine:
					ids.append(self._buchet_fluxuri(g or nume, grupe[g], radio, False))
			return ids[0] if ids else None
		with self._in_pas(_t("Fluxuri importate: %s") % nume):
			return self._buchet_fluxuri(nume, [(n, url, g) for g, n, url in bucati], radio, True)

	def _buchet_fluxuri(self, nume, randuri, radio, cu_marcaje):
		nume = D.curat_nume(nume, 100) or _t("Fluxuri")
		rad = self._b(self.radacina(radio))
		id_ = D.id_buchet_nou(nume, radio, set(self.d.buchete) | set(self._baza[1]))
		intrari = []
		grupa = None
		nr = 0
		for r in randuri:
			n, url = r[0], r[1]
			g = r[2] if len(r) > 2 else None
			if cu_marcaje and g and g != grupa:
				grupa = g
				intrari.append(self._intrare_noua(D.ref_marcaj(D.curat_nume(g), nr), D.curat_nume(g)))
				nr += 1
			n = D.curat_nume(n) or url
			ref = "4097:0:1:0:0:0:0:0:0:0:%s:%s" % (D.codeaza(url), D.codeaza(n))
			if len(("#SERVICE " + ref).encode("utf-8")) > D.LUNGIME_MAXIMA:
				continue
			intrari.append(self._intrare_noua(ref, n))
		self._pune_b(D.Buchet(id_, D.cu_mod(nume, radio), intrari))
		self._pune_b(rad.cu(intrari=list(rad.intrari) + [self._intrare_noua(D.ref_buchet(id_))]))
		return id_

	def importa_dosar(self, director, ce=("lamedb", "buchete"), buchete=None, mod="inlocuieste"):
		"""O lista din alt dosar (arhiva despachetata): lamedb si / sau buchetele (toate sau cele din `buchete`).
		mod "inlocuieste": lista de acum se inlocuieste; "uneste" („Adaugă numai ce lipsește”): serviciile si
		transponderele noi se adauga, buchetele noi se adauga, iar intr-un buchet care exista deja (acelasi fisier) se
		adauga la sfarsit numai randurile care lipsesc (nimic din ce are omul nu se pierde)."""
		alta = D.citeste_dosar(director, None, "/nu-exista")
		rez = {"servicii": 0, "transpondere": 0, "buchete": 0}
		with self._in_pas(_t("Listă importată")) as pas:
			if "lamedb" in ce and alta.lamedb.servicii:
				if mod == "inlocuieste":
					for k5 in list(self.d.lamedb.servicii):
						if k5 not in alta.lamedb.servicii:
							self._scoate_s(k5)
					for k in list(self.d.lamedb.transpondere):
						if k not in alta.lamedb.transpondere:
							self._tine_t(k)
							self.d.lamedb.transpondere.pop(k, None)
							self.d.lamedb.schimbat()
				for k, t in alta.lamedb.transpondere.items():
					if mod == "inlocuieste" or k not in self.d.lamedb.transpondere:
						vechi = self.d.lamedb.transpondere.get(k)
						if vechi is None or vechi.randuri != t.randuri:
							self._tine_t(k)
							self.d.lamedb.transpondere[k] = D.Transponder(t.ns, t.tsid, t.onid, t.randuri)
							self.d.lamedb.schimbat()
							rez["transpondere"] += 1
				for k5, s in alta.lamedb.servicii.items():
					vechi = self.d.lamedb.servicii.get(k5)
					if vechi is not None and mod != "inlocuieste":
						continue
					if vechi is None or vechi.nume != s.nume or vechi.date != s.date:
						self._pune_s(D.Serviciu(s.sid, s.ns, s.tsid, s.onid, s.tip, s.nume, s.date, s.rest))
						rez["servicii"] += 1
			if "buchete" in ce:
				alese = set(buchete) if buchete else None
				for radio in (False, True):
					rad_id = self.radacina(radio)
					rad_alta = alta.buchete.get(rad_id)
					if rad_alta is None:
						continue
					rad = self._b(rad_id)
					if mod == "inlocuieste" and alese is None:
						for i in rad.intrari:
							if i.fel == "subbuchet" and i.fisier in self.d.buchete:
								self._scoate_b(i.fisier)
						self._pune_b(rad.cu(intrari=()))
						rad = self._b(rad_id)
					l = list(rad.intrari)
					for i in rad_alta.intrari:
						f = i.fisier
						if i.fel != "subbuchet" or f not in alta.buchete:
							continue
						if alese is not None and f not in alese:
							continue
						if mod == "uneste":
							self._uneste_arbore(alta, f)
						else:
							self._copiaza_arbore(alta, f)
						rez["buchete"] += 1
						if not any(j.fisier == f for j in l):
							l.append(self._intrare_noua(i.ref, i.descriere))
					self._pune_b(rad.cu(intrari=l))
			if not any(rez.values()):
				pas.nume = None
		return rez

	def _uneste_arbore(self, alta, fisier, vazute=None):
		"""Buchetul `fisier` din lista importata: nou = copiat; existent = randurile care lipsesc puse la sfarsit."""
		vazute = vazute if vazute is not None else set()
		al_meu = self.d.buchete.get(fisier)
		if al_meu is None:
			self._copiaza_arbore(alta, fisier, vazute)
			return
		if fisier in vazute:
			return
		vazute.add(fisier)
		b = alta.buchete[fisier]
		are = set(i.ref for i in al_meu.intrari)
		noi = [self._intrare_noua(i.ref, i.descriere) for i in b.intrari if i.ref not in are]
		if noi:
			self._pune_b(al_meu.cu(intrari=list(al_meu.intrari) + noi))
		for i in b.intrari:
			if i.fel in ("subbuchet", "alternative") and i.fisier in alta.buchete:
				self._uneste_arbore(alta, i.fisier, vazute)

	def _copiaza_arbore(self, alta, fisier, vazute=None):
		vazute = vazute if vazute is not None else set()
		if fisier in vazute:
			return
		vazute.add(fisier)
		b = alta.buchete[fisier]
		self._pune_b(D.Buchet(fisier, b.nume, [self._intrare_noua(i.ref, i.descriere) for i in b.intrari], b.crlf))
		for i in b.intrari:
			if i.fel in ("subbuchet", "alternative") and i.fisier in alta.buchete:
				self._copiaza_arbore(alta, i.fisier, vazute)

	# ------------------------------------------------ exportul

	def text_fisiere(self):
		"""{nume fisier: octeti} ale listei de acum (pentru export si pentru salvare)."""
		rez = {"lamedb": self.d.lamedb.text().encode("utf-8", "surrogateescape")}
		for b in self.d.buchete.values():
			rez[b.id] = b.text().encode("utf-8", "surrogateescape")
		if self.d.blacklist or os.path.exists(os.path.join(self.director, "blacklist")):
			rez["blacklist"] = _text_lista(self.d.blacklist)
		if self.d.whitelist or os.path.exists(os.path.join(self.director, "whitelist")):
			rez["whitelist"] = _text_lista(self.d.whitelist)
		return rez

	def exporta_m3u(self, buchet_id, gazda="", port=8001):
		return U.exporta_m3u(self, buchet_id, gazda, port)

	# ------------------------------------------------ salvarea

	def schimbari(self):
		"""Rezumatul de dinaintea salvarii: canale adaugate / sterse / schimbate, buchete schimbate."""
		baza_db, baza_b = self._baza[0], self._baza[1]
		noi = sum(1 for k in self.d.lamedb.servicii if k not in baza_db.servicii)
		sterse = sum(1 for k in baza_db.servicii if k not in self.d.lamedb.servicii)
		schimbate = sum(1 for k, s in self.d.lamedb.servicii.items() if k in baza_db.servicii and
			baza_db.servicii[k] is not s)
		buchete = [k for k in set(self.d.buchete) | set(baza_b) if self.d.buchete.get(k) is not baza_b.get(k)]
		return {"servicii_noi": noi, "servicii_sterse": sterse, "servicii_schimbate": schimbate,
			"buchete": sorted(buchete), "parental": (self.d.blacklist, self.d.whitelist) != self._baza[2:4],
			"nesalvate": self.nesalvate()}

	def salveaza(self, descriere=""):
		"""Pe loc (probe)."""
		rez = []
		err = []
		self.salveaza_fundal(rez.append, err.append, descriere)
		if err:
			raise err[0]
		return rez[0] if rez else None

	def salveaza_fundal(self, la_gata, la_eroare=None, descriere=""):
		self._verifica()
		N = _nucleu()
		motiv = N.lista_tv_ocupata()
		if motiv:
			raise Eroare(motiv)
		memorie = N.memorie_lamedb()
		stare = (self.d.lamedb.copie(), dict(self.d.buchete), self.d.blacklist, self.d.whitelist)
		baza = self._baza
		director = self.director
		originale = dict(self.d.originale)
		cine = self.cine
		desc = descriere or _t("înainte de salvare")

		def pe_fir():
			plan = pregateste_salvarea(stare, baza, originale, memorie, director)
			plan["copie"] = fa_copie(director, desc, cine)
			scrie_planul(plan, director)
			return plan

		def gata(plan):
			try:
				N.aplica(plan["de_scos"], plan["tp_de_scos"])
				N.dupa_reincarcare()
			except Exception as e:
				_jurnal("reincarcarea: %r" % (e,))
				self._lucru = None
				if la_eroare:
					la_eroare(Eroare(_t("Lista s-a scris, dar nu s-a putut reîncărca. Repornește interfața.")))
				return
			memorie2 = N.memorie_lamedb()

			def verifica():
				return verifica_scrierea(plan["lamedb"], memorie2)

			def verificat(ok):
				self._lucru = None
				self._dupa_salvare(plan)
				c = plan["copie"]
				if c is not None:
					c.avertismente = list(plan["avertismente"])
					c.verificat = ok[0]
					c.diferente = ok[1]
				self.ultima_copie = c
				_anunta("salvat", c)
				la_gata(c)

			_pe_fir(self, verifica, verificat, eroare)

		def eroare(e):
			# si la pasul verificarii: sesiunea nu ramane „ocupata” dupa o eroare
			self._lucru = None
			if la_eroare:
				la_eroare(e)

		_pe_fir(self, pe_fir, gata, eroare)

	def _dupa_salvare(self, plan):
		"""Datele sesiunii = ce s-a scris (cu ce a venit din memorie); baza noua; anularea ramane."""
		db = plan["lamedb"]
		for k5, s in list(self.d.lamedb.servicii.items()):
			if k5 not in db.servicii:
				self.d.lamedb.servicii.pop(k5)
		for k5, s in db.servicii.items():
			if self.d.lamedb.servicii.get(k5) is not s:
				self.d.lamedb.servicii[k5] = s
		for k, t in db.transpondere.items():
			self.d.lamedb.transpondere.setdefault(k, t)
		self.d.lamedb.schimbat()
		for id_, text in plan["texte_buchete"].items():
			self.d.originale[id_] = text
		for id_ in plan["sterse"]:
			self.d.originale.pop(id_, None)
		self._baza = (self.d.lamedb.copie(), dict(self.d.buchete), self.d.blacklist, self.d.whitelist)
		self._salvat_poz = len(self._anulare)
		self._schimbat()

	# ------------------------------------------------ copiile de siguranta

	def copii(self):
		return lista_copii(self.director)

	def compara(self, copie_id):
		"""Lista de acum (cu schimbarile nesalvate) fata de o copie de siguranta: [Grupa] (canale noi, care nu mai
		sunt, redenumite; buchete noi, care nu mai sunt, schimbate). Numai citeste (merge pe firul uneltelor)."""
		return U.compara(self, citeste_copia(copie_id, self.director))

	def intoarce(self, copie_id):
		rez, err = [], []
		self.intoarce_fundal(copie_id, rez.append, err.append)
		if err:
			raise err[0]
		return rez[0] if rez else None

	def intoarce_fundal(self, copie_id, la_gata, la_eroare=None):
		self._verifica()
		N = _nucleu()
		motiv = N.lista_tv_ocupata()
		if motiv:
			raise Eroare(motiv)
		memorie = N.memorie_lamedb()
		director = self.director
		cine = self.cine

		def pe_fir():
			plan = pregateste_intoarcerea(copie_id, memorie, director, cine)
			return plan

		def gata(plan):
			try:
				N.aplica(plan["de_scos"], plan["tp_de_scos"])
				N.dupa_reincarcare()
			except Exception as e:
				_jurnal("reincarcarea: %r" % (e,))
			memorie2 = N.memorie_lamedb()

			def citeste():
				return D.citeste_dosar(director, memorie2, D.SATELITI)

			def citit(d):
				self._lucru = None
				self._incarca(d)
				_anunta("intors", plan["copie"])
				la_gata(plan["copie"])

			_pe_fir(self, citeste, citit, eroare)

		def eroare(e):
			# si la recitirea de dupa intoarcere: sesiunea nu ramane „ocupata” dupa o eroare
			self._lucru = None
			if la_eroare:
				la_eroare(e)

		_pe_fir(self, pe_fir, gata, eroare)


def _text_lista(randuri):
	return "".join(r + "\n" for r in randuri).encode("utf-8", "surrogateescape")


# ---------------------------------------------------------------- salvarea, fara sesiune (se probeaza singura)

def uneste_lamedb(baza, noi, memorie):
	"""Lista de scris: ce a schimbat editorul (noi fata de baza) peste lista din memorie. -> (Lamedb, avertismente)."""
	rez = D.Lamedb()
	if memorie is None:
		memorie = baza
	for k, t in noi.transpondere.items():
		b = baza.transpondere.get(k)
		if b is t and k in memorie.transpondere:
			m = memorie.transpondere[k]
			rez.transpondere[k] = t if m.randuri == t.randuri else m
		elif b is t and k not in memorie.transpondere:
			continue
		else:
			rez.transpondere[k] = t
	for k, t in memorie.transpondere.items():
		if k not in rez.transpondere and k not in baza.transpondere:
			rez.transpondere[k] = t
	for k, s in noi.servicii.items():
		b = baza.servicii.get(k)
		if b is s:
			m = memorie.servicii.get(k)
			if m is not None:
				# acelasi continut: ramane obiectul editorului (memoriile vederilor nu se refac)
				rez.servicii[k] = s if (m.nume == s.nume and m.date == s.date) else m
			continue
		rez.servicii[k] = s
	for k, s in memorie.servicii.items():
		if k not in rez.servicii and k not in baza.servicii:
			rez.servicii[k] = s
	return rez, []


def pregateste_salvarea(stare, baza, originale, memorie, director):
	"""Ce se scrie, ce se sterge si ce se scoate din memorie. stare / baza = (Lamedb, {buchete}, blacklist, whitelist)."""
	noi_db, noi_b, bl, wl = stare
	baza_db, baza_b, baza_bl, baza_wl = baza
	mem = None
	if memorie:
		try:
			mem = D.citeste_lamedb(memorie)
		except D.Stricat:
			mem = None
	db, avertismente = uneste_lamedb(baza_db, noi_db, mem)
	texte = {}
	sterse = []
	for id_ in set(noi_b) | set(baza_b):
		b, vechi = noi_b.get(id_), baza_b.get(id_)
		if b is vechi:
			continue
		disc = D._citeste_fisier(os.path.join(director, id_))
		if disc is not None and originale.get(id_) is not None and disc != originale.get(id_):
			avertismente.append(_t("Buchetul %s s-a schimbat și pe receptor între timp; a rămas varianta din editor.")
				% D.fara_mod(b.nume if b is not None else vechi.nume))
		if b is None:
			sterse.append(id_)
		else:
			texte[id_] = b.text().encode("utf-8", "surrogateescape")
	text_db = db.text().encode("utf-8", "surrogateescape")
	scris = {"lamedb": text_db}
	scris.update(texte)
	if bl != baza_bl:
		scris["blacklist"] = _text_lista(bl)
	if wl != baza_wl:
		scris["whitelist"] = _text_lista(wl)
	# ce se scoate din memorie: serviciile care nu mai sunt sau care s-au schimbat
	de_scos, tp_de_scos = [], []
	if mem is not None:
		for k5, s in mem.servicii.items():
			n = db.servicii.get(k5)
			if n is None or n.nume != s.nume or n.date != s.date:
				de_scos.append(s.ref)
		for k, t in mem.transpondere.items():
			if k not in db.transpondere:
				p = t.poz
				tp_de_scos.append((t.ns, t.tsid, t.onid, p if isinstance(p, int) else 0))
	return {"scris": scris, "sterse": sterse, "lamedb": db, "texte_buchete": texte, "de_scos": de_scos,
		"tp_de_scos": tp_de_scos, "avertismente": avertismente}


def _scrie_sigur(cale, date):
	nou = cale + ".nou"
	try:
		with open(nou, "wb") as f:
			f.write(date)
			f.flush()
			os.fsync(f.fileno())
		os.replace(nou, cale)
	except Exception:
		try:
			os.remove(nou)
		except OSError:
			pass
		raise


def _loc_liber(dosar):
	try:
		st = os.statvfs(dosar)
		return st.f_bavail * st.f_frsize
	except (OSError, AttributeError):
		return None


def scrie_planul(plan, director):
	"""Fisierele scrise (lamedb ultimul: o cadere la jumatate lasa buchetele noi pe lista veche, nu invers)."""
	marime = sum(len(v) for v in plan["scris"].values())
	liber = _loc_liber(director)
	if liber is not None and liber < marime + LOC_MINIM:
		raise Eroare(_t("Nu e loc destul în memoria receptorului pentru lista de canale."))
	for nume, date in sorted(plan["scris"].items(), key=lambda x: x[0] == "lamedb"):
		_scrie_sigur(os.path.join(director, nume), date)
	for nume in plan["sterse"]:
		try:
			os.remove(os.path.join(director, nume))
		except OSError:
			pass
	try:
		fd = os.open(director, os.O_RDONLY)
		try:
			os.fsync(fd)
		finally:
			os.close(fd)
	except (OSError, AttributeError):
		pass


def verifica_scrierea(scris, memorie):
	"""(ok, diferente): lista din memorie dupa reincarcare are aceleasi servicii si aceleasi nume ca ce s-a scris."""
	if memorie is None:
		return (None, {})
	try:
		mem = D.citeste_lamedb(memorie)
	except D.Stricat:
		return (False, {"citire": 1})
	lipsa = sum(1 for k in scris.servicii if k not in mem.servicii)
	in_plus = sum(1 for k in mem.servicii if k not in scris.servicii)
	nume = sum(1 for k, s in scris.servicii.items() if k in mem.servicii and
		D.taie_octeti(mem.servicii[k].nume, D.LUNGIME_MAXIMA) != D.taie_octeti(s.nume, D.LUNGIME_MAXIMA))
	dif = {"lipsa": lipsa, "in_plus": in_plus, "nume": nume}
	return (not any(dif.values()), dif)


# ---------------------------------------------------------------- copiile de siguranta

class Copie(object):
	__slots__ = ("id", "cand", "descriere", "marime", "cine", "servicii", "buchete", "avertismente", "verificat",
		"diferente")

	def __init__(self, id_, cand, descriere="", marime=0, cine="", servicii=0, buchete=0):
		self.id, self.cand, self.descriere, self.marime, self.cine = id_, cand, descriere, marime, cine
		self.servicii, self.buchete = servicii, buchete
		self.avertismente = []
		self.verificat = None
		self.diferente = {}


def _fisiere_de_copiat(director):
	try:
		nume = os.listdir(director)
	except OSError:
		return []
	rez = []
	for f in sorted(nume):
		if f in FISIERE_COPIE or (f.startswith(PREFIXE_COPIE) and (f.endswith(".tv") or f.endswith(".radio"))):
			if os.path.isfile(os.path.join(director, f)):
				rez.append(f)
	return rez


def _dosar_copii(director):
	return DOSAR_COPII if director == DIRECTOR else os.path.join(director, "hds-copii-canale")


def fa_copie(director=DIRECTOR, descriere="", cine=""):
	"""Copia datata a fisierelor de acum (tar.gz + descrierea .json); se pastreaza ultimele MAX_COPII. -> Copie sau
	None (nimic de copiat)."""
	dosar = _dosar_copii(director)
	fisiere = _fisiere_de_copiat(director)
	if not fisiere:
		return None
	try:
		os.makedirs(dosar)
	except OSError:
		pass
	marime = sum(os.path.getsize(os.path.join(director, f)) for f in fisiere)
	liber = _loc_liber(dosar)
	if liber is not None and liber < marime // 3 + LOC_MINIM:
		_curata_copii(dosar, 1)
		liber = _loc_liber(dosar)
		if liber is not None and liber < marime // 3 + LOC_MINIM:
			raise Eroare(_t("Nu e loc pentru copia de siguranță a listei. Nu s-a salvat nimic."))
	acum = time.time()
	id_ = time.strftime("%Y%m%d-%H%M%S", time.localtime(acum))
	k = 2
	while os.path.exists(os.path.join(dosar, id_ + ".tar.gz")):
		id_ = time.strftime("%Y%m%d-%H%M%S", time.localtime(acum)) + "-%d" % k
		k += 1
	cale = os.path.join(dosar, id_ + ".tar.gz")
	nou = cale + ".nou"
	try:
		with tarfile.open(nou, "w:gz", compresslevel=6) as t:
			for f in fisiere:
				t.add(os.path.join(director, f), arcname=f, recursive=False)
		with open(nou, "r+b") as f:
			os.fsync(f.fileno())
		os.replace(nou, cale)
	except Exception:
		try:
			os.remove(nou)
		except OSError:
			pass
		raise
	servicii = 0
	try:
		with open(os.path.join(director, "lamedb"), "rb") as f:
			servicii = len(D.citeste_lamedb(f.read()).servicii)
	except Exception:
		pass
	info = {"cand": acum, "descriere": descriere, "cine": cine, "servicii": servicii,
		"buchete": sum(1 for f in fisiere if f.startswith(PREFIXE_COPIE)), "fisiere": fisiere}
	_scrie_sigur(os.path.join(dosar, id_ + ".json"), json.dumps(info, ensure_ascii=False).encode("utf-8"))
	_curata_copii(dosar, 0)
	return Copie(id_, acum, descriere, os.path.getsize(cale), cine, servicii, info["buchete"])


def _curata_copii(dosar, in_plus):
	ids = sorted(f[:-7] for f in os.listdir(dosar) if f.endswith(".tar.gz"))
	while len(ids) > max(1, MAX_COPII - in_plus):
		v = ids.pop(0)
		for coada in (".tar.gz", ".json"):
			try:
				os.remove(os.path.join(dosar, v + coada))
			except OSError:
				pass


def lista_copii(director=DIRECTOR):
	dosar = _dosar_copii(director)
	try:
		nume = os.listdir(dosar)
	except OSError:
		return []
	rez = []
	for f in nume:
		if not f.endswith(".tar.gz"):
			continue
		id_ = f[:-7]
		info = {}
		try:
			with open(os.path.join(dosar, id_ + ".json"), "rb") as g:
				info = json.loads(g.read().decode("utf-8"))
		except Exception:
			pass
		try:
			marime = os.path.getsize(os.path.join(dosar, f))
		except OSError:
			continue
		rez.append(Copie(id_, info.get("cand") or os.path.getmtime(os.path.join(dosar, f)), info.get("descriere", ""),
			marime, info.get("cine", ""), info.get("servicii", 0), info.get("buchete", 0)))
	rez.sort(key=lambda c: c.id, reverse=True)
	return rez


def buchet_automat(buchet_id):
	"""Textul pentru om cand buchetul e refacut de alt modul al imaginii (BUCHETE_AUTOMATE), altfel ""."""
	fel = BUCHETE_AUTOMATE.get(buchet_id)
	if fel == "dabt2":
		return _t("Buchetul e refăcut de căutarea DAB+ / DVB-T2 din satelit: schimbările făcute aici se pot pierde "
			"la următoarea căutare.")
	if fel == "dvbi":
		return _t("Buchetul e refăcut automat cu canalele de pe internet (DVB-I): schimbările făcute aici se pot "
			"pierde.")
	if fel == "scanare":
		return _t("Buchetul e rescris la fiecare scanare: schimbările făcute aici se pierd la următoarea scanare.")
	return ""


def citeste_copia(copie_id, director=DIRECTOR):
	"""Fisierele unei copii de siguranta citite intr-un Date (despachetate intr-un dosar temporar, sters dupa)."""
	if not _id_bun(copie_id):
		raise Eroare(_t("Copia nu mai există."))
	dosar = _dosar_copii(director)
	cale = os.path.join(dosar, copie_id + ".tar.gz")
	if not os.path.exists(cale):
		raise Eroare(_t("Copia nu mai există."))
	tmp = os.path.join(dosar, ".comparare")
	shutil.rmtree(tmp, True)
	os.makedirs(tmp)
	try:
		despacheteaza(cale, tmp)
		return D.citeste_dosar(tmp, sateliti=os.path.join(tmp, "satellites.xml"))
	finally:
		shutil.rmtree(tmp, True)


def _id_bun(copie_id):
	return bool(copie_id) and all(c.isdigit() or c == "-" for c in copie_id) and len(copie_id) < 40


def despacheteaza(cale, dest):
	"""Numai fisierele de lista (fara cai, fara legaturi) din arhiva in dest."""
	with tarfile.open(cale, "r:*") as t:
		for m in t.getmembers():
			nume = os.path.basename(m.name)
			if not m.isfile() or nume != m.name.lstrip("./"):
				continue
			if not (nume in FISIERE_COPIE or nume.startswith(PREFIXE_COPIE)):
				continue
			f = t.extractfile(m)
			with open(os.path.join(dest, nume), "wb") as g:
				g.write(f.read())


def pregateste_intoarcerea(copie_id, memorie, director=DIRECTOR, cine=""):
	"""Copia de acum, apoi fisierele copiei puse in locul celor de acum (si cele de lista care nu sunt in copie,
	sterse). -> plan pentru Nucleu.aplica."""
	if not _id_bun(copie_id):
		raise Eroare(_t("Copia nu mai există."))
	dosar = _dosar_copii(director)
	cale = os.path.join(dosar, copie_id + ".tar.gz")
	if not os.path.exists(cale):
		raise Eroare(_t("Copia nu mai există."))
	tmp = os.path.join(dosar, ".intoarcere")
	shutil.rmtree(tmp, True)
	os.makedirs(tmp)
	try:
		despacheteaza(cale, tmp)
		with open(os.path.join(tmp, "lamedb"), "rb") as f:
			db = D.citeste_lamedb(f.read())
		fa_copie(director, _t("înainte de întoarcerea la copia din %s") % copie_id, cine)
		din_copie = set(os.listdir(tmp))
		for f in _fisiere_de_copiat(director):
			if f not in din_copie and f != "lamedb5":
				try:
					os.remove(os.path.join(director, f))
				except OSError:
					pass
		for f in sorted(din_copie, key=lambda x: x == "lamedb"):
			with open(os.path.join(tmp, f), "rb") as g:
				_scrie_sigur(os.path.join(director, f), g.read())
	finally:
		shutil.rmtree(tmp, True)
	de_scos, tp_de_scos = [], []
	if memorie:
		try:
			mem = D.citeste_lamedb(memorie)
		except D.Stricat:
			mem = None
		if mem is not None:
			for k5, s in mem.servicii.items():
				n = db.servicii.get(k5)
				if n is None or n.nume != s.nume or n.date != s.date:
					de_scos.append(s.ref)
			for k, t in mem.transpondere.items():
				if k not in db.transpondere:
					p = t.poz
					tp_de_scos.append((t.ns, t.tsid, t.onid, p if isinstance(p, int) else 0))
	c = [x for x in lista_copii(director) if x.id == copie_id]
	return {"de_scos": de_scos, "tp_de_scos": tp_de_scos, "copie": c[0] if c else Copie(copie_id, time.time())}
