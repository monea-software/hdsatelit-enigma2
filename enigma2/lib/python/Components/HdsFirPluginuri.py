# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsFirPluginuri.py: pluginurile altora care isi fac buchetele pe firul principal al interfetei (JediMakerXtream al
# lui KiddaC; Bouquet Maker Xtream pregatit, nelegat inca) le fac aici pe un fir de lucru; interfata raspunde la taste
# cat se fac.
#
# De ce: in Enigma2 desenarea, tastele, ceasurile (eTimer) si interfata web merg toate pe firul principal. Pluginurile
# de mai sus descarca lista IPTV, o parcurg si scriu buchetele chiar in pasii lor (ceasuri eTimer de 10-50 ms legate unul
# de altul), deci cu o lista mare interfata nu raspunde zeci de secunde sau minute (raportul 388460: firul principal la
# 97%, JediMakerXtream process_category si refreshBouquets). Codul care atinge ecranele, eTimer sau eDVBDB din alt fir
# poate darama interfata, deci nu se muta orbeste nimic: numai pasii stiuti ai versiunilor verificate.
#
# Cum:
#   - RETETE: pentru fiecare ecran al unui plugin, modulul, clasa, pasii grei (descarcare, parcurgere, scriere de
#     fisiere) si amprenta fisierelor in care ruleaza codul lor (sha256, primele 16 cifre), cate una pe versiune
#     verificata. Alta amprenta (alta versiune, fisier schimbat, numai .pyc): pluginul ramane exact cum e, cu un rand in
#     jurnal care da amprenta (ca sa poata fi adaugata dupa verificare).
#   - legarea se face cand pluginul isi importa singur modulul ecranului (un cautator in sys.meta_path, pus de
#     PluginComponent.readPluginList prin instaleaza()); nimic nu se importa inainte. Pasii din reteta se inlocuiesc in
#     clasa cu o intrare: chemata pe firul principal (din ceasul pluginului), porneste pasul original pe un fir de lucru,
#     cu un „self” inlocuitor (_EcranFir), si se intoarce pe loc.
#   - pe firul de lucru ruleaza NUMAI corpul pasilor din reteta (si functiile modulelor chemate de ei). Orice altceva prin
#     „self” trece pe firul principal: self["eticheta"].setText/setValue/setRange (fara asteptare, in ordine),
#     self.session.* si orice alta metoda a ecranului (cu asteptare: firul de lucru primeste rezultatul sau exceptia),
#     self.nextjob/nextJob (pastrate pana la sfarsitul pasului, apoi chemate in ordine pe firul principal: ceasul
#     urmatorului pas nu poate porni in mijlocul celui de acum, ca in plugin). Functiile modulelor care ating eDVBDB
#     (refreshBouquets) sunt inlocuite: chemate de pe firul de lucru, ruleaza pe firul principal si se asteapta.
#   - intoarcerea pe firul principal: un eTimer (PAS_POMPA_MS) facut pe firul principal cat ruleaza un pas, care goleste
#     coada si vede cand pasul s-a terminat. Niciun eTimer nu se face pe firul de lucru.
#   - un singur pas odata pe plugin: o intrare venita cat ruleaza un pas (alt ceas, sau alt ecran al aceluiasi plugin,
#     deschis dupa un EXIT cat pasul celui inchis inca lucra) asteapta sfarsitul lui, ca in plugin, unde pasii nu se
#     puteau suprapune.
#   - o exceptie a pluginului se ridica din nou pe firul principal, din ceasul nostru, cu stiva ei (in plugin), deci
#     Components/HdsPluginExtern.trateaza o vede ca pana acum. Ecranul inchis (EXIT) in timpul pasului: ce cere pasul de
#     la ecran dupa inchidere se opreste (_Oprit), fara raport; un buchet inceput se termina de scris.
#   - „cade inapoi” se hotaraste inainte de pas, niciodata la jumatatea lui: o greseala a stratului nostru la pornirea
#     unui pas ruleaza pasul original pe firul principal si opreste protectia pana la repornirea interfetei.
#   - firul de lucru are aceeasi prioritate ca firul principal (NICE_FIR = 0, fara renice): pe .122 (11.11.2026) nice 10
#     n-a schimbat nimic masurabil (cea mai lunga oprire 0,75 s fata de 0,83 s), deci nu se mai atinge prioritatea.
#     GIL-ul se imparte la 5 ms, deci firul principal mai asteapta cate putin cat pasul face Python greu, dar nu mai sta
#     pe loc.
#   - jurnal: un rand la legare, un rand la primul pas al fiecarui ecran si un rand la inchiderea lui (pasi, timpul
#     firului de lucru, cel mai lung pas).
#
# Ce nu muta: eDVBDB.reloadServicelist/reloadBouquets (refreshBouquets de la sfarsit) raman pe firul principal, cat ar
# tine la orice imagine; pentru ele ramane plasa paznicului (Components/HdsPaznic.py, punctul 9). Pasii care fac eTimer
# singuri (JediMakerXtream_Update.checkactive, BMX start/_scheduleSeriesChunk) raman pe firul principal.
# Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC il folosesc direct.

