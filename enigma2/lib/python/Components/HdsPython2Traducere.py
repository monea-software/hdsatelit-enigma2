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
native facute pentru Python 2 (le opreste deja Components/HdsAltPython.py), sursa care nu se poate citi nici ca Python 2.

Nu importa nimic din enigma (probele de pe PC). RADACINA pune un dosar in fata caii STARE, numai la probe. Nu arunca din incearca()."""
import ast
import hashlib
import io
import json
import os
import re
import sys
import time

VERSIUNE = 1                      # se mareste cand se schimba traducerea; ce s-a tradus cu alta versiune nu se reface singur
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


def _scrieStare(date):
	cale = _c(STARE)
	try:
		os.makedirs(os.path.dirname(cale), exist_ok=True)
		tmp = cale + ".tmp"
		with open(tmp, "w", encoding="utf-8") as f:
			json.dump(date, f, ensure_ascii=False, indent=1, sort_keys=True)
			f.flush()
			os.fsync(f.fileno())
		os.replace(tmp, cale)
	except OSError as exc:
		_jurnal("starea nu s-a scris: %s" % exc)


def _cheie(cale):
	return os.path.normpath(cale).replace("\\", "/")


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

	class Unealta(RefactoringTool):
		def get_fixers(self):
			pre, post = RefactoringTool.get_fixers(self)
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
	script = eScript(text)
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
	Python 2 ori importa fara punct un modul vecin (care nu exista ca import absolut)"""
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
		if eScript(date):
			return False
		v = _ImporturiVecine(vecineDosar(os.path.dirname(f)))
		v.visit(arbore)
		return bool(v.gasite)
	except Exception:
		return False


def traduceDosar(cale, timp_maxim=TIMP_MAXIM, tot=None):
	"""traduce pluginul din dosarul cale (vezi antetul). Intoarce Rezultat. tot: True = tot pluginul (s-a vazut ca nu se incarca in
	Python 3: e un plugin de Python 2), None = dupa sintaxa lui plugin.py (pluginul s-a incarcat, deci partea lui Python 3 nu se atinge)."""
	inceput = time.monotonic()
	if _numaiCompilate(cale):
		return Rezultat(COMPILAT, motiv="plugin.pyo")
	if not motorDisponibil():
		return Rezultat(FARA_MOTOR)
	stare = _citesteStare()
	cheie = _cheie(cale)
	vechi = stare["pluginuri"].get(cheie) or {}
	stiute = (vechi.get("fisiere") or {}) if vechi.get("versiune") == VERSIUNE else {}
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
	for f in fisiere:
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
		numai_importuri = False
		if not tot and not sintaxaPython2(f, date):
			if not _ePython2(f, vecine, date):
				continue
			numai_importuri = True
		try:
			text, codare, cookie = _decodeaza(date)
		except UnicodeDecodeError as exc:
			return Rezultat(NETRADUS, motiv="%s: %s" % (rel, exc))
		nou, eroare = traduceText(text, f, numai_importuri)
		if eroare is not None:
			return Rezultat(NETRADUS, motiv="%s, randul %s: %s" % (rel, eroare[0], eroare[1]))
		if time.monotonic() - inceput > timp_maxim:
			return Rezultat(NETRADUS, motiv="timpul (%d s)" % timp_maxim, secunde=time.monotonic() - inceput)
		if nou == text or (nou == text + "\n" and not text.endswith("\n")):
			continue
		nou = _faraCookieStrain(nou, codare, cookie)
		try:
			iesire = nou.encode(codare)
		except (UnicodeEncodeError, LookupError):
			iesire = _faraCookieStrain(nou, "utf-8", False).encode("utf-8")
		if iesire == date:
			continue
		de_scris.append((f, rel, date, iesire))
	secunde = time.monotonic() - inceput
	if not de_scris:
		return Rezultat(DEJA if pastrate else NIMIC, secunde=secunde)
	# totul s-a tradus si se compileaza: abia acum se scrie ceva
	scrise = []
	try:
		for f, rel, original, iesire in de_scris:
			_scrie(f + "2" if f.endswith(".py") else f + SUFIX_ORIGINAL, original)
			_scrie(f, iesire)
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
	stare["pluginuri"][cheie] = {"stare": TRADUS, "versiune": VERSIUNE, "cand": int(time.time()), "secunde": round(secunde, 2),
		"fisiere": pastrate}
	_scrieStare(stare)
	return Rezultat(TRADUS, fisiere=len(scrise), secunde=secunde, detalii=scrise)


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
					n += 1
				except OSError as exc:
					_jurnal("%s: %s" % (vechi, exc))
	stare = _citesteStare()
	if stare["pluginuri"].pop(_cheie(cale), None) is not None:
		_scrieStare(stare)
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


def semnatura(cale):
	"""suma numelor, marimilor si timpilor fisierelor .py ale pluginului (fara sa le citeasca): se schimba la orice actualizare"""
	h = hashlib.sha256()
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


