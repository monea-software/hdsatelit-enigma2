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
  - totul sau nimic: daca un fisier nu se poate traduce sau nu se compileaza dupa traducere, nu se scrie nimic;
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
import os
import re
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
			if g.end_lineno != g.lineno or r.strip() != r[g.col_offset:g.end_col_offset].strip() or r[:g.col_offset].strip():
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
		if g.end_lineno != g.lineno or r.strip() != r[g.col_offset:g.end_col_offset].strip() or r[:g.col_offset].strip():
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


def _scrie(cale, date):
	tmp = cale + ".hds-tmp"
	with open(tmp, "wb") as f:
		f.write(date)
		f.flush()
		os.fsync(f.fileno())
	try:
		os.chmod(tmp, os.stat(cale).st_mode & 0o7777)
	except OSError:
		pass
	os.replace(tmp, cale)


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


def traduceDosar(cale, timp_maxim=TIMP_MAXIM, tot=None, pauza=0.0):
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
				return Rezultat(NETRADUS, motiv="%s: %s" % (rel, exc))
			nou, eroare = traduceText(text, f, numai_importuri)
			if eroare is not None:
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


def puneOriginalele(cale):
	"""pluginul din cale inapoi cum a venit (fisierele .py2 peste traduceri) si scos din STARE. Intoarce cate fisiere."""
	n = 0
	for radacina, dosare, fisiere in os.walk(cale):
		dosare[:] = [d for d in dosare if d != "__pycache__"]
		for f in fisiere:
			if f.endswith(SUFIX_ORIGINAL):
				vechi = os.path.join(radacina, f)
				try:
					os.replace(vechi, vechi[:-len(SUFIX_ORIGINAL)] + ".py")
					_stergeCompilate(vechi[:-len(SUFIX_ORIGINAL)] + ".py")
					n += 1
				except OSError as exc:
					_jurnal("%s: %s" % (vechi, exc))
	_actualizeaza(lambda stare: stare["pluginuri"].pop(_cheie(cale), None) is not None)
	return n


# ---------------------------------------------------------------- legatura cu incarcarea pluginurilor

def _pluginImagine(categorie, nume):
	try:
		from Components.HdsPluginExtern import PLUGINURI_IMAGINE
		return "%s/%s" % (categorie, nume) in PLUGINURI_IMAGINE
	except Exception:
		return categorie == "Extensions" and nume.startswith("Hds")


def _scoateModulele(prefix):
	for n in [n for n in sys.modules if n == prefix or n.startswith(prefix + ".")]:
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
		h.update(("%s\0%d\0%d\n" % (os.path.relpath(f, cale), s.st_size, int(s.st_mtime))).encode("utf-8", "surrogateescape"))
	return h.hexdigest()


# formele de text care pot fi de Python 2 (filtrul de dinaintea analizei; o potrivire nu e un semn, numai un motiv de analiza):
# print fara paranteze, except X, e:, `x`, <>, 0777, ur'', exec fara paranteze, raise X, y, taburi amestecate cu spatii
_CANDIDAT = re.compile(br"^[ \t]*print(?:[ \t]+[^\s(=.]|[ \t]*$)|except[ \t]+[^:\n#]+,[ \t]*\w+[ \t]*:|`|<>|"
	br"(?<![\w.:\"'%-])0[0-7]{2,}(?![\w.:])|"
	br"\b[uU][rR]['\"]|^[ \t]*exec[ \t]+[^\s(=]|^[ \t]*raise[ \t]+[\w.]+[ \t]*,|^(?: +\t|\t+ )", re.M)


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
		forma = _CANDIDAT.search(date) is not None
		importuri = imp is not None and imp.search(date) is not None
		nume_vechi = _NUME_CANDIDAT.search(date) is not None
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


def _semnUsor(st):
	return (getattr(st, "st_ino", 0), st.st_size, int(st.st_mtime))


def incepeCitirea():
	"""Din Components/PluginComponent.py, la inceputul fiecarei citiri a listei de pluginuri: bugetul verificarii din sursa"""
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


