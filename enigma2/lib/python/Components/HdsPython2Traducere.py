# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Traducatorul pluginurilor scrise in Python 2 (0.7.4, Eduard 12.11.2026 04:51): un plugin extern care nu se incarca numai
fiindca e scris in Python 2 (print fara paranteze, except X, e, 0777, ur'', <>, `x`, has_key, iteritems, xrange, unicode,
urllib2, cPickle, StringIO, importuri relative implicite, taburi amestecate cu spatii ...) se traduce in Python 3 la incarcare,
o singura data, apoi se incarca din nou, fara repornirea interfetei.

Cand: Components/PluginComponent.py, la importul unui plugin cazut (incearca()). Semnele (semnPython2): o eroare de sintaxa intr-un
fisier al pluginului, un import al unui modul vecin din acelasi plugin fara punct (importul relativ implicit), un import al unui
modul care exista numai in Python 2 (HdsPython2.MODULE_PY2), un nume vechi negasit (unicode, xrange ...). Pluginurile imaginii nu se
ating niciodata (HdsPluginExtern.PLUGINURI_IMAGINE).

Cum:
  - motorul: fissix (continuarea lui lib2to3, scos din Python 3.13; licenta PSF), cu fixerele obisnuite ale lui 2to3, fara cele
    optionale (idioms, buffer, set_literal, ws_comma), plus doua ale noastre: impartirea lui Python 2 (a / b intre numere intregi
    = impartire intreaga; hds_py2_div, numai fara `from __future__ import division`) si `from .__init__ import` -> `from . import`.
    Motorul nu e in imagine (imaginea mica): e pachetul python3-fissix din feedul nostru; cand lipseste, importul cade cu
    ModuleNotFoundError('fissix'), iar Components/HdsModuleLipsa.py il aduce singur si reciteste lista (planul obisnuit);
  - inainte de motor: taburile amestecate cu spatii la inceputul randurilor scrise numai cu spatii dupa regula lui Python 2 (un
    tab duce la urmatorul multiplu de 8), in afara sirurilor pe mai multe randuri (acelasi inteles; Python 3 refuza amestecul);
  - un fisier care se compileaza deja in Python 3 se traduce cu gramatica fara instructiunea print (print(a, b) ramane apel);
  - numele pe care traducerea nu le repara (cmp, file, coerce, impartirea) vin din Components/HdsPython2Compat.py, printr-un singur
    rand pus numai in fisierele traduse care le folosesc; Python-ul celorlalte pluginuri ramane neatins;
  - totul sau nimic: daca un fisier nu se poate traduce sau nu se compileaza dupa traducere, nu se scrie nimic; un fisier
    care nu se poate importa ca modul (plugin~.py, copia unui editor) si nu se traduce ramane cum e (CM3, importabil);
  - originalul ramane langa traducere (<nume>.py2); traducerea se tine minte dupa suma SHA-256 a fisierelor (STARE): un fisier
    deja tradus nu se traduce a doua oara; o actualizare a pluginului (opkg scrie din nou originalul) se traduce din nou;
  - in jurnal: "tradus din Python 2: <plugin>"; daca pluginul tot cade dupa traducere, raportul obisnuit al pluginurilor externe
    (Components/HdsPluginExtern.py), iar lista pluginurilor care nu se deschid spune "Tradus din Python 2; ...".
Ce nu se traduce (mesajul pentru om, fara cadere): plugin numai cu fisiere compilate (.pyo/.pyc de Python 2, fara sursa), module
native facute pentru Python 2 (le opreste deja Components/HdsAltPython.py), sursa care nu se poate citi nici ca Python 2. Un
modul nativ (.so) gasit, dar care nu se incarca (alt Python, un nume lipsa la dlopen) nu e semn de Python 2 (nativNeincarcat).