def semneStatice(cale, timp_maxim=30.0):
	"""(fisierul, motivul) cand sursa pluginului arata cod de Python 2 care nu cade la import (in functii): sintaxa lui Python 2
	dupa gramatica 3.13 (Python 3.14 primeste iar `except X, e:`, cu alt inteles), importuri de module scoase din Python 3,
	importuri relative implicite; altfel None. Numai citire si analiza, nimic rulat."""
	try:
		from Components.HdsPython2 import din_sursa, GRAMATICA
	except Exception:
		return None
	inceput = time.monotonic()
	fisiere = _fisierePy(cale)
	if len(fisiere) > MAX_FISIERE:
		return None
	vecine = _moduleVecine(cale)
	# filtrul ieftin (masurat pe .122: analiza completa a 14 pluginuri dura 43 s pe ARM): un fisier se analizeaza numai cand textul
	# lui are o forma care poate fi de Python 2 sau un import al unui modul vecin ori al unui modul de Python 2
	try:
		from Components.HdsPython2 import MODULE_PY2
	except Exception:
		MODULE_PY2 = frozenset()
	nume_imp = sorted(n for n in (set(vecine) | set(MODULE_PY2)) if re.match(r"^\w+$", n))
	imp = re.compile(br"^[ \t]*(?:from|import)[ \t]+(?:" + b"|".join(re.escape(n.encode("ascii", "ignore")) for n in nume_imp) +
		br")\b|\burllib\.(?:urlopen|urlencode|quote|unquote|urlretrieve)\b|^[ \t]*from[ \t]+urllib[ \t]+import", re.M) if nume_imp else None
	for f in fisiere:
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
		if not (forma or importuri):
			continue
		rel = os.path.relpath(f, cale).replace("\\", "/")
		r = din_sursa(date, f)
		if r is not None:
			return rel, "%s %s" % r
		if not importuri:
			continue
		import warnings
		try:
			with warnings.catch_warnings():
				warnings.simplefilter("ignore")
				arbore = ast.parse(date, f, "exec", feature_version=GRAMATICA)
			if eScript(date):
				continue
			v = _ImporturiVecine(vecineDosar(os.path.dirname(f)))
			v.visit(arbore)
		except (SyntaxError, ValueError, TypeError, RecursionError, MemoryError, UnicodeError):
			continue
		if v.gasite:
			return rel, "import relativ implicit %s" % v.gasite[0]
	return None


# cat poate lua verificarea din sursa intr-o citire a listei de pluginuri (la pornire, inainte de prima bataie a paznicului):
# masurat pe .122 ~0,1 s pe fisier; ce nu incape se verifica la citirea urmatoare (semnatura nu se scrie)
BUGET_CITIRE_S = 20.0
_buget = {"ramas": BUGET_CITIRE_S}


def incepeCitirea():
	"""Din Components/PluginComponent.py, la inceputul fiecarei citiri a listei de pluginuri: bugetul verificarii din sursa"""
	_buget["ramas"] = BUGET_CITIRE_S


def dupaImport(categorie, nume, cale, plugin, importa):
	"""Din Components/PluginComponent.py, dupa un import reusit: un plugin extern al carui cod de Python 2 e numai in functii (cade
	abia la deschidere) se recunoaste din sursa, o singura data pe versiunea fisierelor (semnatura in STARE), se traduce si se
	importa din nou. Intoarce modulul de folosit; arunca exceptia celui de-al doilea import daca pluginul tradus cade la import."""
	try:
		if _pluginImagine(categorie, nume) or not os.path.exists(os.path.join(cale, "plugin.py")):
			return plugin
		stare = _citesteStare()
		cheie = _cheie(cale)
		sem = semnatura(cale)
		verificate = stare.setdefault("verificate", {})
		if verificate.get(cheie) == sem:
			return plugin
		if _buget["ramas"] <= 0:
			# bugetul acestei citiri s-a dus (prima pornire dupa actualizare, multe pluginuri): pluginul se verifica la citirea urmatoare
			return plugin
		t0 = time.monotonic()
		semn = semneStatice(cale, timp_maxim=max(1.0, _buget["ramas"]))
		durata = time.monotonic() - t0
		_buget["ramas"] -= durata
		if durata > 0.5:
			_jurnal("%s/%s: verificarea din sursa %.1f s" % (categorie, nume, durata))
		if semn is TIMP_DEPASIT:
			return plugin       # oprita de timp, nu terminata: se reia la citirea urmatoare
		if semn is None:
			verificate[cheie] = sem
			_scrieStare(stare)
			return plugin
		_jurnal("%s/%s: cod de Python 2 in %s (%s)" % (categorie, nume, semn[0], semn[1]))
		r = traduceDosar(cale)
		stare = _citesteStare()
		stare.setdefault("verificate", {})[_cheie(cale)] = semnatura(cale)
		_scrieStare(stare)
	except Exception as e:
		_jurnal("%s/%s: verificarea a cazut: %r" % (categorie, nume, e))
		return plugin
	if r.stare == FARA_MOTOR:
		# fara motor: pluginul ramane cum e (s-a incarcat); verificarea se reia dupa ce vine python3-fissix
		_uitaVerificarea(cale)
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
	stare = _citesteStare()
	if stare.get("verificate", {}).pop(_cheie(cale), None) is not None:
		_scrieStare(stare)


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
		if _pluginImagine(categorie, nume) or not semnPython2(exc, cale):
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