import hashlib
import os
import sys
import threading
import time
from collections import deque

PAS_POMPA_MS = 20               # cat de des se uita firul principal la coada cat ruleaza un pas
NICE_FIR = 0                    # prioritatea firului de lucru (0 = ca firul principal; vezi capul fisierului)
ASTEPTARE_PAS_S = 0.5           # firul de lucru asteapta raspunsul firului principal in bucati de atat (verifica inchiderea)
# Cat ruleaza un pas, GIL-ul se preda la 1 ms in loc de 5 ms (sys.setswitchinterval, pus la loc dupa pas). De ce: codul de
# pe firul principal care face multe apeluri scurte de sistem (HdsAfisajCompat._procese citeste /proc, indexul canalelor
# citeste fisiere) isi recapata GIL-ul dupa fiecare apel abia dupa intervalul acesta, cat firul de lucru tine procesorul.
SCHIMB_GIL_S = 0.001

# numele care nu au voie sa apara in codul unui pas mutat (le foloseste numai firul principal)
INTERZISE = frozenset(("eTimer", "eDVBDB", "eConsoleAppContainer", "quitMainloop", "eActionMap", "ePicLoad"))
# metodele componentelor ecranului chemate fara asteptare (nu intorc nimic folosit)
FARA_ASTEPTARE = frozenset(("setText", "setValue", "setRange", "show", "hide", "setPixmapNum", "setBoolean"))
# metodele ecranului care pun urmatorul pas: pastrate pana la sfarsitul pasului
LA_SFARSIT = frozenset(("nextjob", "nextJob"))


def _jurnal(text):
	print("[HdsFirPluginuri] %s" % text)


class Reteta(object):
	"""Un ecran al unui plugin: pasii mutati pe firul de lucru si versiunile verificate."""

	def __init__(self, plugin, modul, clasa, pasi, fisiere, amprente, principal=(), ajutatoare=()):
		self.plugin = plugin            # numele dosarului pluginului (pentru jurnal)
		self.modul = modul              # modulul ecranului, numele intreg
		self.clasa = clasa
		self.pasi = frozenset(pasi)
		# metode chemate si de pasi, si de metode ramase pe firul principal: dintr-un pas ruleaza pe loc, pe firul de
		# lucru; de pe firul principal raman exact ca in plugin (clasa nu se schimba pentru ele)
		self.ajutatoare = frozenset(ajutatoare)
		self.fisiere = tuple(fisiere)   # fisierele din dosarul pluginului care intra in amprenta, in ordinea asta
		self.amprente = dict(amprente)  # amprenta -> versiunea verificata
		self.principal = tuple(principal)   # (submodul, functie): functii care raman pe firul principal

	@property
	def pachet(self):
		return self.modul.rsplit(".", 1)[0]


_JMX_FISIERE = ("globalfunctions.py", "downloads.py", "buildxml.py")
_JMX_PRINCIPAL = (("globalfunctions", "refreshBouquets"),)