Nu importa nimic din enigma (probele de pe PC). RADACINA pune un dosar in fata caii STARE, numai la probe. Nu arunca din incearca()."""
import ast
import hashlib
import io
import json
import keyword
import os
import re
import stat
import sys
import threading
import time
try:
	import _thread as _fire_joase
except ImportError:  # pragma: no cover
	import thread as _fire_joase

# se mareste cand se schimba traducerea. Un plugin tradus cu o versiune mai veche care cade la import se traduce din nou din
# originale (incearca, traduceDosar). 2 (0.7.5, raportul 781623, pluginul Styles): un dosar fara __init__ nu mai e modul vecin
# (`from skin import loadSkin` ramane importul interfetei); plugin.py, __init__.py si fisierele `#!` importate de vecini sunt module
VERSIUNE = 2
RADACINA = ""
STARE = "/var/lib/hds-python2/traduse.json"
MOTOR = "fissix"
SUFIX_ORIGINAL = ".py2"
PRELUDIU = "from Components.HdsPython2Compat import *  # HDSatelit: tradus din Python 2"
MAX_FISIERE = 400                 # un plugin cu mai multe fisiere .py nu se traduce (timpul pe receptor)
MAX_OCTETI = 2 * 1024 * 1024      # un fisier .py mai mare nu se traduce
TIMP_MAXIM = 240.0                # secunde pentru un plugin (paza interfetei are 5 minute pe plugin, Components/HdsPaznic.py)

# fixerele optionale ale lui 2to3 (schimba stilul, nu sensul, sau pot gresi): nu se folosesc
_FARA = frozenset(("fix_idioms", "fix_buffer", "fix_set_literal", "ws_comma", "fix_ws_comma"))
# numele din Components/HdsPython2Compat.py: fisierul tradus care foloseste unul primeste PRELUDIU
NUME_COMPAT = frozenset(("cmp", "file", "coerce", "unicode", "basestring", "long", "xrange", "unichr", "raw_input", "reduce",
	"execfile", "reload", "intern", "apply", "buffer", "hds_py2_div", "hds_py2_idiv"))
# numele vechi care, negasite la import (NameError), arata cod de Python 2
_NUME_PY2 = NUME_COMPAT - frozenset(("hds_py2_div", "hds_py2_idiv"))
_ATRIBUTE_PY2 = re.compile(r"has no attribute '(has_key|iteritems|itervalues|iterkeys|letters|lowercase|uppercase|maxint|"
	r"getcwdu|izip|imap|ifilter|izip_longest|im_func|im_self|func_name|func_code|next)'")
_COOKIE = re.compile(br"^[ \t\f]*#.*?coding[:=][ \t]*([-\w.]+)")

# rezultatul unei traduceri (Rezultat.stare)
TRADUS = "tradus"                 # fisierele scrise, pluginul se incarca din nou
DEJA = "deja"                     # era deja tradus (nimic de facut)
NIMIC = "nimic"                   # nimic de schimbat (nu e cod de Python 2 pe care il stim traduce)
FARA_MOTOR = "fara_motor"         # pachetul python3-fissix lipseste
NETRADUS = "netradus"             # un fisier nu se poate traduce sigur (motiv: fisierul si randul)
COMPILAT = "compilat"             # numai fisiere compilate de Python 2, fara sursa
PREA_MARE = "prea_mare"


def _t(text):
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _jurnal(text):
	print("[HdsPython2Traducere] %s" % text)


def _c(cale):
	return RADACINA + cale if RADACINA else cale


class Rezultat(object):
	__slots__ = ("stare", "fisiere", "motiv", "secunde", "detalii")

	def __init__(self, stare, fisiere=0, motiv="", secunde=0.0, detalii=None):
		self.stare = stare
		self.fisiere = fisiere            # cate fisiere s-au scris (traduse)
		self.motiv = motiv                # textul tehnic (fisierul, randul, mesajul)
		self.secunde = secunde
		self.detalii = detalii or []

	def __repr__(self):
		return "Rezultat(%r, fisiere=%r, motiv=%r, secunde=%.2f)" % (self.stare, self.fisiere, self.motiv, self.secunde)


# ---------------------------------------------------------------- starea (ce s-a tradus)

def _citesteStare():
	try:
		with open(_c(STARE), "r", encoding="utf-8") as f:
			date = json.load(f)
		if isinstance(date, dict) and isinstance(date.get("pluginuri"), dict):
			if not isinstance(date.get("verificate"), dict):
				date["verificate"] = {}
			return date
	except (OSError, ValueError):
		pass
	return {"format": 1, "pluginuri": {}, "verificate": {}}


# HDSatelit 0.7.6 (FRZ): STARE se scrie si de pe firul verificarii din sursa (_lucreaza); scrierile trec prin lacat si fiecare fir are
# fisierul lui temporar (doua scrieri in acelasi .tmp ar fi lasat un JSON amestecat, iar toata starea s-ar fi pierdut)
# PLG 0.7.7: doua lacate. _lacatStare tine citirea, schimbarea si scrierea lui STARE (cu fsync pe memoria interna, sute de ms cand
# discul e ocupat); _lacat tine numai memoria procesului (coada firului, semnaturile, ce s-a tradus) si nu se tine niciodata in
# timpul unei citiri sau scrieri pe disc. Inainte un singur lacat: pompa (la 2 s pe firul interfetei), dupaImport si
# _cereVerificarea asteptau dupa fsync-ul progresului scris de firul de verificare la 5 s.
_lacat = threading.RLock()
_lacatStare = threading.RLock()


def _actualizeaza(schimba):
	"""citire, schimbare si scriere a STARE intr-un singur pas sub lacatul ei: schimba(stare) -> True cand e ceva de scris"""
	with _lacatStare:
		stare = _citesteStare()
		if schimba(stare):
			_scrieStare(stare)


def _scrieStare(date):
	cale = _c(STARE)
	with _lacatStare:
		_scrieFisierStare(cale, date)


def _scrieFisierStare(cale, date):
	try:
		os.makedirs(os.path.dirname(cale), exist_ok=True)
		tmp = "%s.tmp%d" % (cale, threading.get_ident())
		with open(tmp, "w", encoding="utf-8") as f:
			json.dump(date, f, ensure_ascii=False, indent=1, sort_keys=True)
			f.flush()
			os.fsync(f.fileno())
		os.replace(tmp, cale)
	except OSError as exc:
		_jurnal("starea nu s-a scris: %s" % exc)


def _cheie(cale):
	return os.path.normpath(cale).replace("\\", "/")


def _punePlugin(cheie, intrare_noua):
	def schimba(stare):
		stare["pluginuri"][cheie] = intrare_noua
		return True
	_actualizeaza(schimba)


def intrare(cale):
	"""ce stie STARE despre pluginul din dosarul cale (dict) sau None"""
	return _citesteStare()["pluginuri"].get(_cheie(cale))


def eTradus(cale):
	"""True daca pluginul din cale a fost tradus din Python 2 (pentru textul din lista pluginurilor care nu se deschid)"""
	e = intrare(cale)
	return bool(e and e.get("stare") == TRADUS)


def _suma(date):
	return hashlib.sha256(date).hexdigest()


# ---------------------------------------------------------------- semnele

def _lant(exc):
	vazute = []
	while exc is not None and exc not in vazute and len(vazute) < 8:
		vazute.append(exc)
		exc = exc.__cause__ or exc.__context__
	return vazute


# PY2 0.7.7 (asistenta 751207, GigaBlue UHD Trio 4K 0.7.6, pluginul extern Wireguard 14.8 numai cu plugin.so): un modul nativ GASIT,
# dar neincarcat (dlopen: "plugin.so: undefined symbol: _PyUnicode_Ready"; Components/HdsAltPython.py: "built for Python 3.13") da
# un ImportError cu path = fisierul .so si name = numele scurt al modulului ("plugin"). Numele e al unui fisier din dosarul
# pluginului, dar nu e un import relativ implicit: modulul s-a gasit si e facut pentru alt Python, iar traducerea surselor nu il
# repara. Inainte: semn de Python 2, python3-fissix adus din feed degeaba si "traducerea" pluginului (13,4 s pe firul care citeste
# lista, dupa opkg firul interfetei), apoi aceeasi eroare. Un modul NEGASIT (fara path) ramane semn.
_NATIV_TEXT = re.compile(r"^(\S+?\.(?:so(?:\.[0-9.]+)?|pyd)): ")


def _fisierNativ(cale):
	baza = os.path.basename(cale or "")
	return baza.endswith(".so") or ".so." in baza or baza.endswith(".pyd")


def nativNeincarcat(e):
	"""True cand e e ImportError-ul unui modul nativ (.so) gasit, dar neincarcat: facut pentru alt Python (hdsAltPython), un nume
	lipsa la dlopen, un fisier stricat. Calea din path sau, cand pluginul a dat mai departe numai textul, de la inceputul textului."""
	if not isinstance(e, ImportError) or isinstance(e, ModuleNotFoundError):
		return False
	if getattr(e, "hdsAltPython", None):
		return True
	cale = getattr(e, "path", None)
	if not cale:
		m = _NATIV_TEXT.match(str(e))
		cale = m.group(1) if m else None
	return _fisierNativ(cale)


def _subDosar(fisier, cale):
	if not fisier:
		return False
	f = os.path.normpath(os.path.abspath(fisier))
	d = os.path.normpath(os.path.abspath(cale))
	return f == d or f.startswith(d + os.sep)


def _moduleVecine(cale, maxim=MAX_FISIERE):
	"""numele modulelor din dosarul pluginului (fisierele .py si dosarele cu __init__.py), oricat de adanc"""
	nume = set()
	n = 0
	for radacina, dosare, fisiere in os.walk(cale):
		dosare[:] = [d for d in dosare if d != "__pycache__"]
		for f in fisiere:
			if f.endswith(".py") or f.endswith(SUFIX_ORIGINAL):
				nume.add(f.rsplit(".", 1)[0])
				n += 1
			elif f.endswith(".so"):
				# modul nativ vecin (nume.so, nume.cpython-27-arm.so): importul lui fara punct e tot relativ implicit
				nume.add(f.split(".", 1)[0])
			elif f == "__init__.py":
				nume.add(os.path.basename(radacina))
		if n > maxim:
			break
	return nume


def semnPython2(exc, cale):
	"""True cand exceptia importului pluginului din cale arata cod de Python 2 (vezi antetul)"""
	try:
		from Components.HdsPython2 import MODULE_PY2
	except Exception:
		MODULE_PY2 = frozenset(("urllib2", "urlparse", "cookielib", "httplib", "HTMLParser", "Queue", "ConfigParser", "cPickle",
			"cStringIO", "StringIO", "commands", "__builtin__", "thread", "md5", "sha", "sets", "new", "UserDict"))
	vecine = None
	for e in _lant(exc):
		if isinstance(e, SyntaxError):
			if _subDosar(getattr(e, "filename", None), cale):
				return True
		elif isinstance(e, ImportError):
			if nativNeincarcat(e):
				# PY2 0.7.7: modul nativ gasit, facut pentru alt Python; nu e semn (celelalte exceptii din lant raman)
				continue
			nume = getattr(e, "name", None) or ""
			if not nume and "No module named" in str(e):
				m = re.search(r"No module named '([^']+)'", str(e))
				nume = m.group(1) if m else ""
			if not nume:
				continue
			sus = nume.split(".")[0]
			if sus == "__init__" or sus in MODULE_PY2:
				return True
			if vecine is None:
				vecine = _moduleVecine(cale)
			if sus in vecine and "." not in nume:
				return True
		elif isinstance(e, NameError):
			if getattr(e, "name", None) in _NUME_PY2:
				return True
			m = re.search(r"name '(\w+)' is not defined", str(e))
			if m and m.group(1) in _NUME_PY2:
				return True
		elif isinstance(e, AttributeError):
			if _ATRIBUTE_PY2.search(str(e)):
				return True
	return False


# ---------------------------------------------------------------- citirea si scrierea surselor

def _decodeaza(date):
	"""(text, codare pentru scriere, cookie_pastrat). Python 2 citea octeti; un fisier fara declaratie, care nu e UTF-8,
	se citeste ca latin-1 (fiecare octet ramane acelasi caracter) si se scrie inapoi ca UTF-8."""
	if date.startswith(b"\xef\xbb\xbf"):
		return date[3:].decode("utf-8", "strict"), "utf-8", True
	codare = None
	for rand in date.split(b"\n", 2)[:2]:
		m = _COOKIE.match(rand)
		if m:
			codare = m.group(1).decode("ascii", "replace")
			break
	if codare:
		try:
			import codecs
			codecs.lookup(codare)
			return date.decode(codare), codare, True
		except (LookupError, UnicodeDecodeError):
			pass
	try:
		return date.decode("utf-8"), "utf-8", bool(codare)
	except UnicodeDecodeError:
		return date.decode("latin-1"), "utf-8", False


def _faraCookieStrain(text, codare_scriere, cookie_pastrat):
	"""daca fisierul declara o codare pe care n-am pastrat-o (am citit latin-1 si scriem UTF-8), declaratia se scrie utf-8"""
	if cookie_pastrat:
		return text
	randuri = text.split("\n", 2)
	for i in range(min(2, len(randuri))):
		if re.match(r"^[ \t\f]*#.*?coding[:=]", randuri[i]):
			randuri[i] = "# -*- coding: utf-8 -*-"
	return "\n".join(randuri)


def repara_taburi(text, tokenize_mod):
	"""inceputul randurilor cu taburi si spatii amestecate, numai cu spatii, dupa regula lui Python 2 (tab = urmatorul
	multiplu de 8); randurile din interiorul unui sir pe mai multe randuri raman neatinse. Intoarce textul (acelasi obiect daca
	nu era nimic de schimbat)."""
	randuri = text.split("\n")
	indentari = [r[:len(r) - len(r.lstrip(" \t"))] for r in randuri]
	are_tab = any("\t" in i for i in indentari)
	are_spatiu = any(" " in i for i, r in zip(indentari, randuri) if r.strip())
	if not (are_tab and are_spatiu):
		return text
	in_sir = set()
	try:
		for tok in tokenize_mod.generate_tokens(io.StringIO(text).readline):
			(r1, _c1), (r2, _c2) = tok[2], tok[3]
			if r2 > r1:
				in_sir.update(range(r1 + 1, r2 + 1))   # randurile de dupa primul, numerotate de la 1
	except Exception:
		in_sir = set()
	noi = []
	for nr, (r, ind) in enumerate(zip(randuri, indentari), 1):
		if ind and "\t" in ind and nr not in in_sir:
			noi.append(ind.expandtabs(8) + r[len(ind):])
		else:
			noi.append(r)
	return "\n".join(noi)


def _parseaza(text, cale):
	import warnings
	with warnings.catch_warnings():
		warnings.simplefilter("ignore")
		return ast.parse(text, cale)


def _compileaza(text, cale):
	"""None daca textul se compileaza in Python-ul de acum; altfel (randul, mesajul)"""
	import warnings
	try:
		with warnings.catch_warnings():
			warnings.simplefilter("ignore")
			compile(text, cale, "exec", dont_inherit=True)
		return None
	except SyntaxError as exc:
		return (exc.lineno or 0, exc.msg or str(exc))
	except (ValueError, TypeError) as exc:
		return (0, str(exc))


def _globaleInCorp(corp):
	"""instructiunile global din corpul unei functii (si din if/for/while/try/with din el), fara functiile si clasele din ea"""
	rez = []
	for nod in corp:
		if isinstance(nod, ast.Global):
			rez.append(nod)
		elif isinstance(nod, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
			continue
		else:
			for camp in ("body", "orelse", "finalbody", "handlers"):
				sub = getattr(nod, camp, None)
				if isinstance(sub, list):
					rez.extend(_globaleInCorp([s for s in sub if isinstance(s, ast.AST)]))
	return rez


def _singurPeRand(r, nod):
	"""instructiunea nod e singura pe randul r: inainte numai spatii, dupa numai spatii sau un comentariu. CM3 (0.7.8, pachetul
	public IPTVupdater 1.5, raportul 977353): `global HD ## Warning: Unused global`, cum lasa un verificator de cod in pluginurile
	vechi; inainte comentariul oprea mutarea, iar fisierul nu se traducea. Coloanele din ast sunt in octeti UTF-8."""
	b = r.encode("utf-8", "surrogateescape")
	inainte, dupa = b[:nod.col_offset], b[nod.end_col_offset:].strip()
	return not inainte.strip() and (not dupa or dupa.startswith(b"#"))


def ridicaGlobal(text, cale):
	"""Python 2 primea `global x` si dupa ce x era folosit in functie (cu un avertisment): declaratia tine pentru toata functia.
	Python 3 o refuza. Declaratiile mutate la inceputul corpului functiei au acelasi inteles. Numai cand fiecare global e singur
	pe randul lui; altfel textul ramane neschimbat."""
	try:
		arbore = _parseaza(text, cale)
	except SyntaxError:
		return text
	randuri = text.split("\n")
	mutari = []      # (randul primei instructiuni din corp, indentarea, numele, [randurile de sters])
	for nod in ast.walk(arbore):
		if not isinstance(nod, (ast.FunctionDef, ast.AsyncFunctionDef)) or not nod.body:
			continue
		glob = _globaleInCorp(nod.body)
		if not glob:
			continue
		corp = nod.body
		prim = corp[1] if (len(corp) > 1 and isinstance(corp[0], ast.Expr) and isinstance(corp[0].value, ast.Constant)
			and isinstance(corp[0].value.value, str)) else corp[0]
		if prim in glob and len(glob) == 1:
			continue
		de_sters = []
		for g in glob:
			r = randuri[g.lineno - 1]
			if g.end_lineno != g.lineno or not _singurPeRand(r, g):
				return text
			de_sters.append(g.lineno - 1)
		nume = []
		for g in glob:
			for n in g.names:
				if n not in nume:
					nume.append(n)
		r0 = randuri[prim.lineno - 1]
		mutari.append((prim.lineno - 1, r0[:len(r0) - len(r0.lstrip())], nume, de_sters))
	# la nivelul modulului global nu face nimic (in Python 2 nici repetat dupa o atribuire); devine pass
	for g in _globaleInCorp(arbore.body):
		r = randuri[g.lineno - 1]
		if g.end_lineno != g.lineno or not _singurPeRand(r, g):
			return text
		mutari.append((None, "", [], [g.lineno - 1]))
	if not mutari:
		return text
	sterse = set(i for m in mutari for i in m[3])
	inserate = dict((m[0], m[1] + "global " + ", ".join(m[2])) for m in mutari if m[0] is not None)
	noi = []
	for i, r in enumerate(randuri):
		if i in inserate:
			noi.append(inserate[i])
		if i in sterse:
			# randul ramane (gol, cu indentarea), ca numerele randurilor sa nu se schimbe si un bloc sa nu ramana gol
			noi.append(r[:len(r) - len(r.lstrip())] + "pass")
			continue
		noi.append(r)
	return "\n".join(noi)


class _NumeFolosite(ast.NodeVisitor):
	def __init__(self):
		self.citite = set()
		self.definite = set()

	def visit_Name(self, nod):
		if isinstance(nod.ctx, ast.Load):
			self.citite.add(nod.id)
		else:
			self.definite.add(nod.id)

	def visit_FunctionDef(self, nod):
		self.definite.add(nod.name)
		self.generic_visit(nod)

	visit_AsyncFunctionDef = visit_FunctionDef

	def visit_ClassDef(self, nod):
		self.definite.add(nod.name)
		self.generic_visit(nod)

	def visit_Import(self, nod):
		for a in nod.names:
			self.definite.add((a.asname or a.name).split(".")[0])

	def visit_ImportFrom(self, nod):
		for a in nod.names:
			self.definite.add(a.asname or a.name)


# HDSatelit 0.7.6 (NB2, raportul plugin 266302, NeoBoot v10 pe Vu+ Solo 4K 0.7.5): files/devices.py are la nivelul modulului
# `if not fileExists('/usr/lib/python2.7'): open = file`. Sintaxa e de Python 3, fara importuri vechi, iar fisierul se importa abia
# la eticheta discului (goSetDiskLabel, din callback-ul unui ecran): nici citirea listei, nici verificarea din sursa nu-l vedeau,
# deci interfata cadea cu NameError "name 'file' is not defined". Acum un nume vechi citit si nedefinit nicaieri in fisier e semn
# de Python 2 (semneStatice, _ePython2), iar traducerea pune in fisier randul PRELUDIU (numele din HdsPython2Compat).
# Filtrul ieftin de dinaintea analizei: numele intreg, nu atribut (.file), nu sir ('file'), urmat de ( ) , : ] } sau sfarsitul
# randului (fara `file=` din print(..., file=...), fara `file.` si fara cuvantul din fraze).
_NUME_CANDIDAT = re.compile(br"(?<![\w.'\"])(?:" + b"|".join(n.encode("ascii") for n in sorted(_NUME_PY2)) +
	br")\b(?=[ \t]*(?:[(),:\]}]|\r?$))", re.M)
# un `from X import *` din aceste pachete poate aduce chiar numele vechi (six.moves.xrange, past.builtins.unicode), la fel PRELUDIU;
# `from Components.config import *` si celelalte module ale interfetei nu aduc nume vechi
_STEA_COMPAT = frozenset(("six", "past", "future", "builtins", "__builtin__"))
_MODUL_COMPAT = "Components.HdsPython2Compat"


# PLG 0.7.7 (GT IPTV Player Pro 1.9.4 din feedul nostru extern): youtube_vendor/compat.py are, ca youtube-dl,
# `if version_info[0] == 2:` cu unicode, basestring, long si unichr, iar ramura `else:` pentru Python 3. Cu regula NB2 de mai sus
# semneStatice il dadea "nume Python 2 basestring" si un plugin Python 3 care merge se traducea in fundal (compat.py rescris, minute
# de analiza pe receptor cu lacatul Python tinut, apoi lista citita din nou si pluginul importat din nou pe firul interfetei). Acum:
# ramura unui test pe versiunea lui Python care in Python 3 nu ruleaza niciodata nu se cerceteaza (nici numele citite, nici cele
# definite acolo), iar un nume citit pe loc in corpul unui try care prinde NameError nu da NameError. Un test care nu e pe versiune
# (NeoBoot: `if not fileExists('/usr/lib/python2.7'):`) se cerceteaza in ambele ramuri, ca pana acum.
_NUME_TEST = {"PY2": False, "PY3": True, "IS_PY2": False, "IS_PY3": True, "PY3K": True, "IS_PY3K": True, "PYTHON2": False,
	"PYTHON3": True, "PYTHON_2": False, "PYTHON_3": True, "isPY2": False, "isPY3": True}
_VERSIUNE_ACUM = tuple(sys.version_info[:3])
_COMPARATII = {ast.Eq: lambda a, b: a == b, ast.NotEq: lambda a, b: a != b, ast.Lt: lambda a, b: a < b,
	ast.LtE: lambda a, b: a <= b, ast.Gt: lambda a, b: a > b, ast.GtE: lambda a, b: a >= b}


def _valoareVersiune(nod):
	"""sys.version_info / version_info (tuplul), [0], [:2], .major, .minor in Python-ul de acum; altfel None"""
	if isinstance(nod, ast.Name) and nod.id == "version_info":
		return _VERSIUNE_ACUM
	if isinstance(nod, ast.Attribute):
		if nod.attr == "version_info" and isinstance(nod.value, ast.Name) and nod.value.id == "sys":
			return _VERSIUNE_ACUM
		if nod.attr in ("major", "minor"):
			v = _valoareVersiune(nod.value)
			if isinstance(v, tuple):
				return v[0] if nod.attr == "major" else v[1]
		return None
	if isinstance(nod, ast.Subscript):
		v = _valoareVersiune(nod.value)
		if not isinstance(v, tuple):
			return None
		s = nod.slice
		if isinstance(s, ast.Constant) and type(s.value) is int and 0 <= s.value < len(v):
			return v[s.value]
		if isinstance(s, ast.Slice) and s.step is None and isinstance(s.upper, ast.Constant) and type(s.upper.value) is int and \
				0 < s.upper.value <= len(v) and (s.lower is None or (isinstance(s.lower, ast.Constant) and s.lower.value == 0)):
			return v[:s.upper.value]
	return None


def _constantaVersiune(nod):
	"""un intreg sau un tuplu de intregi scris in sursa, altfel None"""
	if isinstance(nod, ast.Constant) and type(nod.value) is int:
		return nod.value
	if isinstance(nod, ast.Tuple) and nod.elts and all(isinstance(e, ast.Constant) and type(e.value) is int for e in nod.elts):
		return tuple(e.value for e in nod.elts)
	return None


def testVersiune(nod):
	"""True / False: cat face in Python-ul de acum un test pe versiune (sys.version_info[0] == 2, version_info >= (3, 4),
	sys.version_info.major < 3, PY2, six.PY3, str is bytes, not, and, or); None cand testul nu e (numai) pe versiune"""
	if isinstance(nod, ast.UnaryOp) and isinstance(nod.op, ast.Not):
		v = testVersiune(nod.operand)
		return None if v is None else not v
	if isinstance(nod, ast.BoolOp):
		valori = [testVersiune(x) for x in nod.values]
		if isinstance(nod.op, ast.And):
			if False in valori:
				return False
			return True if all(v is True for v in valori) else None
		if True in valori:
			return True
		return False if all(v is False for v in valori) else None
	if isinstance(nod, ast.Name):
		return _NUME_TEST.get(nod.id)
	if isinstance(nod, ast.Attribute) and isinstance(nod.value, ast.Name):
		return _NUME_TEST.get(nod.attr)
	if isinstance(nod, ast.Compare) and len(nod.ops) == 1:
		stanga, dreapta, op = nod.left, nod.comparators[0], nod.ops[0]
		if isinstance(stanga, ast.Name) and isinstance(dreapta, ast.Name) and set((stanga.id, dreapta.id)) == set(("str", "bytes")):
			# `str is bytes` / `bytes == str`: adevarat numai in Python 2
			if isinstance(op, (ast.Is, ast.Eq)):
				return False
			if isinstance(op, (ast.IsNot, ast.NotEq)):
				return True
			return None
		f = _COMPARATII.get(type(op))
		if f is None:
			return None
		a, b = _valoareVersiune(stanga), _constantaVersiune(dreapta)
		if a is None or b is None:
			a, b = _constantaVersiune(stanga), _valoareVersiune(dreapta)
		if a is None or b is None or type(a) is not type(b):
			return None
		return bool(f(a, b))
	return None


def _prindeNameError(tip):
	"""True cand clauza except numeste chiar NameError (singur sau in tuplu): rezerva scrisa pentru Python 3. `except:` si
	`except Exception:` nu: codul de Python 2 inchis intr-un try care prinde tot nu mai cade, dar nici nu merge (NB2)."""
	if isinstance(tip, ast.Tuple):
		return any(_prindeNameError(e) for e in tip.elts)
	return isinstance(tip, ast.Name) and tip.id == "NameError"


class _NumeVechi(_NumeFolosite):
	"""ca _NumeFolosite, plus ce mai leaga un nume: parametrii functiilor si ai lambda, `except ... as e`, `global`/`nonlocal`,
	tiparele din match; peste tot in fisier, in orice ramura al carei test nu e pe versiune (la NeoBoot testul e pe un fisier si in
	Python 3 chiar ruleaza ramura cu numele vechi; PRELUDIU numai defineste numele vechi, nu schimba nimic altceva). PLG 0.7.7: fara
	ramurile pe care testul pe versiune le opreste in Python 3 si fara numele citite pe loc intr-un try care prinde NameError."""

	def __init__(self):
		_NumeFolosite.__init__(self)
		self.stea = False
		self._prins = 0         # cate try-uri care prind NameError cuprind codul cercetat acum (care ruleaza pe loc)

	def visit_Name(self, nod):
		if self._prins and isinstance(nod.ctx, ast.Load) and nod.id in _NUME_PY2:
			return
		_NumeFolosite.visit_Name(self, nod)

	def visit_If(self, nod):
		v = testVersiune(nod.test)
		self.visit(nod.test)
		if v is not False:
			for n in nod.body:
				self.visit(n)
		if v is not True:
			for n in nod.orelse:
				self.visit(n)

	def visit_IfExp(self, nod):
		v = testVersiune(nod.test)
		self.visit(nod.test)
		if v is not False:
			self.visit(nod.body)
		if v is not True:
			self.visit(nod.orelse)

	def visit_Try(self, nod):
		prinde = any(_prindeNameError(h.type) for h in nod.handlers)
		self._prins += 1 if prinde else 0
		try:
			for n in nod.body:
				self.visit(n)
		finally:
			self._prins -= 1 if prinde else 0
		for n in list(nod.handlers) + list(nod.orelse) + list(nod.finalbody):
			self.visit(n)

	visit_TryStar = visit_Try

	def _faraTry(self, nod, vizita):
		# corpul unei functii sau al unui lambda ruleaza mai tarziu, nu sub try-ul in care e definit
		prins, self._prins = self._prins, 0
		try:
			vizita(self, nod)
		finally:
			self._prins = prins

	def visit_FunctionDef(self, nod):
		self._faraTry(nod, _NumeFolosite.visit_FunctionDef)

	visit_AsyncFunctionDef = visit_FunctionDef

	def visit_Lambda(self, nod):
		self._faraTry(nod, ast.NodeVisitor.generic_visit)

	def visit_arg(self, nod):
		self.definite.add(nod.arg)
		self.generic_visit(nod)

	def visit_ExceptHandler(self, nod):
		if nod.name:
			self.definite.add(nod.name)
		self.generic_visit(nod)

	def visit_Global(self, nod):
		self.definite.update(nod.names)

	visit_Nonlocal = visit_Global

	def visit_MatchAs(self, nod):
		if nod.name:
			self.definite.add(nod.name)
		self.generic_visit(nod)

	def visit_MatchStar(self, nod):
		if nod.name:
			self.definite.add(nod.name)

	def visit_MatchMapping(self, nod):
		if nod.rest:
			self.definite.add(nod.rest)
		self.generic_visit(nod)

	def visit_ImportFrom(self, nod):
		_NumeFolosite.visit_ImportFrom(self, nod)
		modul = nod.module or ""
		if any(a.name == "*" for a in nod.names) and (modul == _MODUL_COMPAT or modul.split(".", 1)[0] in _STEA_COMPAT):
			self.stea = True


def numePython2(arbore):
	"""primul nume vechi din Python 2 (_NUME_PY2: file, unicode, xrange, cmp ...) citit in arborele unui fisier si nedefinit
	nicaieri in el (in Python 3 da NameError cand ajunge acolo), altfel None"""
	v = _NumeVechi()
	v.visit(arbore)
	if v.stea:
		return None
	lipsa = (v.citite & _NUME_PY2) - v.definite
	return min(lipsa) if lipsa else None


def _cuPreludiu(text, cale):
	"""textul tradus, cu PRELUDIU dupa docstringul modulului (sau inaintea primei instructiuni) cand foloseste un nume din
	Components/HdsPython2Compat.py pe care nu il defineste el insusi"""
	try:
		arbore = _parseaza(text, cale)
	except SyntaxError:
		return text
	v = _NumeFolosite()
	v.visit(arbore)
	if not ((v.citite & NUME_COMPAT) - v.definite):
		return text
	randuri = text.split("\n")
	corp = arbore.body
	if not corp:
		return text
	if isinstance(corp[0], ast.Expr) and isinstance(getattr(corp[0], "value", None), ast.Constant) and \
			isinstance(corp[0].value.value, str):
		# dupa docstring si dupa importurile din __future__ (trebuie sa ramana primele)
		poz = corp[0].end_lineno
		for nod in corp[1:]:
			if isinstance(nod, ast.ImportFrom) and nod.module == "__future__":
				poz = nod.end_lineno
			else:
				break
	else:
		poz = 0
		for nod in corp:
			if isinstance(nod, ast.ImportFrom) and nod.module == "__future__":
				poz = nod.end_lineno
			else:
				break
		if poz == 0:
			prim = corp[0]
			poz = min([prim.lineno] + [d.lineno for d in getattr(prim, "decorator_list", [])]) - 1
	randuri.insert(poz, PRELUDIU)
	return "\n".join(randuri)


# ---------------------------------------------------------------- motorul

_motor = {}


def motorDisponibil():
	try:
		import fissix  # noqa: F401
		return True
	except Exception:
		return False


def _fixerImpartire(fixer_base, fixer_util, token, syms):
	"""a / b -> hds_py2_div(a, b) si a /= b -> a = hds_py2_idiv(a, b), ca in Python 2 (fara `from __future__ import division`)"""
	from fissix.pytree import Leaf, Node

	def _float(nod):
		return nod.type == token.NUMBER and not nod.value.lower().startswith("0x") and \
			("." in nod.value or "e" in nod.value.lower() or nod.value.lower().endswith("j"))

	class FixHdsImpartire(fixer_base.BaseFix):
		BM_compatible = False
		order = "post"
		PATTERN = """
			term< any+ >
			|
			expr_stmt< any '/=' any >
		"""

		def start_tree(self, tree, filename):
			super(FixHdsImpartire, self).start_tree(tree, filename)
			self.sari = "division" in getattr(tree, "future_features", ())

		def match(self, nod):
			if self.sari:
				return False
			if nod.type == syms.term:
				return any(c.type == token.SLASH for c in nod.children)
			if nod.type == syms.expr_stmt and len(nod.children) == 3:
				return nod.children[1].type == token.SLASHEQUAL
			return False

		def transform(self, nod, rezultate):
			if nod.type == syms.expr_stmt:
				tinta, _op, val = nod.children
				if tinta.type not in (token.NAME, syms.power):
					return None
				apel = fixer_util.Call(Name_("hds_py2_idiv"), [tinta.clone(), fixer_util.Comma(), _faraPrefix(val.clone())],
					prefix=" ")
				nou = Node(syms.expr_stmt, [tinta.clone(), Leaf(token.EQUAL, "=", prefix=" "), apel])
				nou.prefix = nod.prefix
				return nou
			copii = [c.clone() for c in nod.children]
			prefix = copii[0].prefix
			copii[0].prefix = ""
			acum = [copii[0]]
			i = 1
			while i < len(copii):
				op, dreapta = copii[i], copii[i + 1]
				if op.type == token.SLASH and not (_float(acum[-1]) if len(acum) == 1 else False) and not _float(dreapta):
					stanga = acum[0] if len(acum) == 1 else Node(syms.term, acum)
					stanga.prefix = ""
					acum = [fixer_util.Call(Name_("hds_py2_div"), [stanga, fixer_util.Comma(), _faraPrefix(dreapta)])]
				else:
					acum.extend([op, dreapta])
				i += 2
			nou = acum[0] if len(acum) == 1 else Node(syms.term, acum)
			nou.prefix = prefix
			return nou

	def Name_(text):
		return fixer_util.Name(text)

	def _faraPrefix(n):
		n.prefix = " "
		return n

	return FixHdsImpartire


_INIT_PACHET = ("__init__.py", "__init__.pyc", "__init__.pyo", "__init__" + SUFIX_ORIGINAL)


def ePachet(dosar):
	"""True cand dosarul e pachet pentru Python 2 (are __init__.py, .pyc, .pyo sau originalul nostru __init__.py2)"""
	return any(os.path.exists(os.path.join(dosar, n)) for n in _INIT_PACHET)


def _fixerImport():
	"""fix_import din fissix, cu modulul vecin ca in Python 2: un dosar e modul vecin numai cand e pachet (are __init__). fissix
	socoteste orice dosar cu acelasi nume (raportul 781623: Styles/skin/, cu xml si imagini, facea din `from skin import loadSkin`
	un `from .skin import`, iar in Python 3 dosarul devenea pachet gol: "unknown location")."""
	from fissix.fixes.fix_import import FixImport

	class FixHdsImport(FixImport):
		def probably_a_local_import(self, imp_name):
			if imp_name.startswith("."):
				return False
			imp_name = imp_name.split(".", 1)[0]
			dosar = os.path.dirname(self.filename)
			if not ePachet(dosar):
				return False
			baza = os.path.join(dosar, imp_name)
			for ext in (".py", ".pyc", ".so", ".sl", ".pyd"):
				if os.path.exists(baza + ext):
					return True
			return os.path.isdir(baza) and ePachet(baza)
	return FixHdsImport


def _unelte():
	"""(unealta cu gramatica lui Python 2, unealta fara instructiunea print), facute o data"""
	if "unelte" in _motor:
		return _motor["unelte"]
	import logging
	from fissix import fixer_base, fixer_util, pygram
	from fissix.pgen2 import token
	from fissix.refactor import RefactoringTool, get_fixers_from_package
	logging.getLogger("RefactoringTool").setLevel(logging.ERROR)
	fixere = [f for f in get_fixers_from_package("fissix.fixes") if f.rsplit(".", 1)[-1] not in _FARA]
	Impartire = _fixerImpartire(fixer_base, fixer_util, token, pygram.python_symbols)
	ImportVecin = _fixerImport()

	def _importulNostru(lista, unealta):
		return [ImportVecin(unealta.options, unealta.fixer_log) if type(f).__name__ == "FixImport" else f for f in lista]

	class Unealta(RefactoringTool):
		def get_fixers(self):
			pre, post = RefactoringTool.get_fixers(self)
			pre, post = _importulNostru(pre, self), _importulNostru(post, self)
			post.append(Impartire(self.options, self.fixer_log))
			return pre, post

		def log_error(self, msg, *args, **kwds):
			raise

	from fissix.pgen2 import tokenize as tok
	_motor["tokenize"] = tok
	_motor["unelte"] = (Unealta(fixere, {"print_function": False}), Unealta(fixere, {"print_function": True}))
	# pentru scripturi (rulate cu `python fisier.py`): fara importurile relative (acolo `import vecin` e corect si in Python 3)
	fara_import = [f for f in fixere if not f.endswith(".fix_import")]
	_motor["scripturi"] = (Unealta(fara_import, {"print_function": False}), Unealta(fara_import, {"print_function": True}))
	# „numai importurile”: un fisier care se compileaza in Python 3 si are numai importuri vechi (importul relativ implicit, module
	# de Python 2) intr-un plugin Python 3: se repara numai importurile; impartirea si restul codului lui raman cum sunt

	class NumaiImporturi(RefactoringTool):
		def get_fixers(self):
			pre, post = RefactoringTool.get_fixers(self)
			return _importulNostru(pre, self), _importulNostru(post, self)

		def log_error(self, msg, *args, **kwds):
			raise
	importuri = [f for f in fixere if f.rsplit(".", 1)[-1] in _IMPORTURI]
	_motor["importuri"] = NumaiImporturi(importuri, {"print_function": True})
	_motor["importuri_script"] = NumaiImporturi([f for f in importuri if not f.endswith(".fix_import")], {"print_function": True})
	return _motor["unelte"]


_IMPORTURI = frozenset(("fix_import", "fix_imports", "fix_imports2", "fix_urllib"))


def eScript(text):
	"""True pentru un fisier care se ruleaza ca program (#! pe primul rand, ca NeoBoot ex_init.py rulat cu `python ex_init.py`):
	acolo dosarul lui e in sys.path, deci un import fara punct al unui vecin merge si in Python 3 si nu e semn de Python 2. Un bloc
	`if __name__ == "__main__"` singur nu face dintr-un fisier un program: multe module il au pentru probe si se importa ca module
	(SimpleRSS GoogleReader.py, VideoColorSpace plugin.py)."""
	if isinstance(text, bytes):
		return text.startswith(b"#!")
	return text.startswith("#!")


_MODULE_MEREU = ("plugin.py", "__init__.py")   # le importa interfata, oricat ar avea `#!` pe primul rand


def _importDe(nume):
	n = re.escape(nume)
	return re.compile(r"^[ \t]*(?:from[ \t]+\.?%s(?:\.\w+)*[ \t]+import\b|import[ \t]+[^\n#]*\b%s\b|"
		r"from[ \t]+\.[ \t]+import[ \t]+[^\n#]*\b%s\b)" % (n, n, n), re.M)


def eScriptFisier(text, cale):
	"""eScript, dupa fisier: plugin.py, __init__.py si un fisier `#!` importat de un modul din acelasi dosar sunt module, nu
	programe (vezi _moduleDosar). Multe pluginuri vechi au `#!/usr/bin/python` pe plugin.py si pe modulele lor (raportul 781623,
	Styles: plugin.py, Styles.py, PicLoader.py); fara repararea importurilor ramaneau `from __init__ import _` si
	`from PicLoader import ...`, care in Python 3 nu gasesc nimic. Un program adevarat (NeoBoot ex_init.py, rulat cu
	`python ex_init.py`) nu e importat de niciun modul (extract.py e importat numai de ex_init.py, tot program)."""
	if not eScript(text):
		return False
	if not cale:
		return True
	baza = os.path.basename(cale)
	if baza in _MODULE_MEREU:
		return False
	return baza.rsplit(".", 1)[0] not in _moduleDosar(os.path.dirname(cale))


_module_dosar = {}


def _moduleDosar(dosar):
	"""numele fisierelor .py din dosar care sunt module: cele fara `#!`, plugin.py, __init__.py, apoi, pana nu mai apare nimic nou,
	orice fisier `#!` importat de un modul (plugin.py -> A.py `#!` -> B.py `#!`: amandoua module). Tinut minte dupa marimile si
	timpii fisierelor."""
	try:
		nume = sorted(f for f in os.listdir(dosar) if f.endswith(".py"))
		semn = tuple((f, os.stat(os.path.join(dosar, f)).st_size, os.stat(os.path.join(dosar, f)).st_mtime_ns) for f in nume)
	except OSError:
		return frozenset()
	stiut = _module_dosar.get(dosar)
	if stiut and stiut[0] == semn:
		return stiut[1]
	texte = {}
	for f in nume[:MAX_FISIERE]:
		try:
			with open(os.path.join(dosar, f), "rb") as fh:
				texte[f[:-3]] = fh.read(MAX_OCTETI)
		except OSError:
			pass
	module = set(n for n, d in texte.items() if n + ".py" in _MODULE_MEREU or not d.startswith(b"#!"))
	de_cautat = list(module)
	while de_cautat:
		m = texte[de_cautat.pop()].decode("utf-8", "replace")
		for n in texte:
			if n not in module and _importDe(n).search(m):
				module.add(n)
				de_cautat.append(n)
	rez = frozenset(module)
	if len(_module_dosar) > 64:
		_module_dosar.clear()
	_module_dosar[dosar] = (semn, rez)
	return rez


def vecineDosar(dosar):
	"""numele modulelor din acelasi dosar (importul relativ implicit al lui Python 2 cauta numai in pachetul fisierului)"""
	if True:
		nume = set()
		try:
			for f in os.listdir(dosar):
				p = os.path.join(dosar, f)
				if f.endswith(".py") or f.endswith(SUFIX_ORIGINAL):
					nume.add(f.rsplit(".", 1)[0])
				elif f.endswith(".so"):
					nume.add(f.split(".", 1)[0])
				elif os.path.isdir(p) and (os.path.exists(os.path.join(p, "__init__.py")) or
						os.path.exists(os.path.join(p, "__init__" + SUFIX_ORIGINAL))):
					nume.add(f)
		except OSError:
			pass
	return nume


_INIT_RELATIV = re.compile(r"^(\s*from\s+)\.__init__(\s+import\b)", re.M)
# numele scoase din Python dupa Python 2 (3.3-3.12), cu acelasi inteles sub numele nou: se schimba numai in fisierele traduse
_ABC = ("Mapping", "MutableMapping", "Sequence", "MutableSequence", "Set", "MutableSet", "Iterable", "Iterator", "Callable",
	"Hashable", "Sized", "Container", "KeysView", "ItemsView", "ValuesView", "MappingView", "Generator", "Awaitable", "Coroutine")
_COLLECTIONS_ABC = re.compile(r"\bcollections\.(%s)\b" % "|".join(_ABC))
_FROM_COLLECTIONS = re.compile(r"^([ \t]*)from[ \t]+collections[ \t]+import[ \t]+([\w \t,]+)$", re.M)
_BASE64 = re.compile(r"\bbase64\.(encodestring|decodestring)\b")
_IS_ALIVE = re.compile(r"\.isAlive\(\)")
_TIME_CLOCK = re.compile(r"\btime\.clock\(\)")
_FROM_BASE64 = re.compile(r"^([ \t]*from[ \t]+base64[ \t]+import[ \t]+)([\w \t,]+)$", re.M)
_MAKETRANS = re.compile(r"\bstring\.maketrans\(")
_FROM_STRING = re.compile(r"^([ \t]*)from[ \t]+string[ \t]+import[ \t]+([\w \t,]+)$", re.M)


def numeScoase(text):
	"""base64.encodestring/decodestring -> encodebytes/decodebytes, collections.Mapping & co. -> collections.abc,
	Thread.isAlive() -> is_alive() (cand fisierul nu are el insusi o metoda isAlive), time.clock() -> time.perf_counter()"""
	nou = _BASE64.sub(lambda m: "base64." + ("encodebytes" if m.group(1) == "encodestring" else "decodebytes"), text)
	nou = _TIME_CLOCK.sub("time.perf_counter()", nou)
	nou = _MAKETRANS.sub("str.maketrans(", nou)

	def din_base64(m):
		nume = [n.strip() for n in m.group(2).split(",") if n.strip()]
		vechi = {"encodestring": "encodebytes", "decodestring": "decodebytes"}
		if not any(n in vechi for n in nume):
			return m.group(0)
		return m.group(1) + ", ".join(("%s as %s" % (vechi[n], n)) if n in vechi else n for n in nume)
	nou = _FROM_BASE64.sub(din_base64, nou)

	def din_string(m):
		nume = [n.strip() for n in m.group(2).split(",") if n.strip()]
		if "maketrans" not in nume:
			return m.group(0)
		rest = [n for n in nume if n != "maketrans"]
		# pe acelasi rand (numerele randurilor raman aceleasi)
		text = m.group(1) + "maketrans = str.maketrans"
		return text + ("; from string import %s" % ", ".join(rest) if rest else "")
	nou = _FROM_STRING.sub(din_string, nou)
	if "def isAlive" not in nou:
		nou = _IS_ALIVE.sub(".is_alive()", nou)

	def din_collections(m):
		nume = [n.strip() for n in m.group(2).split(",") if n.strip()]
		abc = [n for n in nume if n.split()[0] in _ABC]
		if not abc:
			return m.group(0)
		rest = [n for n in nume if n not in abc]
		# pe acelasi rand (numerele randurilor raman aceleasi)
		text = "%sfrom collections.abc import %s" % (m.group(1), ", ".join(abc))
		return text + ("; from collections import %s" % ", ".join(rest) if rest else "")
	nou = _FROM_COLLECTIONS.sub(din_collections, nou)
	if _COLLECTIONS_ABC.search(nou):
		nou = _COLLECTIONS_ABC.sub(r"collections.abc.\1", nou)
		# collections.abc nu vine singur cu `import collections`; randul pus langa `import collections`
		nou = re.sub(r"^(\s*)import collections\s*$", r"\1import collections, collections.abc", nou, count=0, flags=re.M)
	return nou


def traduceText(text, cale, numai_importuri=False):
	"""(textul tradus, None) sau (None, (randul, mesajul)). cale e calea adevarata a fisierului (importurile relative
	implicite se recunosc dupa fisierele vecine). numai_importuri: numai importurile vechi (vezi _unelte)."""
	py2, py3 = _unelte()
	script = eScriptFisier(text, cale)
	if script:
		py2, py3 = _motor["scripturi"]
	text = repara_taburi(text, _motor["tokenize"])
	if not text.endswith("\n"):
		text += "\n"
	if numai_importuri:
		unealta = _motor["importuri_script" if script else "importuri"]
	else:
		unealta = py3 if _compileaza(text, cale) is None else py2
	try:
		arbore = unealta.refactor_string(text, cale)
	except Exception as exc:
		rand = 0
		ctx = getattr(exc, "context", None)
		try:
			rand = ctx[1][0]
		except (TypeError, IndexError):
			pass
		return None, (rand, "%s: %s" % (type(exc).__name__, (str(exc).splitlines() or [""])[0][:160]))
	if arbore is None:
		return None, (0, "nu s-a putut citi")
	nou = _INIT_RELATIV.sub(r"\1.\2", str(arbore))
	nou = numeScoase(nou)
	nou = _cuPreludiu(nou, cale)
	eroare = _compileaza(nou, cale)
	if eroare is not None and "global declaration" in eroare[1]:
		nou = ridicaGlobal(nou, cale)
		eroare = _compileaza(nou, cale)
	if eroare is not None:
		return None, eroare
	return nou, None


def _fisierePy(cale):
	rez = []
	for radacina, dosare, fisiere in os.walk(cale):
		dosare[:] = sorted(d for d in dosare if d != "__pycache__")
		for f in sorted(fisiere):
			if f.endswith(".py"):
				rez.append(os.path.join(radacina, f))
	return rez


def _numaiCompilate(cale):
	"""True cand pluginul are plugin.pyo / plugin.pyc de Python 2 si niciun plugin.py"""
	if os.path.exists(os.path.join(cale, "plugin.py")):
		return False
	for n in ("plugin.pyo", "plugin.pyc"):
		try:
			with open(os.path.join(cale, n), "rb") as f:
				cap = f.read(4)
		except OSError:
			continue
		try:
			from Components.HdsPython2 import versiune_compilat
		except Exception:
			return False
		if versiune_compilat(cap) == 2:
			return True
	return False


_scriereAsteptata = threading.local()


def _scrieVerificat(cale, date, asteptat):
	"""Leaga scrierea de continutul din plan, inclusiv la revenirea dupa eroare."""
	vechi = getattr(_scriereAsteptata, "intrare", None)
	_scriereAsteptata.intrare = (cale, asteptat)
	try:
		_scrie(cale, date)
	finally:
		_scriereAsteptata.intrare = vechi


def _scrie(cale, date):
	import tempfile
	# BPY2: verifica destinatia dupa pregatirea si fsync-ul temporarului.
	# Include identitatea, ca o inlocuire cu acelasi continut sa nu fie pierduta.
	def citeste():
		try:
			with open(cale, "rb") as f:
				s = os.fstat(f.fileno())
				if not stat.S_ISREG(s.st_mode) or os.path.islink(cale):
					raise OSError("destinatie nesigura")
				return (s.st_ino, s.st_mtime_ns, s.st_ctime_ns, s.st_mode, f.read(MAX_PLAN_TRADUCERE + 1))
		except FileNotFoundError:
			return None
	asteptat = citeste()
	plan = getattr(_scriereAsteptata, "intrare", None)
	if plan is not None and plan[0] == cale and (None if asteptat is None else asteptat[-1]) != plan[1]:
		raise OSError("destinatia nu mai corespunde planului")
	fd, tmp = tempfile.mkstemp(prefix=".hds-py2-", dir=os.path.dirname(cale))
	try:
		with os.fdopen(fd, "wb") as f:
			f.write(date)
			f.flush()
			os.fsync(f.fileno())
		try:
			os.chmod(tmp, os.stat(cale).st_mode & 0o7777)
		except OSError:
			os.chmod(tmp, 0o644)
		if citeste() != asteptat:
			raise OSError("destinatie schimbata in timpul scrierii")
		os.replace(tmp, cale)
	finally:
		try:
			os.remove(tmp)
		except FileNotFoundError:
			pass


def sintaxaPython2(f, date=None):
	"""True cand fisierul are sintaxa lui Python 2 (nu se compileaza in Python-ul de acum sau dupa gramatica 3.13): numai atunci
	se traduce tot codul lui, cu impartirea lui Python 2"""
	try:
		if date is None:
			with open(f, "rb") as fh:
				date = fh.read(MAX_OCTETI + 1)
		text = _decodeaza(date)[0]
	except (OSError, UnicodeDecodeError):
		return False
	if _compileaza(text, f) is not None:
		return True
	try:
		from Components.HdsPython2 import din_sursa, SURSA
		r = din_sursa(date, f)
		return r is not None and r[0] == SURSA
	except Exception:
		return False


def _ePython2(f, vecine, date=None):
	"""True cand fisierul .py e de Python 2: nu se compileaza in Python-ul de acum sau dupa gramatica 3.13, importa module de
	Python 2, citeste un nume vechi nedefinit (numePython2) ori importa fara punct un modul vecin (care nu exista ca import
	absolut)"""
	try:
		if date is None:
			with open(f, "rb") as fh:
				date = fh.read(MAX_OCTETI + 1)
		text = _decodeaza(date)[0]
	except (OSError, UnicodeDecodeError):
		return False
	if _compileaza(text, f) is not None:
		return True
	try:
		from Components.HdsPython2 import din_sursa, GRAMATICA
		if din_sursa(date, f) is not None:
			return True
		import warnings
		with warnings.catch_warnings():
			warnings.simplefilter("ignore")
			arbore = ast.parse(date, f, "exec", feature_version=GRAMATICA)
		if eScriptFisier(date, f):
			return False
		# NB2 (0.7.6): un nume vechi citit si nedefinit (NeoBoot files/devices.py `open = file`): traducerea numai la importuri,
		# care pune PRELUDIU in fisier
		if _NUME_CANDIDAT.search(date) is not None and numePython2(arbore):
			return True
		v = _ImporturiVecine(vecineDosar(os.path.dirname(f)))
		v.visit(arbore)
		return bool(v.gasite)
	except Exception:
		return False


def importabil(rel):
	"""CM3 (0.7.8): fisierul .py (calea relativa la plugin) se poate importa ca modul: fiecare dosar si numele fisierului sunt
	nume Python (nu plugin~.py, copia de rezerva a unui editor, nici "plugin (2).py" sau "x-vechi.py"). Traducerea e totul
	sau nimic numai peste fisierele care se pot importa: pe IPTVupdater 1.5 (raportul 977353, pachetul public) copia
	plugin~.py, pe care n-o importa nimeni, oprea traducerea intregului plugin la fiecare citire a listei."""
	parti = rel.replace("\\", "/")[:-3].split("/") if rel.endswith(".py") else [""]
	return all(p.isidentifier() and not keyword.iskeyword(p) for p in parti)


def _lasat(cale, rel, motiv):
	"""un fisier care nu se poate importa ca modul (importabil) si nu se traduce ramane cum e; pluginul se traduce mai departe"""
	_jurnal("%s: %s ramane netradus (nu se importa ca modul): %s" % (_cheie(cale), rel, motiv))


def traduceDosar(cale, timp_maxim=TIMP_MAXIM, tot=None, pauza=0.0, _plan=None):
	"""traduce pluginul din dosarul cale (vezi antetul). Intoarce Rezultat. tot: True = tot pluginul (s-a vazut ca nu se incarca in
	Python 3: e un plugin de Python 2), None = dupa sintaxa lui plugin.py (pluginul s-a incarcat, deci partea lui Python 3 nu se atinge).
	pauza: secunde de asteptare inaintea fiecarui fisier dupa primul (pe firul de verificare, ca interfata sa ia lacatul Python)."""
	inceput = time.monotonic()
	if _numaiCompilate(cale):
		return Rezultat(COMPILAT, motiv="plugin.pyo")
	if not motorDisponibil():
		return Rezultat(FARA_MOTOR)
	stare = _citesteStare()
	cheie = _cheie(cale)
	vechi = stare["pluginuri"].get(cheie) or {}
	stiute = (vechi.get("fisiere") or {}) if vechi.get("versiune") == VERSIUNE else {}
	# traducerile unei versiuni mai vechi a traducatorului: fisierul care e inca acea traducere se traduce din nou din original (.py2),
	# numai cand .py2 e chiar originalul tinut minte (dupa o actualizare prin opkg fisierul de acum e originalul)
	traduse_vechi = (vechi.get("fisiere") or {}) if vechi and vechi.get("versiune") != VERSIUNE else {}
	fisiere = _fisierePy(cale)
	if len(fisiere) > MAX_FISIERE:
		return Rezultat(PREA_MARE, motiv="%d fisiere .py" % len(fisiere))
	de_scris = []       # (cale, original, tradus)
	pastrate = {}
	vecine = _moduleVecine(cale)
	# tot pluginul cand nu se incarca deloc in Python 3 (incearca) sau cand plugin.py are sintaxa lui Python 2; altfel (un plugin Python 3 cu cateva fisiere vechi, de pilda un modul
	# incarcat numai la nevoie) numai fisierele vechi: cele cu sintaxa lui Python 2 de tot, cele care se compileaza in Python 3 si au
	# numai importuri vechi numai la importuri (NeoBoot files/Harddisk.py: `import Task` pe o ramura, dar `/` e impartirea reala)
	if tot is None:
		tot = sintaxaPython2(os.path.join(cale, "plugin.py"))
	for i_fisier, f in enumerate(fisiere):
		if pauza and i_fisier:
			time.sleep(pauza)
		rel = os.path.relpath(f, cale).replace("\\", "/")
		try:
			with open(f, "rb") as fh:
				date = fh.read(MAX_OCTETI + 1)
		except OSError as exc:
			return Rezultat(NETRADUS, motiv="%s: %s" % (rel, exc))
		if len(date) > MAX_OCTETI:
			if not importabil(rel):
				_lasat(cale, rel, "%d octeti" % len(date))
				continue
			return Rezultat(PREA_MARE, motiv="%s: %d octeti" % (rel, len(date)))
		suma = _suma(date)
		stiut = stiute.get(rel)
		if stiut and suma == stiut.get("tradus"):
			pastrate[rel] = stiut          # e traducerea noastra; nu se traduce a doua oara
			continue
		actual = date
		din_original = False
		tv = traduse_vechi.get(rel)
		if tv and suma == tv.get("tradus"):
			try:
				with open(f + "2", "rb") as fh:
					original = fh.read(MAX_OCTETI + 1)
			except OSError:
				original = None
			if original is not None and _suma(original) == tv.get("original"):
				date, din_original = original, True
		iesire = None
		numai_importuri = False
		sari = False
		if not tot and not sintaxaPython2(f, date):
			if not _ePython2(f, vecine, date):
				sari = True
			numai_importuri = True
		if not sari:
			try:
				text, codare, cookie = _decodeaza(date)
			except UnicodeDecodeError as exc:
				if not importabil(rel):
					_lasat(cale, rel, exc)
					continue
				return Rezultat(NETRADUS, motiv="%s: %s" % (rel, exc))
			nou, eroare = traduceText(text, f, numai_importuri)
			if eroare is not None:
				if not importabil(rel):
					_lasat(cale, rel, "randul %s: %s" % (eroare[0], eroare[1]))
					continue
				return Rezultat(NETRADUS, motiv="%s, randul %s: %s" % (rel, eroare[0], eroare[1]))
			if time.monotonic() - inceput > timp_maxim:
				return Rezultat(NETRADUS, motiv="timpul (%d s)" % timp_maxim, secunde=time.monotonic() - inceput)
			if not (nou == text or (nou == text + "\n" and not text.endswith("\n"))):
				nou = _faraCookieStrain(nou, codare, cookie)
				try:
					iesire = nou.encode(codare)
				except (UnicodeEncodeError, LookupError):
					iesire = _faraCookieStrain(nou, "utf-8", False).encode("utf-8")
		if iesire is None or iesire == date:
			if not din_original:
				continue
			iesire = date               # originalul nu mai are nimic de tradus: se pune inapoi
		if iesire == actual:
			pastrate[rel] = {"original": _suma(date), "tradus": suma}
			continue
		de_scris.append((f, rel, date, iesire))
	secunde = time.monotonic() - inceput
	if _plan is not None:
		# BPY1: copilul pregateste traducerea, fara scrieri in plugin sau STARE.
		_plan.update(de_scris=de_scris, pastrate=pastrate, vechi=bool(traduse_vechi), secunde=secunde)
		return Rezultat(TRADUS if de_scris else (DEJA if pastrate else NIMIC),
			fisiere=len(de_scris), secunde=secunde, detalii=[v[1] for v in de_scris])
	if not de_scris:
		if traduse_vechi and pastrate:
			# traducerea veche era deja cea de acum: tinuta minte cu versiunea noua (nu se mai verifica la fiecare pornire)
			_punePlugin(cheie, {"stare": TRADUS, "versiune": VERSIUNE, "cand": int(time.time()),
				"secunde": round(secunde, 2), "fisiere": pastrate})
		return Rezultat(DEJA if pastrate else NIMIC, secunde=secunde)
	# totul s-a tradus si se compileaza: abia acum se scrie ceva
	scrise = []
	try:
		for f, rel, original, iesire in de_scris:
			_scrie(f + "2" if f.endswith(".py") else f + SUFIX_ORIGINAL, original)
			_scrie(f, iesire)
			_stergeCompilate(f)
			scrise.append(rel)
			pastrate[rel] = {"original": _suma(original), "tradus": _suma(iesire)}
	except OSError as exc:
		# puse la loc cele scrise deja: pluginul ramane cum era
		for f, rel, original, _i in de_scris:
			if rel in scrise:
				try:
					_scrie(f, original)
				except OSError:
					pass
		return Rezultat(NETRADUS, motiv="scrierea: %s" % exc, secunde=secunde)
	_punePlugin(cheie, {"stare": TRADUS, "versiune": VERSIUNE, "cand": int(time.time()), "secunde": round(secunde, 2),
		"fisiere": pastrate})
	return Rezultat(TRADUS, fisiere=len(scrise), secunde=secunde, detalii=scrise)


def _stergeCompilate(f):
	"""<nume>.pyc / <nume>.pyo de langa un fisier .py rescris: compilate din textul de dinainte (pe receptor stau langa sursa si
	s-ar incarca mai departe in locul textului nou); Python le face din nou din textul de acum"""
	for ext in (".pyc", ".pyo"):
		try:
			os.remove(f[:-3] + ext)
		except OSError:
			pass


def puneOriginalele(cale, _cerere=None, _nativ=None):
	"""Reface numai traducerile proprii neschimbate. Intoarce numarul fisierelor."""
	cerere = _cerere or {"anulat": threading.Event(), "asteapta": anuleazaTraducerea(cale)}
	for activa in cerere["asteapta"]:
		if not activa["gata"].wait(2):
			_jurnal("originalele asteapta oprirea scrierii traducerii")
			return 0
	cheie = _cheie(cale)
	scrise = []
	with _lacatStare:
		stare = _citesteStare()
		intrare_veche = stare["pluginuri"].get(cheie)
		if not intrare_veche or cerere["anulat"].is_set():
			return 0
		if _nativ is None and intrare_veche.get("nativ"):
			_nativ = _nativPastrat(cale)
		ramase = dict(intrare_veche.get("fisiere") or {})
		try:
			for rel, sume in list(ramase.items()):
				if cerere["anulat"].is_set():
					raise OSError("refacerea originalelor a fost anulata")
				f = os.path.join(cale, rel)
				try:
					with open(f, "rb") as fh:
						actual = fh.read()
					with open(f + "2", "rb") as fh:
						original = fh.read()
				except OSError:
					continue
				if _suma(actual) != sume.get("tradus") or _suma(original) != sume.get("original"):
					continue
				_scrieVerificat(f, original, actual)
				scrise.append((f, original, actual))
				ramase.pop(rel)
			if cerere["anulat"].is_set():
				raise OSError("refacerea originalelor a fost anulata")
			if _nativ is not None:
				noua = dict(intrare_veche, stare=NETRADUS, fisiere=ramase,
					nativ=_nativ, versiune_nativa=_semnVersiuneNativa(cale, _nativ))
				stare["pluginuri"][cheie] = noua
			elif ramase:
				noua = dict(intrare_veche, stare=NETRADUS, fisiere=ramase)
				stare["pluginuri"][cheie] = noua
			else:
				noua = None
				stare["pluginuri"].pop(cheie, None)
			if noua != intrare_veche:
				for camp in ("verificate", "semne", "progres"):
					stare.get(camp, {}).pop(cheie, None)
				_scrieStare(stare)
				if _citesteStare()["pluginuri"].get(cheie) != noua:
					raise OSError("starea originalelor nu a fost salvata")
				cerere["schimbat"] = True
		except OSError as exc:
			for f, original, actual in reversed(scrise):
				try:
					_scrieVerificat(f, actual, original)
				except OSError as eroare:
					_jurnal("%s: %s" % (f, eroare))
			_jurnal("originalele nu s-au refacut: %s" % exc)
			return 0
	for f, _original, _actual in scrise:
		_stergeCompilate(f)
	return len(scrise)


_restaurariOriginale = {}


def _dateEroareNativa(exc):
	return {"mesaj": str(exc), "name": getattr(exc, "name", None), "path": getattr(exc, "path", None),
		"hdsAltPython": getattr(exc, "hdsAltPython", None)}


def _eroareNativa(date):
	exc = ImportError(date["mesaj"], name=date.get("name"), path=date.get("path"))
	if date.get("hdsAltPython"):
		exc.hdsAltPython = date["hdsAltPython"]
	return exc


# unde cauta incarcatorul o biblioteca numita fara cale ("libx.so.1: cannot open shared object file")
_DOSARE_BIBLIOTECI = ("/lib", "/usr/lib")


def _fisiereNative(cale, nativ):
	"""Fisierele numite de eroarea nativa: path si cel de la inceputul textului (ca in nativNeincarcat).
	Un nume fara cale se cauta in dosarul pluginului si in dosarele bibliotecilor, niciodata fata de dosarul curent."""
	if not nativ:
		return []
	m = _NATIV_TEXT.match(nativ.get("mesaj") or "")
	locuri = []
	for f in (nativ.get("path"), m.group(1) if m else None):
		if not f:
			continue
		for loc in [f] if os.path.isabs(f) else [os.path.normpath(os.path.join(d, f)) for d in (cale,) + _DOSARE_BIBLIOTECI]:
			if loc not in locuri:
				locuri.append(loc)
	return locuri


def _semnVersiuneNativa(cale, nativ=None):
	"""Versiunea surselor si binarelor, plus a modulului nativ cazut (si cand e in alt dosar);
	se citeste numai pe firul de lucru."""
	h = hashlib.sha256()
	h.update(repr(tuple(sys.version_info[:2])).encode("ascii"))
	for f in _fisiereNative(cale, nativ):
		try:
			s = os.stat(f)
			semn = (s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
		except OSError:
			semn = None
		h.update(repr(("nativ", f, semn)).encode("utf-8", "surrogateescape"))
	for rad, dosare, fisiere in os.walk(cale):
		dosare[:] = sorted(d for d in dosare if d != "__pycache__")
		for nume in sorted(fisiere):
			if not (nume.endswith((".py", ".py2")) or _fisierNativ(nume)):
				continue
			f = os.path.join(rad, nume)
			s = os.stat(f)
			h.update(repr((os.path.relpath(f, cale), s.st_ino, s.st_size,
				s.st_mtime_ns, s.st_ctime_ns)).encode("utf-8", "surrogateescape"))
	return h.hexdigest()


def _nativPastrat(cale):
	"""Motivul nativ ramane valabil numai pentru versiunea restaurata."""
	e = intrare(cale) or {}
	if e.get("nativ") and e.get("versiune_nativa") == _semnVersiuneNativa(cale, e["nativ"]):
		return e["nativ"]
	return None


def _cereOriginalele(cale, exc):
	"""La importul nativ cazut, pe interfata se pune numai cererea in memorie."""
	cheie = _cheie(cale)
	with _lacat:
		if _inchideTraducerile or cheie in _restaurariOriginale:
			return
		asteapta = anuleazaTraducerea(cale)
		cerere = {"anulat": threading.Event(), "asteapta": asteapta, "nativ": _dateEroareNativa(exc)}
		_restaurariOriginale[cheie] = cerere
	fir = _FirVerificare()
	fir.originale = (cale, cheie, cerere)
	try:
		_pornesteFir(_refaceOriginalele, fir)
	except Exception:
		with _lacat:
			_restaurariOriginale.pop(cheie, None)
		raise
	_pornestePompa()


def _cereOriginaleleCadere(cale):
	"""TRD6: traducerea ceruta dupa o cadere a facut pluginul sa nu se mai incarce: originalele inapoi pe un fir de lucru, apoi
	verdictul "fara semn" pentru fisierele refacute, ca verificarea din fundal sa nu-l traduca din nou in bucla. Pe interfata
	numai cererea in memorie."""
	cheie = _cheie(cale)
	with _lacat:
		if _inchideTraducerile or cheie in _restaurariOriginale:
			return
		cerere = {"anulat": threading.Event(), "asteapta": [], "nativ": None, "cadere": True}
		_restaurariOriginale[cheie] = cerere
	fir = _FirVerificare()
	fir.originale = (cale, cheie, cerere)
	try:
		_pornesteFir(_refaceOriginalele, fir)
	except Exception as exc:
		with _lacat:
			_restaurariOriginale.pop(cheie, None)
		_jurnal("originalele dupa cadere nu s-au cerut: %r" % (exc,))
		return
	_pornestePompa()


def _refaceOriginalele(fir):
	"""Refacerea pe fir de lucru; pompa publica rezultatul pe interfata."""
	cale, cheie, cerere = fir.originale
	try:
		for activa in cerere["asteapta"]:
			while not activa["gata"].wait(0.1):
				if cerere["anulat"].is_set():
					return
		cerere["asteapta"] = []
		puneOriginalele(cale, _cerere=cerere, _nativ=cerere["nativ"])
		if cerere.get("cadere") and cerere.get("schimbat") and not cerere["anulat"].is_set():
			_tineMinteVerdict(cheie, semnatura(cale), None)
		with _lacat:
			if cerere.get("schimbat") and not cerere["anulat"].is_set() and not _inchideTraducerile:
				_fundal["gasite"].append(cheie)
	except Exception as exc:
		_jurnal("originalele nu s-au refacut: %r" % (exc,))
	finally:
		with _lacat:
			if _restaurariOriginale.get(cheie) is cerere:
				_restaurariOriginale.pop(cheie, None)
		fir.terminat()


# ---------------------------------------------------------------- legatura cu incarcarea pluginurilor

def _pluginImagine(categorie, nume):
	try:
		from Components.HdsPluginExtern import PLUGINURI_IMAGINE
		return "%s/%s" % (categorie, nume) in PLUGINURI_IMAGINE
	except Exception:
		return categorie == "Extensions" and nume.startswith("Hds")


def _scoateModulele(prefix, cale=None):
	import types
	for n, m in list(sys.modules.items()):
		fisier = m.__dict__.get("__file__") if isinstance(m, types.ModuleType) else None
		if not (n == prefix or n.startswith(prefix + ".") or
			(cale is not None and isinstance(fisier, str) and _subDosar(fisier, cale))):
			continue
		sys.modules.pop(n, None)
	try:
		import importlib
		importlib.invalidate_caches()
	except Exception:
		pass


class _ImporturiVecine(ast.NodeVisitor):
	"""importurile fara punct ale modulelor vecine din plugin (importul relativ implicit al lui Python 2), in afara unui try sau a
	unui if (acolo e de obicei rezerva pentru cealalta versiune)"""

	def __init__(self, vecine):
		self.vecine = vecine
		self.gasite = []

	def _nimic(self, _nod):
		pass

	visit_Try = _nimic
	if hasattr(ast, "TryStar"):
		visit_TryStar = _nimic

	def visit_If(self, nod):
		# un if pe versiune (sys.version_info, PY2/PY3, six) e rezerva pentru cealalta versiune; orice alt if se cerceteaza
		test = ast.dump(nod.test)
		if "version" in test or "PY2" in test or "PY3" in test or "six" in test:
			return
		self.generic_visit(nod)

	def _vezi(self, nume):
		sus = (nume or "").split(".", 1)[0]
		if sus in self.vecine and _absolutLipsa(sus):
			self.gasite.append(sus)

	def visit_Import(self, nod):
		for a in nod.names:
			self._vezi(a.name)

	def visit_ImportFrom(self, nod):
		if not nod.level:
			self._vezi(nod.module)


_absolute = {}


def _absolutLipsa(nume):
	"""True cand `import nume` (absolut) nu gaseste nimic in Python 3: atunci un modul vecin cu acelasi nume e importul relativ implicit"""
	if nume not in _absolute:
		try:
			import importlib.util
			_absolute[nume] = nume in sys.builtin_module_names or importlib.util.find_spec(nume) is None
		except (ImportError, ValueError, AttributeError):
			_absolute[nume] = True
		if nume == "__init__":
			_absolute[nume] = True
	return _absolute[nume]


# regulile verificarii din sursa (semneStatice): se mareste cand verificarea vede semne noi. 2 (0.7.6, NB2): numele vechi citite si
# nedefinite (numePython2). Altfel decat VERSIUNE: nu traduce din nou nimic din originale, numai verifica din nou.
VERSIUNE_SEMNE = 2


def semnatura(cale):
	"""suma numelor, marimilor si timpilor fisierelor .py ale pluginului (fara sa le citeasca): se schimba la orice actualizare"""
	h = hashlib.sha256()
	# NB2 (0.7.6): versiunea regulilor verificarii din sursa intra in semnatura: un plugin verificat curat cu regulile de dinainte
	# ("verificate" in STARE) se verifica o data din nou dupa actualizarea imaginii (pe firul de verificare), cu regulile noi
	h.update(b"semne %d\n" % VERSIUNE_SEMNE)
	for f in _fisierePy(cale)[:MAX_FISIERE + 1]:
		try:
			s = os.stat(f)
		except OSError:
			continue
		h.update(("%s\0%d\0%d\n" % (os.path.relpath(f, cale), s.st_size, s.st_mtime_ns)).encode("utf-8", "surrogateescape"))
	return h.hexdigest()


# formele de text care pot fi de Python 2 (filtrul de dinaintea analizei; o potrivire nu e un semn, numai un motiv de analiza):
# print fara paranteze, except X, e:, `x`, <>, 0777, ur'', exec fara paranteze, raise X, y, taburi amestecate cu spatii
_CANDIDAT = re.compile(br"^[ \t]*print(?:[ \t]+[^\s(=.]|[ \t]*$)|except[ \t]+[^:\n#]+,[ \t]*\w+[ \t]*:|`|<>|"
	br"(?<![\w.:\"'%-])0[0-7]{2,}(?![\w.:])|"
	br"\b[uU][rR]['\"]|^[ \t]*exec[ \t]+[^\s(=]|^[ \t]*raise[ \t]+[\w.]+[ \t]*,|^(?: +\t|\t+ )", re.M)

# Sirurile si comentariile nu sunt cod. Expresia include si sirurile Python 2
# ur'', pe care tokenize din Python 3 le vede ca un nume ur urmat de STRING.
_TEXT_FARA_COD = re.compile(br"(?P<ur>\b[uU][rR])?(?P<format>\b(?:[fF][rR]?|[rR][fF]))?(?:\"\"\"(?:\\[\s\S]|(?!\"\"\")[^\\])*(?:\"\"\"|\Z)|"
	br"'''(?:\\[\s\S]|(?!''')[^\\])*(?:'''|\Z)|"
	br'"(?:\\[\s\S]|[^"\\\r\n])*"|\'(?:\\[\s\S]|[^\'\\\r\n])*\')|\#[^\r\n]*')


def _numaiCod(date):
	"""Mascheaza continutul sirurilor si comentariile, pastrand randurile si ur."""
	def ascunde(m):
		s = m.group()
		if m.group("format"):
			return _codSirFormatat(s)
		nou = re.sub(br"[^\r\n]", b" ", s)
		if m.group("ur"):
			return s[:3] + nou[3:]
		# Un operand sir trebuie sa ramana vizibil pentru print/exec fara paranteze.
		if not s.startswith(b"#"):
			return b"x" + nou[1:]
		return nou
	return _TEXT_FARA_COD.sub(ascunde, date)


def _codSirFormatat(s):
	"""In f-string numai expresiile sunt cod, nu textul afisat."""
	import tokenize
	if not hasattr(tokenize, "FSTRING_START"):
		return s  # Python mai vechi: filtru conservator, fara semne pierdute.
	text = s.decode("latin-1")
	randuri = text.splitlines(True)
	offset = [0]
	for r in randuri:
		offset.append(offset[-1] + len(r))
	nou = bytearray(re.sub(br"[^\r\n]", b" ", s))
	try:
		for t in tokenize.generate_tokens(io.StringIO(text).readline):
			if t.type in (tokenize.NAME, tokenize.NUMBER, tokenize.OP, tokenize.ERRORTOKEN):
				a, b = offset[t.start[0] - 1] + t.start[1], offset[t.end[0] - 1] + t.end[1]
				nou[a:b] = s[a:b]
	except (tokenize.TokenError, IndentationError, IndexError):
		return s
	return bytes(nou)


TIMP_DEPASIT = ("", "timpul")   # verificarea din sursa oprita de timp (nu terminata)


def semneStatice(cale, timp_maxim=30.0, de_la=0, la_pas=None, pauza=0.0):
	"""(fisierul, motivul) cand sursa pluginului arata cod de Python 2 care nu cade la import (in functii): sintaxa lui Python 2
	dupa gramatica 3.13 (Python 3.14 primeste iar `except X, e:`, cu alt inteles), importuri de module scoase din Python 3,
	importuri relative implicite, nume vechi citite si nedefinite (NB2: "nume Python 2 file"); altfel None; TIMP_DEPASIT cand s-a
	oprit la timp_maxim. Numai citire si analiza, nimic rulat.
	HDSatelit 0.7.6 (FRZ, raportul 2150): de_la = cate fisiere (in ordinea lui _fisierePy) sunt deja verificate fara semn, de la o
	citire de dinainte oprita de timp: se sar; la_pas(n) se cheama dupa fiecare fisier verificat fara semn (n = cate sunt gata), ca
	progresul sa se tina minte; pauza (secunde) dupa fiecare fisier analizat, cand ruleaza pe firul de verificare: lacatul Python
	ajunge la firul interfetei intre doua fisiere."""
	try:
		from Components.HdsPython2 import din_sursa_arbore
	except Exception:
		return None
	inceput = time.monotonic()
	fisiere = _fisierePy(cale)
	if len(fisiere) > MAX_FISIERE:
		return None
	vecine = _moduleVecine(cale)
	# filtrul ieftin (masurat pe receptorul de proba: analiza completa a 14 pluginuri dura 43 s pe ARM): un fisier se analizeaza numai cand textul
	# lui are o forma care poate fi de Python 2 sau un import al unui modul vecin ori al unui modul de Python 2
	try:
		from Components.HdsPython2 import MODULE_PY2
	except Exception:
		MODULE_PY2 = frozenset()
	nume_imp = sorted(n for n in (set(vecine) | set(MODULE_PY2)) if re.match(r"^\w+$", n))
	imp = re.compile(br"^[ \t]*(?:from|import)[ \t]+(?:" + b"|".join(re.escape(n.encode("ascii", "ignore")) for n in nume_imp) +
		br")\b|\burllib\.(?:urlopen|urlencode|quote|unquote|urlretrieve)\b|^[ \t]*from[ \t]+urllib[ \t]+import", re.M) if nume_imp else None
	vecine_dosar = {}       # dosarul -> vecineDosar(dosar), o data pe verificare (inainte: la fiecare fisier cu importuri)
	for i, f in enumerate(fisiere):
		if i < de_la:
			continue
		if i > de_la and la_pas is not None:
			la_pas(i)
		if time.monotonic() - inceput > timp_maxim:
			return TIMP_DEPASIT
		try:
			with open(f, "rb") as fh:
				date = fh.read(MAX_OCTETI + 1)
		except OSError:
			continue
		if len(date) > MAX_OCTETI:
			continue
		cod = _numaiCod(date)
		forma = _CANDIDAT.search(cod) is not None
		importuri = imp is not None and imp.search(cod) is not None
		nume_vechi = _NUME_CANDIDAT.search(cod) is not None
		if not (forma or importuri or nume_vechi):
			continue
		rel = os.path.relpath(f, cale).replace("\\", "/")
		r, arbore = din_sursa_arbore(date, f)
		if pauza:
			time.sleep(pauza)
		if r is not None:
			return rel, "%s %s" % r
		if not (importuri or nume_vechi) or arbore is None:
			continue
		try:
			if eScriptFisier(date, f):
				continue
			# NB2 (0.7.6): nume vechi citit si nedefinit (NeoBoot files/devices.py `open = file`), din acelasi arbore
			n = numePython2(arbore) if nume_vechi else None
			if n:
				return rel, "nume Python 2 %s" % n
			if not importuri:
				continue
			dosar = os.path.dirname(f)
			if dosar not in vecine_dosar:
				vecine_dosar[dosar] = vecineDosar(dosar)
			v = _ImporturiVecine(vecine_dosar[dosar])
			v.visit(arbore)
		except (SyntaxError, ValueError, TypeError, RecursionError, MemoryError, UnicodeError):
			continue
		if v.gasite:
			return rel, "import relativ implicit %s" % v.gasite[0]
	return None


# cat poate lua verificarea din sursa intr-o citire a listei de pluginuri, cand ruleaza pe firul care citeste lista (FUNDAL False):
# masurat pe receptorul de proba ~0,1 s pe fisier; ce nu incape se verifica la citirea urmatoare, de unde a ramas (STARE "progres")
BUGET_CITIRE_S = 20.0
_buget = {"ramas": BUGET_CITIRE_S}

# HDSatelit 0.7.6 (FRZ, rapoartele 2150 si 2136, Uno 4K SE si SF8008, 0.7.5): verificarea din sursa a tinut firul interfetei 20,2 s si
# 22,1 s (ast.parse <- Ipkg.cmdFinished: dupa fiecare opkg din Extensii lista pluginurilor se citeste din nou) si 21,4 s la pornire
# ("TiviMateE2 (import)"): tot bugetul de 20 s, la FIECARE citire, fiindca un plugin mare nu se termina in buget, semnatura nu se scria
# si verificarea o lua de la primul fisier. Acum: pe receptor (FUNDAL) verificarea merge pe un fir de lucru, dupa citire; progresul se
# tine minte in STARE ("progres", pe semnatura); semnul gasit se tine minte ("semne") si lista se citeste din nou pe firul interfetei,
# unde traducerea si importul din nou merg ca pana acum. FUNDAL False (probele vechi de pe PC): verificarea pe loc, cu bugetul.
FUNDAL = True
INTARZIERE_FUNDAL_S = 60.0        # firul asteapta atat inainte de primul plugin (pornirea interfetei tine 40-50 s pe ARM)
PAUZA_FUNDAL_S = 0.1              # dupa fiecare fisier analizat (~0,1 s): lacatul Python e jumatate din timp al interfetei
TIMP_FUNDAL_S = 600.0             # un plugin pe firul de lucru; ce ramane se reia de unde a ramas, la citirea urmatoare
# FRZ 0.7.7 (pachetul de testeri 2445, Vu+ Uno 4K SE 0.7.6: 18,2 s in ast.parse <- HdsPython2.din_sursa_arbore <- pompa): dupa un
# semn gasit in fundal, dupaImport traducea pluginul (o analiza si fissix pe fiecare fisier, ~400 la IPTVplayer) PE FIRUL INTERFETEI,
# in citirea ceruta de pompa. Acum traducerea se face tot pe firul de verificare, cu pauza intre fisiere si timpul ei (ceasul merge
# si in pauze si cat firul asteapta lacatul, deci mai lung decat TIMP_MAXIM); pe firul interfetei raman scoaterea modulelor si
# importul din nou al pluginului tradus (acelasi cost ca importul lui la pornire).
TIMP_TRADUCERE_FUNDAL_S = 900.0
PAS_PROGRES_S = 5.0               # progresul se scrie in STARE cel mult o data la atatea secunde
PAS_POMPA_MS = 2000               # ceasul de pe firul interfetei care vede semnele gasite in fundal
NICE_FUNDAL = 10
_fundal = {"fir": None, "acum": None, "coada": [], "gasite": [], "pompa": None, "traduse": {}}
# FRD (pachetul 2206: 6,7 s in semnatura <- ActionMap.action): semnatura unui plugin (os.walk si cate un stat pe fiecare .py,
# pana la 401) se face numai pe firul de verificare; aici ramane, in memoria procesului, cheie -> (semnul usor, semnatura).
# Semnul usor e statul lui plugin.py (inode, marime, ora): opkg scrie din nou toate fisierele pachetului la orice instalare
# sau actualizare, deci si plugin.py. Un fisier schimbat de mana fara plugin.py se vede la pornirea urmatoare a interfetei.
_semnaturi = {}
_citireInitiala = True


def _semnUsor(st):
	return (getattr(st, "st_ino", 0), st.st_size, st.st_mtime_ns)


def incepeCitirea():
	"""Din Components/PluginComponent.py, la inceputul fiecarei citiri a listei de pluginuri: bugetul verificarii din sursa"""
	global _citireInitiala
	# Pastreaza faza citirii: firstRun devine False inainte sa termine copilul.
	componenta = sys.modules.get("Components.PluginComponent")
	_citireInitiala = bool(getattr(getattr(componenta, "plugins", None), "firstRun", False))
	_buget["ramas"] = BUGET_CITIRE_S


def _progres(stare, cheie, sem):
	"""cate fisiere ale pluginului sunt deja verificate fara semn (pentru aceeasi semnatura), altfel 0"""
	p = (stare.get("progres") or {}).get(cheie) or {}
	try:
		return int(p.get("fisiere", 0)) if p.get("sem") == sem else 0
	except (TypeError, ValueError):
		return 0


def _tineMinteProgres(cheie, sem, n):
	def schimba(stare):
		stare.setdefault("progres", {})[cheie] = {"sem": sem, "fisiere": int(n)}
		return True
	_actualizeaza(schimba)


def _tineMinteVerdict(cheie, sem, semn):
	"""semn None: pluginul e curat (verificate); altfel semnul gasit, pana la traducere (semne). Progresul se uita."""
	def schimba(stare):
		stare.setdefault("progres", {}).pop(cheie, None)
		if semn is None:
			stare.setdefault("verificate", {})[cheie] = sem
			stare.setdefault("semne", {}).pop(cheie, None)
		else:
			stare.setdefault("semne", {})[cheie] = {"sem": sem, "semn": [semn[0], semn[1]]}
		return True
	_actualizeaza(schimba)


def _semnPastrat(stare, cheie, sem):
	"""semnul gasit de firul de verificare pentru aceeasi semnatura, ca tuplu, altfel None"""
	g = (stare.get("semne") or {}).get(cheie) or {}
	if g.get("sem") != sem:
		return None
	s = g.get("semn") or ["?", "?"]
	return (str(s[0]), str(s[1] if len(s) > 1 else ""))


def _verificaPeLoc(categorie, nume, cale, cheie, sem, stare):
	"""verificarea pe firul care citeste lista (FUNDAL False), in bugetul citirii, reluata de unde a ramas"""
	if _buget["ramas"] <= 0:
		# bugetul acestei citiri s-a dus (prima pornire dupa actualizare, multe pluginuri): pluginul se verifica la citirea urmatoare
		return TIMP_DEPASIT
	gata = [_progres(stare, cheie, sem)]
	t0 = time.monotonic()
	semn = semneStatice(cale, timp_maxim=max(1.0, _buget["ramas"]), de_la=gata[0], la_pas=lambda n: gata.__setitem__(0, n))
	durata = time.monotonic() - t0
	_buget["ramas"] -= durata
	if durata > 0.5:
		_jurnal("%s/%s: verificarea din sursa %.1f s" % (categorie, nume, durata))
	if semn is TIMP_DEPASIT:
		_tineMinteProgres(cheie, sem, gata[0])
	return semn


def _ePrincipal():
	return threading.current_thread() is threading.main_thread()


NUME_FIR = "HdsPython2Verificare"


class _FirVerificare(object):
	"""Manerul firului de verificare (in locul lui threading.Thread): ruleaza pana la sfarsitul lui _lucreaza; join si is_alive
	fara lacatul firului (MI8)."""
	name = NUME_FIR

	def __init__(self):
		self._gata = threading.Event()

	def is_alive(self):
		return not self._gata.is_set()

	def join(self, timeout=None):
		self._gata.wait(timeout)

	def terminat(self):
		self._gata.set()


def _pornesteFir(tinta, fir):
	"""Firul nou fara asteptarea pornirii lui: threading.Thread.start asteapta ca firul nou sa primeasca lacatul Python, iar
	cat il tine alt fir, interfata sta (FRD, ca HdsStareOsd.Cititor). Probele il pot inlocui."""
	_fire_joase.start_new_thread(tinta, (fir,))


def _cereVerificarea(categorie, nume, cale, cheie, sem, usor=None, reia=False):
	"""pune pluginul la coada firului de verificare (o data) si porneste firul, daca nu ruleaza. sem None: semnatura o afla
	firul (FRD), cu semnul usor `usor` pentru memoria _semnaturi. Firul porneste fara threading.Thread.start (MI8: start
	astepta lacatul Python, o data pe citirea listei cand firul nu rula)."""
	fir_nou = None
	with _lacat:
		if _inchideTraducerile:
			return
		if ((_fundal["acum"] == cheie and not reia) or any(c[3] == cheie for c in _fundal["coada"])
			or cheie in _proceseTraducere or cheie in _publicariTraducere
			or cheie in _validariTraducere or cheie in _publicariGata):
			return
		_anulateTraducere.discard(cheie)
		_fundal["coada"].append((categorie, nume, cale, cheie, sem, usor))
		fir = _fundal["fir"]
		if fir is None or not fir.is_alive():
			fir_nou = _FirVerificare()
			_fundal["fir"] = fir_nou
	if fir_nou is not None:
		try:
			_pornesteFir(_lucreaza, fir_nou)
		except Exception as e:
			_jurnal("firul verificarii nu a pornit: %r" % (e,))
			with _lacat:
				if _fundal["fir"] is fir_nou:
					_fundal["fir"] = None
			fir_nou.terminat()
	_pornestePompa()


def _lucreaza(fir=None):
	"""firul de verificare: pluginurile din coada, unul cate unul; nimic din enigma (numai fisiere si STARE)"""
	try:
		try:
			threading.current_thread().name = NUME_FIR
		except Exception:
			pass
		try:
			os.setpriority(os.PRIO_PROCESS, threading.get_native_id(), NICE_FUNDAL)
		except (AttributeError, OSError):
			pass
		if INTARZIERE_FUNDAL_S > 0 and not any(len(c) < 3 for c in list(_cereriCadere.values())):
			# TRD6: dupa o cadere la rulare omul asteapta pluginul tradus; asteptarea e numai pentru pornirea interfetei
			time.sleep(INTARZIERE_FUNDAL_S)
		while True:
			with _lacat:
				if not _fundal["coada"]:
					if _fundal["fir"] is fir or fir is None:
						_fundal["fir"] = None
					_fundal["acum"] = None
					return
				categorie, nume, cale, cheie, sem, usor = _fundal["coada"].pop(0)
				_fundal["acum"] = cheie
			try:
				_verificaInFundal(categorie, nume, cale, cheie, sem, usor)
			except Exception as e:
				_jurnal("%s/%s: verificarea din fundal a cazut: %r" % (categorie, nume, e))
	finally:
		if fir is not None:
			with _lacat:
				if _fundal["fir"] is fir:
					_fundal["fir"] = None
			fir.terminat()


def _verificaInFundal(categorie, nume, cale, cheie, sem, usor=None):
	with _lacat:
		if _inchideTraducerile or cheie in _anulateTraducere:
			return
		cerere_import = _cereriImportTraducere.pop(cheie, None)
		cerere_cadere = _cereriCadere.pop(cheie, None)
	if cerere_cadere is not None and cerere_import is None:
		# TRD6: cadere "python2" la rulare: tot pluginul, si fisierele care se compileaza in Python 3 (traduceDupaCadere)
		if not motorDisponibil():
			# fara python3-fissix cererea ramane (si mesajul promis); prima data rezultatul FARA_MOTOR ajunge la dupaImport,
			# care cere motorul (Components/HdsModuleLipsa.py); citirea listei de dupa instalare o ia de aici, fara alta cadere.
			# Urmatoarele treceri fara motor nu mai publica nimic (fara citiri ale listei in bucla).
			with _lacat:
				if not _inchideTraducerile and cheie in _cadereAnunt:
					_cereriCadere[cheie] = cerere_cadere[:2] + ("motor",)
					if len(cerere_cadere) < 3:
						_fundal["traduse"][cheie] = (Rezultat(FARA_MOTOR), cerere_cadere[:2])
						_fundal["gasite"].append(cheie)
			return
		# pluginul s-a incarcat in Python 3: regula de acum (tot=None), deci fisierele lui de Python 3 raman neatinse
		_jurnal("%s/%s: cadere Python 2 la rulare (%s): traduc partile vechi ale pluginului" % (categorie, nume, cerere_cadere[1]))
		_traduceInFundal(categorie, nume, cale, cheie, cerere_cadere[:2])
		return
	nativ = _nativPastrat(cale)
	if nativ is not None:
		with _lacat:
			if cerere_import is not None and not _inchideTraducerile and cheie not in _anulateTraducere:
				_importuriDeActivat.discard(cheie)
				_fundal["traduse"][cheie] = (Rezultat("nativ_incompatibil", detalii=nativ), None)
				_fundal["gasite"].append(cheie)
		return
	if cerere_import is not None:
		e = intrare(cale)
		vechi = bool(e and e.get("stare") == TRADUS and e.get("versiune") != VERSIUNE)
		semn = vechi or semnPython2(cerere_import[2], cale)
		if not semn and cerere_import[4] is None:
			with _lacat:
				_importuriDeActivat.discard(cheie)
			return
		_traduceInFundal(categorie, nume, cale, cheie, cerere_import[:2], echec=cerere_import[2],
			importa=cerere_import[3], verificat=cerere_import[4], forteaza=bool(semn))
		return
	proaspata = semnatura(cale)
	if proaspata != sem:
		# FRD: semnatura se afla aici, nu pe firul care citeste lista (sem None: prima data; alta: pluginul s-a schimbat de la
		# cerere, si un .py schimbat fara plugin.py); memoria se face din nou, apoi ce stie STARE pentru semnatura de acum
		sem = proaspata
		with _lacat:
			_semnaturi[cheie] = (usor, sem)
		stare = _citesteStare()
		if stare.get("verificate", {}).get(cheie) == sem:
			return
	else:
		stare = _citesteStare()
	semn = _semnPastrat(stare, cheie, sem)
	if semn is not None:
		# semnul gasit inainte (alta citire, alta pornire a interfetei): traducerea tot aici (FRZ 0.7.7)
		_traduceInFundal(categorie, nume, cale, cheie, semn)
		return
	gata = [_progres(stare, cheie, sem)]
	scris = [time.monotonic()]

	def la_pas(n):
		gata[0] = n
		if time.monotonic() - scris[0] >= PAS_PROGRES_S:
			scris[0] = time.monotonic()
			_tineMinteProgres(cheie, sem, n)

	t0 = time.monotonic()
	in_proces, semn = _semneInProces(cale, TIMP_FUNDAL_S, gata[0], la_pas)
	with _lacat:
		if _inchideTraducerile or cheie in _anulateTraducere:
			return
	if not in_proces:
		semn = semneStatice(cale, timp_maxim=TIMP_FUNDAL_S, de_la=gata[0], la_pas=la_pas, pauza=PAUZA_FUNDAL_S)
	durata = time.monotonic() - t0
	if durata > 0.5:
		_jurnal("%s/%s: verificarea din sursa (in fundal%s) %.1f s" % (categorie, nume, ", proces separat" if in_proces else "",
			durata))
	if semn is TIMP_DEPASIT:
		_tineMinteProgres(cheie, sem, gata[0])
		return
	if semnatura(cale) != sem:
		return
	_tineMinteVerdict(cheie, sem, semn)
	if semn is not None:
		_jurnal("%s/%s: cod de Python 2 in %s (%s), gasit in fundal: il traduc tot aici" % (categorie, nume, semn[0], semn[1]))
		_traduceInFundal(categorie, nume, cale, cheie, semn)


# PLG 0.7.7 (masurat pe Octagonul SF8008 de proba, cu GT IPTV Player Pro 1.9.4 instalat): ast.parse e un apel C care tine lacatul
# Python cat analizeaza. Pe firul de verificare fisierele mari ale lui GTI (main.py 376 KB: 1,79 s pe ARM, inca 4 peste 1 s)
# opreau firul interfetei de 8-9 ori cate 1-3 s in cele 45-60 s ale verificarii (o data dupa instalare, actualizare sau
# actualizarea imaginii). Acum verificarea din sursa merge intr-un proces python3 separat (nice 10, alt interpretor, fara
# lacatul lui enigma2; ~37 MB de memorie cat tine, masurat pe GTI): firul de verificare doar citeste ce scrie procesul (pasii,
# pentru progres, si semnul). Fara python3, cand procesul nu porneste sau nu scrie semnul, verificarea merge pe fir, ca pana
# acum. Traducerea (numai pluginurile chiar scrise in Python 2, rare) ramane pe firul de verificare.
PYTHON3 = "/usr/bin/python3"      # niciodata sys.executable: in enigma2 nu e un interpretor
PROCES = True
TIMP_PROCES_IN_PLUS_S = 60.0      # procesul se opreste singur la TIMP_FUNDAL_S; dupa inca atat il opreste firul
_COPIL = """import json, os, sys
radacina, cale, de_la, timp, parinte = sys.argv[1], sys.argv[2], int(sys.argv[3]), float(sys.argv[4]), int(sys.argv[5])
try:
    os.nice(max(0, 10 - os.nice(0)))
except Exception:
    pass
sys.path.insert(0, radacina)
import builtins
if not hasattr(builtins, "_"):
    builtins._ = lambda s: s
from Components import HdsPython2Traducere as T
def pas(n):
    if os.getppid() != parinte:
        sys.exit(0)
    sys.stdout.write("pas %d\\n" % n)
    sys.stdout.flush()
s = T.semneStatice(cale, timp_maxim=timp, de_la=de_la, la_pas=pas)
sys.stdout.write("semn %s\\n" % json.dumps(None if s is None else list(s)))
sys.stdout.flush()
"""


def _semneInProces(cale, timp_maxim, de_la, la_pas):
	"""semneStatice intr-un proces python3 separat: (True, semnul) sau (False, None) cand nu s-a putut (verificarea merge atunci
	pe fir). la_pas(n) se cheama pe firul acesta, pe masura ce procesul scrie pasii."""
	if not PROCES or not os.access(PYTHON3, os.X_OK):
		return False, None
	import subprocess
	radacina = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
	try:
		p = subprocess.Popen([PYTHON3, "-I", "-B", "-c", _COPIL, radacina, cale, str(int(de_la)), repr(float(timp_maxim)),
			str(os.getpid())], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, close_fds=True)
	except (OSError, ValueError) as e:
		_jurnal("verificarea in proces separat nu a pornit: %r" % (e,))
		return False, None
	ceas = threading.Timer(timp_maxim + TIMP_PROCES_IN_PLUS_S, p.kill)
	ceas.daemon = True
	ceas.start()
	cheie = _cheie(cale)
	with _lacat:
		_proceseVerificare[cheie] = p
		if _inchideTraducerile or cheie in _anulateTraducere:
			p.kill()
	gasit, semn = False, None
	try:
		for rand in p.stdout:
			rand = rand.decode("utf-8", "replace").strip()
			if rand.startswith("pas "):
				try:
					la_pas(int(rand[4:]))
				except ValueError:
					pass
			elif rand.startswith("semn "):
				try:
					v = json.loads(rand[5:])
				except ValueError:
					continue
				if v is None or (isinstance(v, list) and len(v) == 2):
					gasit, semn = True, (None if v is None else (str(v[0]), str(v[1])))
	finally:
		ceas.cancel()
		try:
			p.stdout.close()
		except Exception:
			pass
		try:
			p.wait(10)
		except Exception:
			p.kill()
			try:
				p.wait(5)
			except Exception:
				pass
		with _lacat:
			if _proceseVerificare.get(cheie) is p:
				_proceseVerificare.pop(cheie, None)
	with _lacat:
		if _inchideTraducerile or cheie in _anulateTraducere:
			return True, TIMP_DEPASIT
	if not gasit:
		_jurnal("verificarea in proces separat nu a dat semnul (cod %s): o fac pe fir" % (p.returncode,))
		return False, None
	if semn == TIMP_DEPASIT:
		semn = TIMP_DEPASIT
	return True, semn


_proceseTraducere = {}
_proceseVerificare = {}
_anulateTraducere = set()
_publicariTraducere = {}
_validariTraducere = {}
_publicariGata = {}
_importuriDeActivat = set()
_asteaptaActivarea = set()
_cereriImportTraducere = {}
# TRD6 (MI9): caderile cu cauza "python2" la rulare (Components/HdsPluginExtern.py). _cereriCadere: cheie -> semnul, pentru
# firul de verificare (traducerea intregului plugin); _cadereCerute: cheile cerute in sesiunea interfetei (o data pe plugin);
# _cadereAnunt: cheile care asteapta mesajul pentru om dupa traducere (dupaImport, pe firul interfetei)
_cereriCadere = {}
_cadereCerute = set()
_cadereAnunt = {}
_inchideTraducerile = False
MEMORIE_TRADUCERE = 512 * 1024 * 1024
MAX_PLAN_TRADUCERE = 64 * 1024 * 1024
_REIMPORT = "reimport-verificat"


class _SchimbariPlugin:
	"""Notificari ale nucleului, fara citiri de disc la interogarea de pe interfata."""
	def __init__(self, cale, recursiv=True):
		import ctypes
		self.maner = None
		self.schimbare = False
		self.recursiv = recursiv
		self.program = None
		self.terminat = threading.Event()
		if sys.platform == "win32":
			from ctypes import wintypes
			class Overlapped(ctypes.Structure):
				_fields_ = [("Internal", ctypes.c_size_t), ("InternalHigh", ctypes.c_size_t),
					("Offset", wintypes.DWORD), ("OffsetHigh", wintypes.DWORD), ("hEvent", wintypes.HANDLE)]
			self.api = ctypes.WinDLL("kernel32", use_last_error=True)
			self.api.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
				wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
			self.api.CreateFileW.restype = wintypes.HANDLE
			self.api.CreateEventW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
			self.api.CreateEventW.restype = wintypes.HANDLE
			self.api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
			self.api.CloseHandle.argtypes = [wintypes.HANDLE]
			self.api.CancelIoEx.argtypes = [wintypes.HANDLE, wintypes.LPVOID]
			self.api.GetOverlappedResult.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.LPVOID, wintypes.BOOL]
			self.api.ReadDirectoryChangesW.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD,
				wintypes.BOOL, wintypes.DWORD, wintypes.LPVOID, wintypes.LPVOID, wintypes.LPVOID]
			h = self.api.CreateFileW(cale, 1, 7, None, 3, 0x42000000, None)
			if h in (None, ctypes.c_void_p(-1).value):
				raise OSError("notificarile pluginului nu au pornit")
			self.maner = h
			self.operatie = Overlapped()
			self.operatie.hEvent = self.api.CreateEventW(None, True, False, None)
			self.tampon = ctypes.create_string_buffer(65536)
			if not self.operatie.hEvent or not self.api.ReadDirectoryChangesW(h, self.tampon,
				len(self.tampon), recursiv, 0x1F, None, ctypes.byref(self.operatie), None):
				self.elibereaza()
				raise OSError("coada notificarilor nu a pornit")
		elif sys.platform.startswith("linux"):
			self.api = ctypes.CDLL(None, use_errno=True)
			self.api.inotify_add_watch.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32]
			fd = self.api.inotify_init1(os.O_NONBLOCK | os.O_CLOEXEC)
			if fd < 0:
				raise OSError("notificarile pluginului nu au pornit")
			self.maner = fd
			try:
				for rad, dosare, _fisiere in (os.walk(cale) if recursiv else [(cale, [], [])]):
					dosare[:] = [d for d in dosare if d != "__pycache__" and not os.path.islink(os.path.join(rad, d))]
					if len(dosare) > MAX_FISIERE * 6:
						raise OSError("prea multe dosare pentru notificari")
					if self.api.inotify_add_watch(fd, os.fsencode(rad), 0xFC6) < 0:
						raise OSError("notificarile unui dosar nu au pornit")
			except Exception:
				self.elibereaza()
				raise
		else:
			raise OSError("notificarile pluginului nu sunt disponibile")

	def schimbat(self):
		if self.maner is None or self.schimbare or self.terminat.is_set():
			return True
		if self.program is not None and self.program.schimbat():
			self.schimbare = True
			return True
		if sys.platform == "win32":
			self.schimbare = self.api.WaitForSingleObject(self.operatie.hEvent, 0) != 258
		else:
			import struct
			try:
				for _lot in range(4):
					# Coada de evenimente a nucleului, nu fisierele pluginului.
					date = os.read(self.maner, 65536)
					if not date:
						self.schimbare = True
						break
					poz = 0
					while poz < len(date):
						_wd, masca, _cookie, n = struct.unpack_from("iIII", date, poz)
						nume = date[poz + 16:poz + 16 + n].split(b"\0", 1)[0]
						poz += 16 + n
						if not self.recursiv or (masca & 0xEC00) or (masca & 0x40000000 and nume != b"__pycache__") or nume.endswith((b".py", b".py2", b".so", b".pyd")):
							self.schimbare = True
					if self.schimbare:
						break
				else:
					self.schimbare = True
			except BlockingIOError:
				pass
			except OSError:
				self.schimbare = True
		return self.schimbare

	def inchide(self):
		# Firul interfetei semnaleaza doar; eliberarea nativa poate astepta discul.
		self.terminat.set()
		if self.program is not None:
			self.program.inchide()

	def elibereaza(self):
		if self.program is not None:
			self.program.elibereaza()
		maner, self.maner = self.maner, None
		if maner is not None:
			if sys.platform == "win32":
				import ctypes
				from ctypes import wintypes
				n = wintypes.DWORD()
				self.api.CancelIoEx(maner, ctypes.byref(self.operatie))
				self.api.GetOverlappedResult(maner, ctypes.byref(self.operatie), ctypes.byref(n), True)
				self.api.CloseHandle(maner)
				if self.operatie.hEvent:
					self.api.CloseHandle(self.operatie.hEvent)
			else:
				os.close(maner)
		self.terminat.set()


def _pazesteImportul(notificari):
	"""Numai in fundal: CM3 si notificari pana la consumul de pe principal."""
	import importlib
	HdsPluginExtern = importlib.import_module("Components.HdsPluginExtern")
	if HdsPluginExtern.imagineSchimbataPeDisc():
		return False
	try:
		cale = os.readlink(getattr(HdsPluginExtern, "EXECUTABIL_PORNIT", "/proc/self/exe"))
	except (OSError, ValueError, NotImplementedError):
		# Pe PC nu ruleaza enigma2; contractul CM3 ramane acelasi.
		cale = ""
	if os.path.basename(cale.removesuffix(" (deleted)")) == "enigma2":
		notificari.program = _SchimbariPlugin(os.path.dirname(cale.removesuffix(" (deleted)")), recursiv=False)
	# Acopera si inlocuirea programului dinaintea armarii notificarii.
	return not HdsPluginExtern.imagineSchimbataPeDisc()


def _amprentaTraducere(cale):
	"""Metadate precise, inclusiv originale si module native; fara urmarit legaturi."""
	rez = []
	if os.path.islink(cale) or not os.path.isdir(cale):
		raise OSError("dosarul pluginului nu este sigur")
	s = os.stat(cale)
	rez.append([".", s.st_ino, 0, 0, 0, s.st_mode])
	for rad, dosare, fisiere in os.walk(cale):
		dosare[:] = sorted(d for d in dosare if d != "__pycache__")
		for n in dosare + sorted(fisiere):
			f = os.path.join(rad, n)
			if os.path.islink(f):
				if n.endswith((".py", ".py2")):
					raise OSError("legatura in sursele pluginului")
				continue
			if n in dosare or n.endswith((".py", ".py2", ".so", ".pyd")):
				s = os.stat(f)
				rez.append([os.path.relpath(f, cale), s.st_ino, 0 if n in dosare else s.st_size,
					0 if n in dosare else s.st_mtime_ns, 0 if n in dosare else s.st_ctime_ns, s.st_mode])
				if len(rez) > MAX_FISIERE * 6:
					raise OSError("prea multe fisiere in plugin")
	return rez


def anuleazaTraducerea(cale=None):
	"""Anuleaza o cerere sau inchide traducerile; copilul este oprit si cules."""
	global _inchideTraducerile
	cheie = _cheie(cale) if cale is not None else None
	anulate = []
	with _lacat:
		if cheie is None:
			_inchideTraducerile = True
		else:
			_anulateTraducere.add(cheie)
		for k, cerere in list(_restaurariOriginale.items()):
			if cheie is None or k == cheie:
				cerere["anulat"].set()
		for k, p in list(_proceseVerificare.items()):
			if cheie is None or k == cheie:
				try:
					p.kill()
				except OSError:
					pass
		for k, cerere in list(_proceseTraducere.items()):
			if cheie is None or k == cheie:
				anulate.append(cerere)
				cerere["anulat"].set()
				p = cerere.get("proces")
				if p is not None and p.poll() is None:
					try:
						p.kill()
					except OSError:
						pass
		for k in list(_publicariTraducere):
			if cheie is None or k == cheie:
				_publicariTraducere.pop(k)[2][4]["anulat"].set()
		for registru in (_validariTraducere, _publicariGata):
			for k, v in list(registru.items()):
				if cheie is None or k == cheie:
					v[2][4]["anulat"].set()
					if registru is _publicariGata:
						v[4].inchide()
						registru.pop(k, None)
		_importuriDeActivat.difference_update([k for k in _importuriDeActivat if cheie is None or k == cheie])
		_asteaptaActivarea.difference_update([k for k in _asteaptaActivarea if cheie is None or k == cheie])
		for k in list(_fundal["traduse"]):
			if cheie is None or k == cheie:
				_fundal["traduse"].pop(k, None)
		for registru in (_cereriImportTraducere, _cereriCadere, _cadereAnunt):
			for k in list(registru):
				if cheie is None or k == cheie:
					registru.pop(k, None)
		_fundal["gasite"][:] = [k for k in _fundal["gasite"] if cheie is not None and k != cheie]
		_fundal["coada"][:] = [c for c in _fundal["coada"] if cheie is not None and c[3] != cheie]
	return anulate


_COPIL_TRADUCERE = '''import sys
sys.path.insert(0, sys.argv[1])
if sys.argv[2]:
    sys.path.insert(0, sys.argv[2])
from Components import HdsPython2Traducere as T
T._pregatesteTraducerea(sys.argv[3], float(sys.argv[4]), int(sys.argv[5]))
'''


def _dovadaImport(exc, cale):
	"""Pe firul de lucru: numai sintaxa intrarii, fara presupuneri despre dependente."""
	sintaxa = []
	intrari = {os.path.abspath(os.path.join(cale, n)) for n in ("plugin.py", "__init__.py")}
	for eroare in _lant(exc):
		# Un modul conditionat poate sa nu mai fie importat dupa actualizare.
		if isinstance(eroare, SyntaxError) and eroare.filename and os.path.abspath(eroare.filename) in intrari:
			sintaxa.append(eroare.filename)
	return {"sintaxa": sintaxa}


def _importNeschimbat(cale, dovada):
	"""Numai in copil: sintaxa actuala; stiva nu confirma modulele deja importate."""
	def citeste(f):
		if not _subDosar(f, cale) or os.path.islink(f):
			raise OSError("sursa importului nu este sigura")
		with open(f, "rb") as fh:
			date = fh.read(MAX_OCTETI + 1)
		if len(date) > MAX_OCTETI:
			raise OSError("sursa importului este prea mare")
		return compile(date, f, "exec", dont_inherit=True)
	try:
		# O eroare de sintaxa veche nu este dovada despre versiunea de acum.
		for f in dovada["sintaxa"]:
			try:
				citeste(f)
			except SyntaxError as exc:
				if semnPython2(exc, cale):
					return True
	except (OSError, SyntaxError, ValueError, TypeError):
		return False
	return False


def _pregatesteTraducerea(dosar, timp, parinte):
	"""Intrarea copilului izolat: resurse limitate, numai analiza sursei."""
	import math
	if sys.platform.startswith("linux"):
		# Kernelul opreste copilul si daca parintele moare in timpul unui apel C.
		import ctypes
		import signal
		if ctypes.CDLL(None, use_errno=True).prctl(1, signal.SIGKILL, 0, 0, 0) != 0:
			raise OSError("paza procesului copil nu a pornit")
		if os.getppid() != parinte:
			return
	try:
		import resource
		resource.setrlimit(resource.RLIMIT_AS, (MEMORIE_TRADUCERE, MEMORIE_TRADUCERE))
		resource.setrlimit(resource.RLIMIT_CPU, (max(1, int(math.ceil(timp))), max(2, int(math.ceil(timp)) + 1)))
		resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_PLAN_TRADUCERE, MAX_PLAN_TRADUCERE))
		resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
		os.nice(max(0, NICE_FUNDAL - os.nice(0)))
	except ImportError:
		pass  # PC Windows: termenul este impus si de parinte.
	def paznic():
		limita = time.monotonic() + timp
		while time.monotonic() < limita and os.getppid() == parinte:
			time.sleep(0.1)
		os._exit(124)
	threading.Thread(target=paznic, daemon=True).start()
	with open(os.path.join(dosar, "cerere.json"), encoding="utf-8") as f:
		cerere = json.load(f)
	cale = cerere["cale"]
	if _amprentaTraducere(cale) != cerere["amprenta"]:
		return
	_citeste = cerere["stare"]
	global _citesteStare
	_citesteStare = lambda: _citeste
	plan = {}
	tot = cerere["tot"]
	dovada = cerere.get("import")
	if dovada is not None:
		# La o cerere depasita ramane numai analiza sursei actuale.
		tot = True if _importNeschimbat(cale, dovada) else None
	if cerere.get("fara_traducere"):
		r = Rezultat(NIMIC)
	else:
		r = traduceDosar(cale, timp_maxim=timp, tot=tot, _plan=plan)
	if _amprentaTraducere(cale) != cerere["amprenta"]:
		return
	date = {"rezultat": {k: getattr(r, k) for k in Rezultat.__slots__}, "fisiere": [], "intrare": None}
	pastrate = plan.get("pastrate", {})
	total = 0
	for i, (f, rel, original, tradus) in enumerate(plan.get("de_scris", [])):
		total += len(original) + len(tradus)
		if total > MAX_PLAN_TRADUCERE:
			return
		with open(f, "rb") as fh:
			actual = _suma(fh.read(MAX_OCTETI + 1))
		for sufix, continut in (("in", original), ("out", tradus)):
			with open(os.path.join(dosar, "%d.%s" % (i, sufix)), "wb") as fh:
				fh.write(continut)
		date["fisiere"].append([rel, actual])
		pastrate[rel] = {"original": _suma(original), "tradus": _suma(tradus)}
	if r.stare == TRADUS or (plan.get("vechi") and pastrate):
		date["intrare"] = {"stare": TRADUS, "versiune": VERSIUNE, "cand": int(time.time()),
			"secunde": round(r.secunde, 2), "fisiere": pastrate}
	with open(os.path.join(dosar, "rezultat.json"), "w", encoding="utf-8") as f:
		json.dump(date, f)


def _aplicaTraducerea(cale, dosar, date, amprenta, cerere):
	"""Pe firul de lucru: verificare din nou, scrieri atomice, revenire la eroare."""
	if cerere["anulat"].is_set() or _amprentaTraducere(cale) != amprenta:
		return False
	plan = []
	for i, (rel, suma) in enumerate(date["fisiere"]):
		f = os.path.abspath(os.path.join(cale, rel))
		if os.path.commonpath([os.path.abspath(cale), f]) != os.path.abspath(cale) or not f.endswith(".py"):
			return False
		with open(f, "rb") as fh:
			actual = fh.read(MAX_OCTETI + 1)
		if _suma(actual) != suma:
			return False
		with open(os.path.join(dosar, "%d.in" % i), "rb") as fh:
			original = fh.read(MAX_OCTETI + 1)
		with open(os.path.join(dosar, "%d.out" % i), "rb") as fh:
			tradus = fh.read(MAX_PLAN_TRADUCERE + 1)
		try:
			with open(f + "2", "rb") as fh:
				rezerva = fh.read(MAX_OCTETI + 1)
		except FileNotFoundError:
			rezerva = None
		if rezerva is not None and len(rezerva) > MAX_OCTETI:
			return False
		plan.append((f, actual, original, tradus, rezerva))
	scrise = []
	try:
		for f, actual, original, tradus, rezerva in plan:
			if cerere["anulat"].is_set():
				raise OSError("traducere anulata")
			# Actualizarea pluginului nu este suprascrisa nici intre doua scrieri.
			with open(f, "rb") as fh:
				if fh.read(MAX_OCTETI + 1) != actual:
					raise OSError("plugin schimbat")
			scrise.append((f, actual, tradus, rezerva, original))
			_scrieVerificat(f + "2", original, rezerva)
			with open(f, "rb") as fh:
				if fh.read(MAX_OCTETI + 1) != actual:
					raise OSError("plugin schimbat inaintea inlocuirii")
			_scrieVerificat(f, tradus, actual)
			_stergeCompilate(f)
		if cerere["anulat"].is_set():
			raise OSError("traducere anulata")
		# Nu publica o traducere daca alt fisier a fost actualizat la aplicare.
		atinse = set(os.path.relpath(f, cale) for f, _a, _o, _t, _r in plan)
		atinse.update(n + "2" for n in list(atinse))
		atinse.update(n[:-3] + ext for n in list(atinse) if n.endswith(".py") for ext in (".pyc", ".pyo"))
		acum = _amprentaTraducere(cale)
		vechi = {a[0]: a for a in amprenta if not stat.S_ISDIR(a[-1]) and a[0] not in atinse}
		nou = {a[0]: a for a in acum if not stat.S_ISDIR(a[-1]) and a[0] not in atinse}
		if vechi != nou:
			raise OSError("plugin schimbat la aplicare")
		for f, _actual, original, tradus, _rezerva in plan:
			with open(f, "rb") as fh:
				if fh.read(MAX_PLAN_TRADUCERE + 1) != tradus:
					raise OSError("traducere schimbata la aplicare")
			with open(f + "2", "rb") as fh:
				if fh.read(MAX_OCTETI + 1) != original:
					raise OSError("original schimbat la aplicare")
		return acum
	except OSError:
		for f, actual, tradus, rezerva, original in reversed(scrise):
			try:
				with open(f, "rb") as fh:
					inca_tradus = fh.read(MAX_PLAN_TRADUCERE + 1) == tradus
				if inca_tradus:
					_scrieVerificat(f, actual, tradus)
				with open(f + "2", "rb") as fh:
					inca_original = fh.read(MAX_OCTETI + 1) == original
				if inca_original:
					if rezerva is None:
						os.remove(f + "2")
					else:
						_scrieVerificat(f + "2", rezerva, original)
			except OSError:
				pass
		return False


def _traduceInProces(cale, timp, tot=None, echec=None, importa=None, verificat=None, forteaza=False):
	"""Un copil per plugin; fara reluarea muncii grele pe fir la eroare."""
	import subprocess
	import tempfile
	import importlib.util
	cheie = _cheie(cale)
	cerere = {"anulat": threading.Event(), "gata": threading.Event(), "proces": None, "importa": importa}
	with _lacat:
		if _inchideTraducerile or cheie in _anulateTraducere or cheie in _proceseTraducere or cheie in _publicariTraducere:
			return None
		_proceseTraducere[cheie] = cerere
	p = None
	reusit = False
	try:
		if not os.access(PYTHON3, os.X_OK):
			return None
		amprenta = _amprentaTraducere(cale)
		if verificat is not None and amprenta != verificat:
			return None
		dovada = _dovadaImport(echec, cale) if echec is not None and verificat is None else None
		if dovada is not None and not dovada["sintaxa"]:
			# Numai cache regenerabil; importul nou trebuie sa citeasca sursa actuala.
			# Pregatirea nu necesita un copil si ramane pe firul de lucru.
			fisiere = _fisierePy(cale)
			if len(fisiere) > MAX_FISIERE:
				return None
			for sursa in fisiere:
				cache = importlib.util.cache_from_source(sursa)
				if os.path.islink(os.path.dirname(cache)):
					raise OSError("legatura in cache-ul pluginului")
				for f in (cache, sursa[:-3] + ".pyc", sursa[:-3] + ".pyo"):
					try:
						os.remove(f)
					except FileNotFoundError:
						pass
			if cerere["anulat"].is_set() or _amprentaTraducere(cale) != amprenta:
				return None
			sem = semnatura(cale)
			reusit = True
			return Rezultat(_REIMPORT), None, amprenta, sem, cerere
		with tempfile.TemporaryDirectory(prefix="hds-py2-") as dosar:
			with open(os.path.join(dosar, "cerere.json"), "w", encoding="utf-8") as f:
				json.dump({"cale": cale, "tot": forteaza if verificat is not None else tot,
					"stare": _citesteStare(), "amprenta": amprenta,
					"fara_traducere": verificat is not None and not forteaza,
					"import": dovada}, f)
			spec = importlib.util.find_spec(MOTOR)
			motor = os.path.dirname(os.path.dirname(spec.origin)) if spec and spec.origin else ""
			rad = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
			p = subprocess.Popen([PYTHON3, "-I", "-B", "-c", _COPIL_TRADUCERE, rad, motor, dosar,
				repr(float(timp)), str(os.getpid())], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
				stderr=subprocess.DEVNULL, close_fds=True)
			with _lacat:
				cerere["proces"] = p
			limita = time.monotonic() + timp
			while p.poll() is None:
				if cerere["anulat"].is_set() or time.monotonic() >= limita:
					_jurnal("traducerea in proces separat a fost anulata sau a depasit timpul")
					p.kill()
					p.wait()
					return None
				cerere["anulat"].wait(min(0.1, max(0.001, limita - time.monotonic())))
			if p.returncode or cerere["anulat"].is_set():
				_jurnal("traducerea in proces separat s-a oprit (cod %s)" % p.returncode)
				return None
			with open(os.path.join(dosar, "rezultat.json"), encoding="utf-8") as f:
				date = json.load(f)
			r = Rezultat(**date["rezultat"])
			amprenta_noua = _aplicaTraducerea(cale, dosar, date, amprenta, cerere)
			if amprenta_noua is False:
				return None
			amprenta = amprenta_noua
			sem = semnatura(cale)
			reusit = True
			return r, date["intrare"], amprenta, sem, cerere
	except (OSError, ValueError, TypeError, KeyError) as e:
		_jurnal("traducerea in proces separat nu s-a terminat: %r" % (e,))
		return None
	finally:
		if p is not None:
			if p.poll() is None:
				try:
					p.kill()
				except OSError:
					pass
			p.wait()
		with _lacat:
			if not reusit and _proceseTraducere.get(cheie) is cerere:
				_proceseTraducere.pop(cheie, None)
		cerere["gata"].set()


def _traduceInFundal(categorie, nume, cale, cheie, semn, tot=None, echec=None, importa=None, verificat=None, forteaza=False):
	"""Pe firul de verificare (FRZ 0.7.7): traducerea pluginului cu semnul gasit. Rezultatul ramane in _fundal["traduse"] pana la
	citirea listei ceruta de pompa, cand dupaImport (pe firul interfetei) face numai ce cere enigma: modulul tradus importat din
	nou, ori cererea motorului (python3-fissix). Semnatura fisierelor traduse se tine minte aici, ca dupaImport sa nu mai ceara
	nimic dupa aceea."""
	t0 = time.monotonic()
	if PROCES:
		gata = _traduceInProces(cale, TIMP_TRADUCERE_FUNDAL_S, tot=tot, echec=echec,
			importa=importa, verificat=verificat, forteaza=forteaza)
		if gata is not None:
			with _lacat:
				if not gata[4]["anulat"].is_set() and not _inchideTraducerile:
					_publicariTraducere[cheie] = (cale, semn, gata)
					_fundal["gasite"].append(cheie)
				if _proceseTraducere.get(cheie) is gata[4]:
					_proceseTraducere.pop(cheie, None)
		elif cheie in _cadereAnunt:
			# TRD6: traducerea ceruta dupa o cadere nu s-a facut (procesul, timpul): omul afla, la citirea listei, ca nu s-a putut
			with _lacat:
				if not _inchideTraducerile and cheie not in _anulateTraducere:
					_fundal["traduse"][cheie] = (Rezultat(NETRADUS, motiv="traducerea nu s-a terminat"), semn)
					_fundal["gasite"].append(cheie)
		return
	try:
		r = traduceDosar(cale, timp_maxim=TIMP_TRADUCERE_FUNDAL_S, tot=tot, pauza=PAUZA_FUNDAL_S)
	except Exception as e:
		_jurnal("%s/%s: traducerea din fundal a cazut: %r" % (categorie, nume, e))
		return
	if r.stare == FARA_MOTOR:
		# ca inainte: verificarea se reia dupa ce vine python3-fissix (semnul se uita, pluginul ramane cum s-a incarcat)
		_tineMinteVerdict(cheie, semnatura(cale), None)
		_uitaVerificarea(cale)
		with _lacat:
			_semnaturi.pop(cheie, None)
	else:
		sem = semnatura(cale)
		_tineMinteVerdict(cheie, sem, None)
		try:
			usor = _semnUsor(os.stat(os.path.join(cale, "plugin.py")))
		except OSError:
			usor = None
		with _lacat:
			if usor is None:
				_semnaturi.pop(cheie, None)
			else:
				_semnaturi[cheie] = (usor, sem)
	_jurnal("%s/%s: tradus in fundal: %s (%.1f s)" % (categorie, nume, r.stare, time.monotonic() - t0))
	with _lacat:
		_fundal["traduse"][cheie] = (r, semn)
		_fundal["gasite"].append(cheie)     # pompa citeste lista din nou; dupaImport importa pluginul tradus


def _pornestePompa():
	"""ceasul de pe firul interfetei (facut numai acolo) care, dupa un semn gasit in fundal, citeste din nou lista pluginurilor"""
	if not _ePrincipal():
		return
	try:
		if _fundal["pompa"] is None:
			from enigma import eTimer
			t = eTimer()
			t.callback.append(pompa)
			_fundal["pompa"] = t
		if not _fundal["pompa"].isActive():
			_fundal["pompa"].start(PAS_POMPA_MS, False)
	except Exception as e:
		# pe PC (fara enigma) probele cheama pompa() de mana
		_fundal["pompa"] = None
		if not isinstance(e, ImportError):
			_jurnal("ceasul verificarii: %r" % (e,))


def _recitesteLista():
	"""numai citirea listei (ca reincarcaPluginuri dupa opkg, dar fara curatarea locurilor orfane, care sterge fisiere).
	0.7.7 (UPD): nu cand programul imaginii s-a schimbat pe disc sub interfata (pluginurile noi ar cadea in procesul vechi;
	traducerea se face la pornirea urmatoare)"""
	import importlib
	from Components.HdsPluginExtern import imagineSchimbataPeDisc
	if imagineSchimbataPeDisc():
		_jurnal("lista pluginurilor nu se citeste din nou: programul imaginii s-a schimbat pe disc (interfata trebuie repornita)")
		return
	from Components.PluginComponent import plugins
	from Tools.Directories import resolveFilename, SCOPE_PLUGINS
	from Components import HdsModuleLipsa
	sesiune = HdsModuleLipsa._stare.get("sesiune")
	if _asteaptaActivarea and sesiune is None:
		# Importul de control nu pastreaza in cache o versiune pana la sesiune.
		for cale in list(_asteaptaActivarea):
			prefix = "Plugins." + ".".join(cale.replace("\\", "/").split("/")[-2:])
			_scoateModulele(prefix, cale)
		return
	cai = set(_asteaptaActivarea) if sesiune is not None else set()
	inainte = list(plugins.pluginList) if cai else []
	importlib.invalidate_caches()
	plugins.readPluginList(resolveFilename(SCOPE_PLUGINS))
	if cai:
		# needsRestart=False intra deja in lista; si el trebuie sa primeasca SESSIONSTART.
		for cale in cai:
			noi = [p for p in plugins.pluginList if p.path == cale and p not in inainte]
			amanati = plugins.amanateToate.setdefault(cale, [])
			amanati.extend(p for p in noi if p not in amanati)
		plugins.activeazaAcum(cai, sesiune)
		_importuriDeActivat.difference_update(cai)
		_asteaptaActivarea.difference_update(cai)


def _valideazaPublicarea(fir):
	"""Disc numai in fundal; pompa primeste doar rezultatul din memorie."""
	cheie, publicare = fir.publicare
	cale, semn, gata = publicare
	r, intrare_noua, amprenta, sem, cerere = gata
	notificari = None
	publicat = False
	anterioara = None
	try:
		notificari = _SchimbariPlugin(cale)
		if r.stare == _REIMPORT and not _pazesteImportul(notificari):
			cerere["anulat"].set()
			_jurnal("importul de control este amanat: programul imaginii s-a schimbat pe disc (interfata trebuie repornita)")
			return
		actuala = _amprentaTraducere(cale)
		if cerere["anulat"].is_set() or actuala != amprenta or notificari.schimbat():
			return
		anterioara = _citesteStare() if r.stare != _REIMPORT else None
		if intrare_noua is not None:
			_punePlugin(cheie, intrare_noua)
			# Scrierea existenta jurnalizeaza erorile; recitirea confirma rezultatul.
			if _citesteStare()["pluginuri"].get(cheie) != intrare_noua:
				raise OSError("starea traducerii nu a fost salvata")
		if r.stare == FARA_MOTOR:
			_uitaVerificarea(cale)
		elif r.stare != _REIMPORT:
			_tineMinteVerdict(cheie, sem, None)
		if cerere["anulat"].is_set() or _amprentaTraducere(cale) != amprenta:
			return
		try:
			usor = _semnUsor(os.stat(os.path.join(cale, "plugin.py")))
		except OSError:
			usor = None
		with _lacat:
			if not cerere["anulat"].is_set() and not _inchideTraducerile:
				_publicariGata[cheie] = (cale, semn, gata, usor, notificari)
				publicat = True
	except Exception as exc:
		_jurnal("rezultatul traducerii nu se publica: %r" % (exc,))
	finally:
		if notificari is not None:
			if publicat:
				# Windows anuleaza notificarea cand firul care a creat-o se termina.
				# Firul asteapta numai consumul pompei, cu un termen propriu.
				if not notificari.terminat.wait(60):
					cerere["anulat"].set()
			notificari.elibereaza()
		if anterioara is not None and (not publicat or cerere["anulat"].is_set() or notificari.schimbare):
			def revine(stare):
				schimbat = False
				for camp, asteptat in (("pluginuri", intrare_noua), ("verificate", sem)):
					d = stare.setdefault(camp, {})
					if asteptat is not None and d.get(cheie) == asteptat:
						veche = anterioara.get(camp, {}).get(cheie)
						if veche is None:
							d.pop(cheie, None)
						else:
							d[cheie] = veche
						schimbat = True
				return schimbat
			_actualizeaza(revine)
		with _lacat:
			if r.stare == _REIMPORT and (not publicat or cerere["anulat"].is_set() or notificari.schimbare):
				_importuriDeActivat.discard(cheie)
			if _validariTraducere.get(cheie) is publicare:
				_validariTraducere.pop(cheie, None)
		fir.terminat()


def pompa(reciteste=None):
	"""Pe firul interfetei: dupa semnele gasite in fundal, lista pluginurilor se citeste din nou (PluginComponent.
	readPluginList, ca dupa opkg): dupaImport gaseste semnul in STARE, traduce si importa din nou pe loc. Intoarce True cand a
	cerut citirea. Ceasul se opreste cand firul s-a terminat si nu mai e nimic de facut."""
	if PROCES and not _ePrincipal():
		return False
	with _lacat:
		gasite = list(_fundal["gasite"])
		del _fundal["gasite"][:]
		publicari = [(k, _publicariTraducere.pop(k)) for k in gasite if k in _publicariTraducere]
		pregatite = list(_publicariGata.items())
		_publicariGata.clear()
		fir = _fundal["fir"]
		viu = bool(_restaurariOriginale) or (fir is not None and fir.is_alive())
	for cheie, publicare in publicari:
		gasite = [k for k in gasite if k != cheie]
		validare = _FirVerificare()
		validare.publicare = (cheie, publicare)
		with _lacat:
			_validariTraducere[cheie] = publicare
		try:
			_pornesteFir(_valideazaPublicarea, validare)
		except Exception as exc:
			with _lacat:
				_validariTraducere.pop(cheie, None)
			_jurnal("validarea traducerii nu a pornit: %r" % (exc,))
	for cheie, (cale, semn, gata, usor, notificari) in pregatite:
		r, _intrare, _amprenta, sem, cerere = gata
		if cerere["anulat"].is_set() or notificari.schimbat():
			cerere["anulat"].set()
			with _lacat:
				_importuriDeActivat.discard(cheie)
			notificari.inchide()
			continue
		if r.stare == _REIMPORT:
			# Importul si obiectele Enigma2 raman numai pe firul principal.
			# Modulele vechi din cache nu pot confirma noua versiune a dependentei.
			try:
				prefix = "Plugins." + ".".join(cheie.replace("\\", "/").split("/")[-2:])
				_scoateModulele(prefix, cale)
				fara_cache = sys.dont_write_bytecode
				try:
					sys.dont_write_bytecode = True
					# Curatarea cache-ului poate lasa timp unei actualizari opkg.
					if cerere["anulat"].is_set() or notificari.schimbat():
						cerere["anulat"].set()
						notificari.inchide()
						continue
					cerere["importa"]()
				finally:
					sys.dont_write_bytecode = fara_cache
			except Exception as exc:
				_scoateModulele(prefix, cale)
				if not notificari.schimbat():
					categorie, nume = cheie.replace("\\", "/").split("/")[-2:]
					with _lacat:
						if not cerere["anulat"].is_set() and not _inchideTraducerile and cheie not in _anulateTraducere:
							_validariTraducere.pop(cheie, None)
							_cereriImportTraducere[cheie] = ("plugin.py", "import Python 2", exc, cerere["importa"], _amprenta)
							_cereVerificarea(categorie, nume, cale, cheie, None, reia=True)
				notificari.inchide()
				continue
			if notificari.schimbat() or cerere["anulat"].is_set():
				_scoateModulele(prefix, cale)
				notificari.inchide()
				continue
			r = Rezultat(NIMIC)
		with _lacat:
			_semnaturi[cheie] = (usor, sem)
			_fundal["traduse"][cheie] = (r, semn, notificari)
			if cheie in _importuriDeActivat and r.stare in (TRADUS, DEJA, NIMIC):
				_asteaptaActivarea.add(cheie)
		gasite.append(cheie)
	with _lacat:
		fir = _fundal["fir"]
		viu = (viu or (fir is not None and fir.is_alive()) or
			bool(_validariTraducere or _publicariGata or _publicariTraducere or _asteaptaActivarea))
		if reciteste is None and _asteaptaActivarea:
			from Components import HdsModuleLipsa
			if HdsModuleLipsa._stare.get("sesiune") is not None:
				gasite.extend(k for k in _asteaptaActivarea if k not in gasite)
	if not viu and not gasite and _fundal["pompa"] is not None:
		try:
			_fundal["pompa"].stop()
		except Exception:
			pass
	if not gasite:
		return False
	try:
		if reciteste is None:
			reciteste = _recitesteLista
		reciteste()
	except Exception as e:
		_jurnal("citirea listei dupa verificare: %r" % (e,))
	finally:
		# Rezultatele validate sunt valabile numai pentru aceasta citire a listei.
		with _lacat:
			for cheie, _publicare in pregatite:
				_fundal["traduse"].pop(cheie, None)
				_publicare[4].inchide()
	return True


def _iaTraducerea(cale, cheie):
	"""Consuma in memorie rezultatul verificat de firul de lucru pentru aceasta citire."""
	with _lacat:
		gata = _fundal["traduse"].pop(cheie, None)
	if gata is not None and len(gata) > 2 and gata[2].schimbat():
		return None
	return gata


def dupaImport(categorie, nume, cale, plugin, importa):
	"""Din Components/PluginComponent.py, dupa un import reusit: un plugin extern al carui cod de Python 2 e numai in functii (cade
	abia la deschidere) se recunoaste din sursa, o singura data pe versiunea fisierelor (semnatura in STARE), se traduce si se
	importa din nou. Intoarce modulul de folosit; arunca exceptia celui de-al doilea import daca pluginul tradus cade la import.
	Pe receptor (FUNDAL) recunoasterea merge pe firul de verificare: pluginul ramane cum s-a incarcat, iar semnul gasit acolo se
	traduce la citirea urmatoare a listei (ceruta singura, vezi pompa)."""
	try:
		if _pluginImagine(categorie, nume):
			return plugin
		if not (FUNDAL and PROCES):
			try:
				st_plugin = os.stat(os.path.join(cale, "plugin.py"))
			except OSError:
				return plugin
		gata = _iaTraducerea(cale, _cheie(cale)) if FUNDAL else None
	except Exception as e:
		_jurnal("%s/%s: verificarea a cazut: %r" % (categorie, nume, e))
		return plugin
	# Eroarea reimportului apartine incarcatorului, inclusiv dependenta lipsa.
	if gata is not None:
		return _dupaTraducere(categorie, nume, cale, plugin, importa, gata[0])
	try:
		if FUNDAL and _cheie(cale) in _cereriCadere:
			# TRD6: o cerere dupa cadere care asteapta motorul (python3-fissix) se reia la fiecare citire a listei
			_cereVerificarea(categorie, nume, cale, _cheie(cale), None)
			return plugin
		if FUNDAL and PROCES:
			cheie = _cheie(cale)
			_cereVerificarea(categorie, nume, cale, cheie, None)
			return plugin
		cheie = _cheie(cale)
		if FUNDAL:
			# FRD: pe firul care citeste lista numai statul lui plugin.py; semnatura vine din memoria facuta de firul de verificare
			usor = _semnUsor(st_plugin)
			tinut = _semnaturi.get(cheie)
			if tinut is None or tinut[0] != usor:
				_cereVerificarea(categorie, nume, cale, cheie, None, usor)
				return plugin
			sem = tinut[1]
		else:
			sem = semnatura(cale)
		# PLG 0.7.7: STARE (JSON pe memoria interna) se citeste abia aici, nu pentru fiecare plugin strain la fiecare citire a listei:
		# la pornirea interfetei memoria semnaturilor e goala, deci pe firul interfetei nu se mai citeste nimic din STARE
		stare = _citesteStare()
		if stare.setdefault("verificate", {}).get(cheie) == sem:
			return plugin
		semn = _semnPastrat(stare, cheie, sem)
		if FUNDAL:
			# fara semn: verificarea; cu semnul pastrat (gasit inainte): traducerea; amandoua pe firul de verificare (FRZ 0.7.7)
			_cereVerificarea(categorie, nume, cale, cheie, sem, tinut[0])
			return plugin
		if semn is None:
			semn = _verificaPeLoc(categorie, nume, cale, cheie, sem, stare)
			if semn is TIMP_DEPASIT:
				return plugin       # oprita de timp, nu terminata: se reia la citirea urmatoare, de unde a ramas
			if semn is None:
				_tineMinteVerdict(cheie, sem, None)
				return plugin
		_jurnal("%s/%s: cod de Python 2 in %s (%s)" % (categorie, nume, semn[0], semn[1]))
		r = traduceDosar(cale)
		_tineMinteVerdict(_cheie(cale), semnatura(cale), None)
		with _lacat:
			_semnaturi.pop(_cheie(cale), None)   # fisierele traduse au alta semnatura: firul o afla la citirea urmatoare
	except Exception as e:
		_jurnal("%s/%s: verificarea a cazut: %r" % (categorie, nume, e))
		return plugin
	if r.stare == FARA_MOTOR:
		_uitaVerificarea(cale)
	return _dupaTraducere(categorie, nume, cale, plugin, importa, r)


def traduceDupaCadere(categorie, nume, cale, exc):
	"""TRD6 (MI9): din Components/HdsPluginExtern.py, pe firul enigma2, la o eroare cu cauza "python2" la rulare intr-un plugin
	extern care s-a incarcat (o parte scrisa in Python 2 pe care traducerea de la incarcare n-a prins-o). Numai cererea: tot
	pluginul se traduce pe firul de verificare (traduceDosar cu regula de acum: partea de Python 3 neatinsa), pompa cere citirea listei, dupaImport importa pluginul
	tradus si abia atunci omul primeste mesajul (HdsPluginExtern.anuntaTraducere). O data pe plugin in sesiunea interfetei.
	Fara disc pe firul care cheama. True cand cererea e la coada (mesajul va veni), altfel False. Nu arunca."""
	try:
		if not FUNDAL or _pluginImagine(categorie, nume):
			return False
		cheie = _cheie(cale)
		with _lacat:
			if _inchideTraducerile or cheie in _cadereCerute:
				return False
			_cadereCerute.add(cheie)
			cerere = ("rulare", "%s: %s" % (exc.__class__.__name__, str(exc)[:200]))
			_cereriCadere[cheie] = cerere
			_cadereAnunt[cheie] = nume
		_cereVerificarea(categorie, nume, cale, cheie, None, reia=True)
		with _lacat:
			la_coada = _fundal["acum"] == cheie or any(c[3] == cheie for c in _fundal["coada"])
			# luata deja de fir: nu mai e aceeasi cerere (scoasa sau pusa inapoi ca asteptare de motor)
			if not la_coada and _cereriCadere.get(cheie) is cerere:
				# alta lucrare pe acelasi plugin (traducere, validare): cererea nu intra; o cadere urmatoare o poate face
				_cereriCadere.pop(cheie, None)
				_cadereAnunt.pop(cheie, None)
				_cadereCerute.discard(cheie)
				return False
		return True
	except Exception as e:
		_jurnal("%s/%s: traducerea dupa cadere nu s-a cerut: %r" % (categorie, nume, e))
		return False


def _anuntaCadere(cale, tradus):
	"""TRD6: mesajul pentru om dupa traducerea ceruta de o cadere (pe firul interfetei, din _dupaTraducere)"""
	with _lacat:
		nume = _cadereAnunt.pop(_cheie(cale), None)
	if nume is None:
		return
	try:
		from Components.HdsPluginExtern import anuntaTraducere
		anuntaTraducere(nume, tradus)
	except Exception as e:
		_jurnal("mesajul traducerii dupa cadere: %r" % (e,))


def _dupaTraducere(categorie, nume, cale, plugin, importa, r):
	"""pe firul care citeste lista, dupa traducerea pluginului (pe loc sau pe firul de verificare): ce cere enigma"""
	if r.stare == FARA_MOTOR:
		# TRD6: fara motor nu e un raspuns: cererea de dupa o cadere asteapta python3-fissix (_verificaInFundal), mesajul ramane
		# fara motor: pluginul ramane cum e (s-a incarcat); verificarea se reia dupa ce vine python3-fissix
		_jurnal("%s/%s: lipseste traducatorul (python3-fissix)" % (categorie, nume))
		try:
			from Components import HdsModuleLipsa
			HdsModuleLipsa.cere(ModuleNotFoundError("No module named '%s'" % MOTOR, name=MOTOR), cale, nume, "incarcare")
		except Exception as e:
			_jurnal("HdsModuleLipsa: %r" % (e,))
		return plugin
	if r.stare != TRADUS:
		if r.stare in (COMPILAT, PREA_MARE, NETRADUS):
			_jurnal("%s/%s: scris pentru Python 2, netradus: %s" % (categorie, nume, r.motiv))
		_anuntaCadere(cale, False)
		return plugin
	_jurnal("tradus din Python 2: %s/%s (%d fișiere, %.1f s)" % (categorie, nume, r.fisiere, r.secunde))
	_scoateModulele(".".join(["Plugins", categorie, nume]))
	try:
		modul = importa()
	except Exception:
		with _lacat:
			dupa_cadere = _cheie(cale) in _cadereAnunt
		if dupa_cadere:
			# TRD6: pluginul se incarca inainte de traducere; tradus nu se mai incarca: originalele inapoi pe un fir (drumul
			# existent, _refaceOriginalele), lista se citeste din nou si pluginul ramane cum era; mesajul "nu a putut" e adevarat
			_cereOriginaleleCadere(cale)
		_anuntaCadere(cale, False)
		raise
	_anuntaCadere(cale, True)
	return modul


def _uitaVerificarea(cale):
	_actualizeaza(lambda stare: stare.get("verificate", {}).pop(_cheie(cale), None) is not None)


class Python2Netradus(ImportError):
	"""pluginul e scris in Python 2 si nu s-a putut traduce sigur; textul e pentru om (Components/PluginComponent.py)"""


def textOm(rezultat):
	if rezultat.stare == COMPILAT:
		return _t("Scris pentru Python 2, numai cu fișiere compilate (fără sursă): nu se poate traduce")
	if rezultat.stare == PREA_MARE:
		return _t("Scris pentru Python 2; prea mare pentru traducerea pe receptor")
	return _t("Scris pentru Python 2; nu s-a putut traduce sigur")


def incearca(categorie, nume, cale, exc, importa):
	"""Din Components/PluginComponent.py, cand importul pluginului a cazut cu exc. importa(): importul din nou.
	Intoarce modulul pluginului (tradus si incarcat) sau None (nu e cod de Python 2 sau era deja tradus: eroarea ramane cea
	initiala). Arunca exceptia celui de-al doilea import (pluginul tradus tot cade), ModuleNotFoundError('fissix') cand lipseste
	motorul (Components/HdsModuleLipsa.py il aduce) sau Python2Netradus."""
	try:
		if _pluginImagine(categorie, nume):
			return None
		# PY2 0.7.7: importul s-a oprit pe un modul nativ al pluginului facut pentru alt Python (.so cu un nume lipsa, "built for
		# Python 3.13"): fara traducere si fara python3-fissix; lista pluginurilor spune ca e facut pentru alta versiune de Python
		# (Components/PluginComponent.py, alt_python, din Components/HdsAltPython.py)
		if nativNeincarcat(exc):
			if FUNDAL:
				_cereOriginalele(cale, exc)
			else:
				puneOriginalele(cale, _nativ=_dateEroareNativa(exc))
			return None
		with _lacat:
			if _cheie(cale) in _restaurariOriginale:
				return None
		gata = _iaTraducerea(cale, _cheie(cale)) if FUNDAL and PROCES else None
		if FUNDAL and PROCES:
			if gata is not None:
				r = gata[0]
			else:
				cheie = _cheie(cale)
				with _lacat:
					_cereriImportTraducere[cheie] = ("plugin.py", "import Python 2", exc, importa, None)
					if _citireInitiala:
						_importuriDeActivat.add(cheie)
				_cereVerificarea(categorie, nume, cale, cheie, None)
				return None
		else:
			# Traducerea veche cazuta se reface din originale.
			nativ = _nativPastrat(cale)
			if nativ is not None:
				r = Rezultat("nativ_incompatibil", detalii=nativ)
			else:
				e = intrare(cale)
				tradus_vechi = bool(e and e.get("stare") == TRADUS and e.get("versiune") != VERSIUNE)
				if not tradus_vechi and not semnPython2(exc, cale):
					return None
				r = traduceDosar(cale, tot=True)
	except Exception as e:
		_jurnal("%s/%s: traducerea a cazut: %r" % (categorie, nume, e))
		return None
	if r.stare == "nativ_incompatibil":
		raise _eroareNativa(r.detalii) from exc
	if r.stare == FARA_MOTOR:
		_jurnal("%s/%s: scris pentru Python 2; lipseste traducatorul (python3-fissix)" % (categorie, nume))
		eroare = ModuleNotFoundError("No module named '%s'" % MOTOR, name=MOTOR)
		raise eroare from exc
	if r.stare in (COMPILAT, PREA_MARE, NETRADUS):
		_jurnal("%s/%s: scris pentru Python 2, netradus: %s" % (categorie, nume, r.motiv))
		eroare = Python2Netradus("%s (%s)" % (textOm(r), r.motiv))
		eroare.python2 = r
		raise eroare from exc
	if r.stare != TRADUS:
		return None
	_jurnal("tradus din Python 2: %s/%s (%d fișiere, %.1f s)" % (categorie, nume, r.fisiere, r.secunde))
	_scoateModulele(".".join(["Plugins", categorie, nume]))
	return importa()


def _inchidereTraduceri():
	anuleazaTraducerea()
	with _lacat:
		procese = [c.get("proces") for c in _proceseTraducere.values()] + list(_proceseVerificare.values())
	for p in procese:
		if p is not None:
			try:
				p.wait(2)
			except Exception:
				pass


import atexit
atexit.register(_inchidereTraduceri)