def _cereVerificarea(categorie, nume, cale, cheie, sem, usor=None):
	"""pune pluginul la coada firului de verificare (o data) si porneste firul, daca nu ruleaza. sem None: semnatura o afla
	firul (FRD), cu semnul usor `usor` pentru memoria _semnaturi. Firul porneste fara threading.Thread.start (MI8: start
	astepta lacatul Python, o data pe citirea listei cand firul nu rula)."""
	fir_nou = None
	with _lacat:
		if _fundal["acum"] == cheie or any(c[3] == cheie for c in _fundal["coada"]):
			return
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
		if INTARZIERE_FUNDAL_S > 0:
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
	if not gasit:
		_jurnal("verificarea in proces separat nu a dat semnul (cod %s): o fac pe fir" % (p.returncode,))
		return False, None
	if semn == TIMP_DEPASIT:
		semn = TIMP_DEPASIT
	return True, semn


def _traduceInFundal(categorie, nume, cale, cheie, semn):
	"""Pe firul de verificare (FRZ 0.7.7): traducerea pluginului cu semnul gasit. Rezultatul ramane in _fundal["traduse"] pana la
	citirea listei ceruta de pompa, cand dupaImport (pe firul interfetei) face numai ce cere enigma: modulul tradus importat din
	nou, ori cererea motorului (python3-fissix). Semnatura fisierelor traduse se tine minte aici, ca dupaImport sa nu mai ceara
	nimic dupa aceea."""
	t0 = time.monotonic()
	try:
		r = traduceDosar(cale, timp_maxim=TIMP_TRADUCERE_FUNDAL_S, pauza=PAUZA_FUNDAL_S)
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
	importlib.invalidate_caches()
	plugins.readPluginList(resolveFilename(SCOPE_PLUGINS))


def pompa(reciteste=None):
	"""Pe firul interfetei: dupa semnele gasite in fundal, lista pluginurilor se citeste din nou (PluginComponent.
	readPluginList, ca dupa opkg): dupaImport gaseste semnul in STARE, traduce si importa din nou pe loc. Intoarce True cand a
	cerut citirea. Ceasul se opreste cand firul s-a terminat si nu mai e nimic de facut."""
	with _lacat:
		gasite = list(_fundal["gasite"])
		del _fundal["gasite"][:]
		fir = _fundal["fir"]
		viu = fir is not None and fir.is_alive()
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
	return True


def dupaImport(categorie, nume, cale, plugin, importa):
	"""Din Components/PluginComponent.py, dupa un import reusit: un plugin extern al carui cod de Python 2 e numai in functii (cade
	abia la deschidere) se recunoaste din sursa, o singura data pe versiunea fisierelor (semnatura in STARE), se traduce si se
	importa din nou. Intoarce modulul de folosit; arunca exceptia celui de-al doilea import daca pluginul tradus cade la import.
	Pe receptor (FUNDAL) recunoasterea merge pe firul de verificare: pluginul ramane cum s-a incarcat, iar semnul gasit acolo se
	traduce la citirea urmatoare a listei (ceruta singura, vezi pompa)."""
	try:
		if _pluginImagine(categorie, nume):
			return plugin
		try:
			st_plugin = os.stat(os.path.join(cale, "plugin.py"))
		except OSError:
			return plugin
		cheie = _cheie(cale)
		if FUNDAL:
			# FRZ 0.7.7: pluginul tradus pe firul de verificare; aici numai importul din nou
			with _lacat:
				gata_tradus = _fundal["traduse"].pop(cheie, None)
			if gata_tradus is not None:
				return _dupaTraducere(categorie, nume, cale, plugin, importa, gata_tradus[0])
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


def _dupaTraducere(categorie, nume, cale, plugin, importa, r):
	"""pe firul care citeste lista, dupa traducerea pluginului (pe loc sau pe firul de verificare): ce cere enigma"""
	if r.stare == FARA_MOTOR:
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
		return plugin
	_jurnal("tradus din Python 2: %s/%s (%d fișiere, %.1f s)" % (categorie, nume, r.fisiere, r.secunde))
	_scoateModulele(".".join(["Plugins", categorie, nume]))
	return importa()


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
			return None
		# tradus de o versiune mai veche a traducatorului si tot cade (orice eroare, de pilda "unknown location" din raportul
		# 781623): se traduce din nou din originale; altfel numai la semnele lui Python 2
		e = intrare(cale)
		tradus_vechi = bool(e and e.get("stare") == TRADUS and e.get("versiune") != VERSIUNE)
		if not tradus_vechi and not semnPython2(exc, cale):
			return None
		r = traduceDosar(cale, tot=True)
	except Exception as e:
		_jurnal("%s/%s: traducerea a cazut: %r" % (categorie, nume, e))
		return None
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