RETETE = (
	# JediMakerXtream 6.32 si 6.37 (Maintainer: kiddac; pachetele din oglinda publica, autorul a scos depozitul):
	# buildbouquet.py la fel in amandoua (in afara de pauza, 5 / 10 ms)
	Reteta("JediMakerXtream", "Plugins.Extensions.JediMakerXtream.buildbouquet", "JediMakerXtream_BuildBouquets",
		pasi=("downloadrytec", "downloadLive", "downloadVod", "downloadSeries", "downloadgetfile", "deleteBouquets",
			"buildBouquets", "process_category", "buildM3uBouquets", "m3u_process_category"),
		fisiere=("buildbouquet.py",) + _JMX_FISIERE,
		amprente={"9ed584f4a98f7bf6": "6.32", "6dfc44ddd30be3ff": "6.37"},
		principal=_JMX_PRINCIPAL),
	# actualizarea buchetelor (din meniu si automata, la ora aleasa: plugin.py o deschide singur)
	Reteta("JediMakerXtream", "Plugins.Extensions.JediMakerXtream.update", "JediMakerXtream_Update",
		pasi=("downloadrytec", "downloadLive", "downloadVod", "downloadSeries", "getM3uCategories", "downloadgetfile",
			"deleteBouquets", "buildBouquets", "process_category", "buildM3uBouquets", "m3u_process_category",
			"updateBouquetJsonFile"),
		fisiere=("update.py",) + _JMX_FISIERE,
		amprente={"29964ab32d8c04c7": "6.32", "7cc345ee041d946a": "6.37"},
		principal=_JMX_PRINCIPAL),
	# Bouquet Maker Xtream 1.82-20261108 (github.com/kiddac/Bouquet_Maker_Xtream, cad9baaaf): numai caile rulate in proba
	# de PC (xtream live si VOD, lista M3U externa), alese dupa graful apelurilor. Serialele (downloadXtreamSeries,
	# loadSeries, processSeriesChunk ... createSeriesBouquets), lista locala (parseLocal), finished, exit, start, nextJob,
	# _scheduleSeriesChunk si updateJson raman pe firul principal, ca in plugin. Ajutatoarele (parsarea M3U, XMLTV,
	# bouquets.tv grupat, clearCaches: trei os.system „echo N > /proc/sys/vm/drop_caches”) ruleaza pe fir numai cand le
	# cheama un pas mutat; chemate din finished() sau din seriale raman pe firul principal, deci calea serialelor ramane
	# neschimbata.
	Reteta("BouquetMakerXtream", "Plugins.Extensions.BouquetMakerXtream.buildbouquets", "BmxBuildBouquets",
		pasi=("downloadXtreamLive", "downloadXtreamVod", "downloadExternal", "loadLive", "loadVod"),
		ajutatoare=("parseFullM3u8Data", "buildXmltvSource", "buildXmltvChannels", "buildBouquetTvGroupedFile",
			"clearCaches"),
		fisiere=("buildbouquets.py", "globalfunctions.py", "parsem3u.py", "seriesparsem3u.py", "bouquetorder.py"),
		amprente={"f96938ba9a3a231e": "1.82"},
		principal=(("globalfunctions", "refreshBouquets"),)),
)

_activ = [True]                 # False dupa o greseala a stratului nostru: pana la repornirea interfetei, nimic mutat
# plugin -> _Lucrator-ul care a pornit ultimul pas: un singur fir viu pe plugin (ecranele lui impart variabilele
# modulelor si bouquets.tv; un ecran inchis cu EXIT in mijlocul unui pas isi termina pasul cat altul se deschide)
_firePlugin = {}
_gil = {"pasi": 0, "vechi": None}     # pasii care ruleaza acum (toate pluginurile) si intervalul GIL de dinainte


def _incepePas():
	"""Pe firul principal, la pornirea unui pas: primul pas coboara intervalul de predare a GIL-ului."""
	if _gil["pasi"] == 0 and SCHIMB_GIL_S:
		try:
			vechi = sys.getswitchinterval()
			if SCHIMB_GIL_S < vechi:
				sys.setswitchinterval(SCHIMB_GIL_S)
				_gil["vechi"] = vechi
		except Exception:
			_gil["vechi"] = None
	_gil["pasi"] += 1


def _terminaPas():
	"""Pe firul principal, dupa un pas: ultimul pune intervalul la loc."""
	_gil["pasi"] = max(0, _gil["pasi"] - 1)
	if _gil["pasi"] == 0 and _gil["vechi"] is not None:
		try:
			sys.setswitchinterval(_gil["vechi"])
		except Exception:
			pass
		_gil["vechi"] = None
_legate = {}                    # (modul, clasa) -> versiunea, sau None (neverificata / refuzata)
_local = threading.local()      # .lucru: _Lucrator al pasului care ruleaza pe acest fir


class _Oprit(BaseException):
	"""Ecranul s-a inchis cat rula pasul: ce mai cere pasul de la ecran se opreste aici."""


def _lucruCurent():
	return getattr(_local, "lucru", None)


def _pePrincipal():
	return threading.current_thread() is threading.main_thread()


# ---------------------------------------------------------------- amprenta si verificarea codului

def amprenta(dosar, fisiere):
	"""Primele 16 cifre sha256 peste (nume, continut) ale fisierelor, in ordine; None daca lipseste unul."""
	h = hashlib.sha256()
	for nume in fisiere:
		try:
			with open(os.path.join(dosar, nume), "rb") as f:
				continut = f.read()
		except (IOError, OSError):
			return None
		h.update(nume.encode("utf-8") + b"\0" + continut + b"\0")
	return h.hexdigest()[:16]


def _numeCod(cod, adancime=8):
	"""Numele globale si atributele folosite de un cod, cu functiile lui interioare."""
	nume = set(cod.co_names)
	if adancime > 0:
		for c in cod.co_consts:
			if hasattr(c, "co_names"):
				nume |= _numeCod(c, adancime - 1)
	return nume


def verificaPasi(clasa, pasi):
	"""Lista problemelor (gol = bine): fiecare pas e o functie a clasei si nu foloseste nimic din INTERZISE."""
	probleme = []
	for nume in sorted(pasi):
		f = clasa.__dict__.get(nume)
		f = getattr(f, "_hds_fir", f)
		cod = getattr(f, "__code__", None)
		if cod is None:
			probleme.append("%s lipseste" % nume)
			continue
		rele = _numeCod(cod) & INTERZISE
		if rele:
			probleme.append("%s foloseste %s" % (nume, ",".join(sorted(rele))))
	return probleme


# ---------------------------------------------------------------- legarea

def lega(reteta, modul, radacina_fisiere=None):
	"""Leaga reteta de modulul importat. -> versiunea legata, sau None (pluginul ramane cum e)."""
	cheie = (reteta.modul, reteta.clasa)
	if cheie in _legate:
		return _legate[cheie]
	_legate[cheie] = None
	clasa = getattr(modul, reteta.clasa, None)
	if clasa is None:
		_jurnal("%s: clasa %s lipseste, ramane cum e" % (reteta.plugin, reteta.clasa))
		return None
	dosar = radacina_fisiere or os.path.dirname(getattr(modul, "__file__", "") or "")
	a = amprenta(dosar, reteta.fisiere)
	versiune = reteta.amprente.get(a)
	if versiune is None:
		_jurnal("%s %s: versiune neverificata (amprenta %s), ramane cum e" % (reteta.plugin, reteta.clasa, a))
		return None
	probleme = verificaPasi(clasa, reteta.pasi | reteta.ajutatoare)
	if probleme:
		_jurnal("%s %s %s: %s; ramane cum e" % (reteta.plugin, versiune, reteta.clasa, "; ".join(probleme)))
		return None
	inlocuite = []
	try:
		for sub, functie in reteta.principal:
			m = sys.modules.get(reteta.pachet + "." + sub)
			if m is None:
				__import__(reteta.pachet + "." + sub)
				m = sys.modules[reteta.pachet + "." + sub]
			orig = getattr(m, functie)
			if not getattr(orig, "_hds_fir", None):
				setattr(m, functie, _pePrincipalSiAsteapta(orig))
				inlocuite.append((m, functie, orig))
		for nume in reteta.pasi:
			orig = clasa.__dict__[nume]
			if getattr(orig, "_hds_fir", None):
				continue
			setattr(clasa, nume, _intrare(reteta, nume, orig))
			inlocuite.append((clasa, nume, orig))
	except Exception as e:
		for obiect, nume, orig in reversed(inlocuite):
			setattr(obiect, nume, orig)
		_jurnal("%s %s %s: legarea a cazut (%r); ramane cum e" % (reteta.plugin, versiune, reteta.clasa, e))
		return None
	_legate[cheie] = versiune
	_jurnal("%s %s: pasii grei ai %s merg pe un fir de lucru" % (reteta.plugin, versiune, reteta.clasa))
	return versiune


def _dupaImport(nume, modul):
	for r in RETETE:
		if r.modul == nume:
			try:
				lega(r, modul)
			except Exception as e:
				_jurnal("%s: %r" % (r.plugin, e))


class _Incarcator(object):
	"""Incarcatorul adevarat al modulului, plus legarea dupa ce modulul s-a executat."""

	def __init__(self, incarcator, nume):
		self._incarcator = incarcator
		self._nume = nume

	def create_module(self, spec):
		return self._incarcator.create_module(spec)

	def exec_module(self, modul):
		self._incarcator.exec_module(modul)
		_dupaImport(self._nume, modul)

	def __getattr__(self, nume):
		return getattr(self._incarcator, nume)


class _Cautator(object):
	"""In sys.meta_path: pentru modulele din RETETE ia specificatia de la ceilalti cautatori si ii pune _Incarcator."""

	def __init__(self):
		self.nume = frozenset(r.modul for r in RETETE)

	def find_spec(self, nume, cale=None, tinta=None):
		if nume not in self.nume or getattr(_local, "caut", False):
			return None
		_local.caut = True
		try:
			for c in sys.meta_path:
				if c is self or not hasattr(c, "find_spec"):
					continue
				spec = c.find_spec(nume, cale, tinta)
				if spec is not None:
					break
			else:
				return None
		finally:
			_local.caut = False
		if spec.loader is None or not hasattr(spec.loader, "exec_module"):
			return None
		spec.loader = _Incarcator(spec.loader, nume)
		return spec


_cautator = [None]


def instaleaza():
	"""Din PluginComponent.readPluginList; de cate ori e chemat, o singura data. Nu arunca."""
	try:
		if _cautator[0] is None:
			_cautator[0] = _Cautator()
			sys.meta_path.insert(0, _cautator[0])
		for r in RETETE:
			m = sys.modules.get(r.modul)
			if m is not None:
				_dupaImport(r.modul, m)
	except Exception as e:
		_jurnal("instalarea: %r" % (e,))


# ---------------------------------------------------------------- firul de lucru

def _pePrincipalSiAsteapta(functie):
	"""Functia unui modul care atinge eDVBDB: de pe firul de lucru ruleaza pe firul principal si se asteapta."""
	def peFirulPrincipal(*a, **k):
		lucru = _lucruCurent()
		if lucru is None:
			return functie(*a, **k)
		return lucru.trimite(functie, a, k, True)
	peFirulPrincipal._hds_fir = functie
	peFirulPrincipal.__name__ = getattr(functie, "__name__", "functie")
	peFirulPrincipal.__doc__ = getattr(functie, "__doc__", None)
	return peFirulPrincipal


def _intrare(reteta, nume, orig):
	def intrare(self, *a, **k):
		lucru = _lucruCurent()
		if lucru is not None:       # chemat cu ecranul adevarat de pe firul de lucru: ramane pe el
			return orig(lucru.proxy if lucru.ecran is self else self, *a, **k)
		if not _activ[0] or not _pePrincipal():
			return orig(self, *a, **k)
		try:
			l = _Lucrator.al(self, reteta)
		except Exception as e:
			_opreste("pornirea pasului %s: %r" % (nume, e))
			return orig(self, *a, **k)
		return l.cere(nume, orig, a, k)
	intrare._hds_fir = orig
	intrare.__name__ = getattr(orig, "__name__", nume)
	intrare.__doc__ = getattr(orig, "__doc__", None)
	return intrare


def _opreste(motiv):
	if _activ[0]:
		_activ[0] = False
		_jurnal("%s; pana la repornirea interfetei pluginurile raman cum sunt" % motiv)


def _faCeas(functie):
	"""(ceasul, legatura): legatura trebuie tinuta cat ceasul (fara ea, connect se desface)."""
	from enigma import eTimer
	t = eTimer()
	try:
		legatura = t.timeout.connect(functie)
	except AttributeError:
		t.callback.append(functie)
		legatura = None
	return t, legatura


class _Pas(object):
	"""Un pas din reteta luat prin _EcranFir (de pilda dat lui nextjob): pe firul principal porneste pasul pe firul de
	lucru, pe firul de lucru ruleaza pe loc."""

	def __init__(self, lucrator, nume, orig):
		self._l = lucrator
		self._nume = nume
		self._orig = orig

	def __call__(self, *a, **k):
		l = self._l
		if _lucruCurent() is l:
			return self._orig(l.proxy, *a, **k)
		if _pePrincipal():
			if _activ[0]:
				return l.cere(self._nume, self._orig, a, k)
			return self._orig(l.ecran, *a, **k)
		return self._orig(l.proxy, *a, **k)     # un fir pornit chiar de pas: tot prin „self”-ul inlocuitor


class _PeFirulPrincipal(object):
	"""Un obiect al firului principal (o componenta a ecranului, sesiunea) vazut de pe firul de lucru."""

	def __init__(self, lucrator, obiect, fara=frozenset()):
		self._l = lucrator
		self._o = obiect
		self._fara = fara

	def __getattr__(self, nume):
		self._l.verificaInchis()
		v = getattr(self._o, nume)
		if not callable(v):
			return v
		l = self._l
		asteapta = nume not in self._fara
		return lambda *a, **k: l.trimite(v, a, k, asteapta)

	def __getitem__(self, cheie):
		return self._l.trimite(self._o.__getitem__, (cheie,), {}, True)

	def __call__(self, *a, **k):
		return self._l.trimite(self._o, a, k, True)


class _EcranFir(object):
	"""„self”-ul pasilor mutati: datele ecranului direct, tot ce atinge interfata pe firul principal."""

	__slots__ = ("_e", "_l")

	def __init__(self, ecran, lucrator):
		object.__setattr__(self, "_e", ecran)
		object.__setattr__(self, "_l", lucrator)

	def __getattr__(self, nume):
		e = object.__getattribute__(self, "_e")
		l = object.__getattribute__(self, "_l")
		l.verificaInchis()
		if nume in l.reteta.pasi:
			f = type(e).__dict__.get(nume)
			return _Pas(l, nume, getattr(f, "_hds_fir", f))
		if nume in l.reteta.ajutatoare:
			f = type(e).__dict__.get(nume)
			proxy = l.proxy
			return lambda *a, **k: f(proxy, *a, **k)
		if nume == "session":
			return _PeFirulPrincipal(l, e.session)
		v = getattr(e, nume)
		if nume in LA_SFARSIT:
			return lambda *a, **k: l.laSfarsitulPasului(v, a, k)
		if callable(v) and getattr(v, "__self__", None) is e:
			return lambda *a, **k: l.trimite(v, a, k, True)
		return v

	def __setattr__(self, nume, valoare):
		l = object.__getattribute__(self, "_l")
		l.verificaInchis()
		setattr(object.__getattribute__(self, "_e"), nume, valoare)

	def __getitem__(self, cheie):
		l = object.__getattribute__(self, "_l")
		l.verificaInchis()
		return _PeFirulPrincipal(l, object.__getattribute__(self, "_e")[cheie], FARA_ASTEPTARE)

	def __setitem__(self, cheie, valoare):
		l = object.__getattribute__(self, "_l")
		l.trimite(object.__getattribute__(self, "_e").__setitem__, (cheie, valoare), {}, True)

	def __contains__(self, cheie):
		return cheie in object.__getattribute__(self, "_e")


class _Lucrator(object):
	"""Pasii unui ecran pe firul de lucru: unul odata, cu coada spre firul principal."""

	@classmethod
	def al(cls, ecran, reteta):
		l = ecran.__dict__.get("_hdsFirLucrator")
		if l is None:
			l = cls(ecran, reteta)
			ecran.__dict__["_hdsFirLucrator"] = l
		return l

	def __init__(self, ecran, reteta):
		self.ecran = ecran
		self.reteta = reteta
		self.proxy = _EcranFir(ecran, self)
		self.fir = None
		self.exceptie = None
		self.coada = deque()        # (functie, a, k, eveniment sau None, cutie)
		self.laSfarsit = []         # nextjob/nextJob ale pasului de acum
		self.amanate = []           # intrari venite cat rula un pas
		self.inchis = False
		self.ceas, self.legatura = _faCeas(self._pompa)
		self.pasi = 0
		self.timpFir = 0.0
		self.celMaiLung = (0.0, "")
		self.inceput = 0.0
		self.numePas = ""
		onClose = getattr(ecran, "onClose", None)
		if onClose is not None:
			onClose.append(self._laInchidere)

	# -- pe firul principal
	def _altViu(self):
		"""True cat un pas al altui ecran al aceluiasi plugin inca ruleaza pe firul lui."""
		alt = _firePlugin.get(self.reteta.plugin)
		return alt is not None and alt is not self and alt.fir is not None and alt.fir.is_alive()

	def cere(self, nume, orig, a, k):
		if self.inchis:
			return None
		if self.fir is not None or self._altViu():
			self.amanate.append((nume, orig, a, k))
			if self.fir is None:        # asteapta firul celuilalt ecran: pompa se uita la el
				self.ceas.start(PAS_POMPA_MS, False)
			return None
		if not self.pasi:
			_jurnal("%s: %s pe firul de lucru" % (self.reteta.clasa, nume))
		self.exceptie = None
		self.numePas = nume
		self.inceput = time.monotonic()
		try:
			fir = threading.Thread(target=self._ruleaza, args=(orig, a, k), name="HdsFirPlugin")
			fir.daemon = True
			self.fir = fir
			_firePlugin[self.reteta.plugin] = self
			_incepePas()
			try:
				fir.start()
			except Exception:
				_terminaPas()
				raise
			self.ceas.start(PAS_POMPA_MS, False)
		except Exception as e:      # inainte sa ruleze ceva din pas: pasul pe firul principal, ca in plugin
			self.fir = None
			_opreste("firul de lucru nu porneste (%r)" % (e,))
			return orig(self.ecran, *a, **k)
		return None

	def _goleste(self):
		while self.coada:
			functie, a, k, ev, cutie = self.coada.popleft()
			if not self.inchis:
				try:
					cutie[0] = functie(*a, **k)
				except BaseException as e:
					if ev is None:
						raise
					cutie[1] = e
			if ev is not None:
				ev.set()

	def _pompa(self):
		self._goleste()
		fir = self.fir
		if fir is None:                 # niciun pas al nostru: poate asteptam firul altui ecran al pluginului
			if self.inchis or not self.amanate:
				self.amanate = []
				self.ceas.stop()
			elif not self._altViu():
				self.ceas.stop()
				amanate, self.amanate = self.amanate, []
				for nume, orig, a, k in amanate:
					self.cere(nume, orig, a, k)
			return
		if fir.is_alive():
			return
		fir.join()
		self.fir = None
		_terminaPas()
		self._goleste()
		durata = time.monotonic() - self.inceput
		self.pasi += 1
		self.timpFir += durata
		if durata > self.celMaiLung[0]:
			self.celMaiLung = (durata, self.numePas)
		exceptie, self.exceptie = self.exceptie, None
		laSfarsit, self.laSfarsit = self.laSfarsit, []
		amanate, self.amanate = self.amanate, []
		if self.inchis:
			self.ceas.stop()
			return
		self.ceas.stop()
		for functie, a, k in laSfarsit:
			functie(*a, **k)
		if exceptie is not None:
			raise exceptie
		for nume, orig, a, k in amanate:
			self.cere(nume, orig, a, k)

	def _laInchidere(self):
		if self.inchis:
			return
		self.inchis = True
		self.amanate = []
		self.laSfarsit = []
		if self.pasi or self.fir is not None:
			_jurnal("%s inchis: %d pasi pe firul de lucru, %.1f s, cel mai lung %s %.1f s%s"
				% (self.reteta.clasa, self.pasi, self.timpFir, self.celMaiLung[1], self.celMaiLung[0],
				", un pas inca lucreaza" if self.fir is not None else ""))

	# -- pe firul de lucru
	def _ruleaza(self, orig, a, k):
		_local.lucru = self
		if NICE_FIR:
			try:
				os.setpriority(os.PRIO_PROCESS, threading.get_native_id(), NICE_FIR)
			except Exception:
				pass
		try:
			orig(self.proxy, *a, **k)
		except _Oprit:
			pass
		except BaseException as e:
			if not self.inchis:
				self.exceptie = e
		finally:
			_local.lucru = None

	def verificaInchis(self):
		if self.inchis and _lucruCurent() is self:
			raise _Oprit()

	def trimite(self, functie, a, k, asteapta):
		if _pePrincipal():
			return functie(*a, **k)
		# firul de lucru, sau un fir pornit chiar de pas (ThreadPool): tot pe firul principal
		self.verificaInchis()
		if not asteapta:
			self.coada.append((functie, a, k, None, [None, None]))
			return None
		ev = threading.Event()
		cutie = [None, None]
		self.coada.append((functie, a, k, ev, cutie))
		while not ev.wait(ASTEPTARE_PAS_S):
			if self.fir is None:    # un fir ramas dupa sfarsitul pasului: nimeni nu mai goleste coada
				return None
		self.verificaInchis()
		if cutie[1] is not None:
			raise cutie[1]
		return cutie[0]

	def laSfarsitulPasului(self, functie, a, k):
		self.verificaInchis()
		self.laSfarsit.append((functie, a, k))
