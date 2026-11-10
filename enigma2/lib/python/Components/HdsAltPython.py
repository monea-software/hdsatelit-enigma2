# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsAltPython.py: imaginea nu incarca in enigma2 un modul .so (sau o biblioteca) legat de alt Python decat al ei.
#
# Un modul de extensie facut pentru alt Python (de pilda 3.7) cere in antetul ELF (DT_NEEDED) libpython3.7m.so.1.0.
# Daca biblioteca aceea exista pe receptor, dlopen o incarca langa libpython3.14 al imaginii: cele doua interpretoare
# isi impart numele functiilor, iar interfata cade mai tarziu, cu semnalul 11 in libpython3.7m (raportul 919342,
# SF8008, 0.7.0: sase porniri in opt minute). Fara biblioteca, dlopen da numai ImportError.
#
# Paza (pazeste(), chemata o data de Components/PluginComponent.py, inainte de citirea pluginurilor):
#   - importlib: ExtensionFileLoader.create_module citeste intai antetul ELF al fisierului; un modul legat de alt
#     libpython (direct, sau printr-o biblioteca din dosarul lui ori din RPATH/RUNPATH) da AltPython (un ImportError),
#     fara dlopen. Pluginul primeste eroarea ca pe orice import cazut: incarcatorul il trece in lista celor care nu se
#     pot deschide, iar o eroare la folosire merge la Components/HdsPluginExtern (mesajul pe ecran si raportul);
#   - ctypes: dlopen-ul din _ctypes (deci CDLL, cdll.LoadLibrary) refuza, cu OSError, o biblioteca libpythonX.Y a altui
#     Python si un fisier (cale cu /) legat de una.
# Un fisier care nu se poate citi, sau care nu e ELF, trece ca inainte: ce nu se stie nu opreste niciodata nimic.
# Antetul se citeste in Python (program headers, segmentul dinamic, tabela de nume), cateva citiri mici pe fisier;
# rezultatul se tine minte dupa cale, marime si ora.
# Modulul nu importa nimic din enigma2 (probele de pe PC il folosesc direct).

import os
import re
import struct
import sys

ACUM = tuple(sys.version_info[:2])

# libpython3.7m.so.1.0, libpython3.14.so.1.0, libpython2.7.so.1.0 (nu libpython3.so, ABI-ul stabil)
_LIBPY = re.compile(r"^libpython(\d{1,2})\.(\d{1,3})[a-z]*\.so(?:\.[0-9.]+)?$")
# bibliotecile C si C++ ale sistemului: nu se cauta langa modul (cate un stat mai putin pe fiecare)
_RUNTIME = re.compile(r"^(?:libc|libm|libpthread|libdl|librt|libutil|libgcc_s|libstdc\+\+|libatomic|ld-linux[\w.-]*)\.so(?:\.|$)")

PT_LOAD, PT_DYNAMIC = 1, 2
DT_NULL, DT_NEEDED, DT_STRTAB, DT_STRSZ, DT_SONAME, DT_RPATH, DT_RUNPATH = 0, 1, 5, 10, 14, 15, 29
MAX_PH = 128
MAX_DYN = 4096
MAX_STR = 2 * 1024 * 1024
MAX_NUME = 4096
MAX_CACHE = 4096
MAX_VECINI = 32

_cache = {}
_pazit = [False]


class AltPython(ImportError):
	"""Modulul (sau biblioteca) e legat de alt Python decat al imaginii; nu s-a incarcat. hdsAltPython: "3.7"."""

	def __init__(self, cale, versiune, nume=None, prin=None):
		self.hdsAltPython = versiune
		self.prin = prin
		text = "%s: built for Python %s, this image has Python %s; not loaded" % (cale, versiune, textVersiune(ACUM))
		if prin:
			text += " (through %s)" % prin
		ImportError.__init__(self, text, name=nume, path=cale)


def textVersiune(v):
	return "%d.%d" % tuple(v[:2])


def versiuneLib(nume):
	"""(major, minor) pentru numele unei biblioteci libpythonX.Y, altfel None"""
	m = _LIBPY.match(os.path.basename(nume or ""))
	return (int(m.group(1)), int(m.group(2))) if m else None


def _strain(nume):
	v = versiuneLib(nume)
	return textVersiune(v) if v is not None and v != ACUM else None


# ------------------------------------------------------------------ antetul ELF

def legaturiDinFisier(f):
	"""{"needed": [...], "rpath": [...], "soname": ""} din antetul ELF al unui fisier deschis binar (seek/read), sau
	None (nu e ELF, e stricat sau nu are segment dinamic). Nu arunca pentru un fisier oarecare."""
	try:
		return _legaturi(f)
	except (struct.error, ValueError, OverflowError, OSError, IndexError, MemoryError):
		return None


def _citesteLa(f, poz, n):
	f.seek(poz)
	b = f.read(n)
	if len(b) != n:
		raise ValueError("scurt")
	return b


def _legaturi(f):
	f.seek(0)
	cap = f.read(64)
	if cap[:4] != b"\x7fELF" or len(cap) < 52:
		return None
	clasa, ordine = cap[4], cap[5]
	if clasa not in (1, 2) or ordine not in (1, 2) or (clasa == 2 and len(cap) < 64):
		return None
	o = "<" if ordine == 1 else ">"
	if clasa == 1:
		phoff, = struct.unpack(o + "I", cap[28:32])
		phentsize, phnum = struct.unpack(o + "HH", cap[42:46])
		fph, mph = o + "IIIIIIII", 32
	else:
		phoff, = struct.unpack(o + "Q", cap[32:40])
		phentsize, phnum = struct.unpack(o + "HH", cap[54:58])
		fph, mph = o + "IIQQQQQQ", 56
	if not phoff or not phnum or phnum > MAX_PH or phentsize < mph:
		return None
	ph = _citesteLa(f, phoff, phentsize * phnum)
	incarcate, dinamic = [], None
	for i in range(phnum):
		c = struct.unpack(fph, ph[i * phentsize:i * phentsize + mph])
		if clasa == 1:
			tip, offset, vaddr, filesz = c[0], c[1], c[2], c[4]
		else:
			tip, offset, vaddr, filesz = c[0], c[2], c[3], c[5]
		if tip == PT_LOAD:
			incarcate.append((vaddr, filesz, offset))
		elif tip == PT_DYNAMIC and dinamic is None:
			dinamic = (offset, filesz)
	if dinamic is None:
		return None
	marime = 8 if clasa == 1 else 16
	n = min(dinamic[1] // marime, MAX_DYN)
	date = _citesteLa(f, dinamic[0], n * marime)
	fd = o + ("iI" if clasa == 1 else "qQ")
	needed, rpath, soname, strtab, strsz = [], [], [], None, None
	for i in range(n):
		tag, val = struct.unpack(fd, date[i * marime:(i + 1) * marime])
		if tag == DT_NULL:
			break
		if tag == DT_NEEDED:
			needed.append(val)
		elif tag in (DT_RPATH, DT_RUNPATH):
			rpath.append(val)
		elif tag == DT_SONAME:
			soname.append(val)
		elif tag == DT_STRTAB:
			strtab = val
		elif tag == DT_STRSZ:
			strsz = val
	if strtab is None or not strsz:
		return None
	poz = None
	for vaddr, filesz, offset in incarcate:
		if vaddr <= strtab < vaddr + filesz:
			poz = strtab - vaddr + offset
			break
	if poz is None:
		return None
	strsz = min(strsz, MAX_STR)

	def nume(k):
		# numai numele cerute, nu toata tabela (la un modul mare are sute de KB)
		if k >= strsz:
			raise ValueError("nume")
		f.seek(poz + k)
		b = f.read(min(MAX_NUME, strsz - k))
		sfarsit = b.find(b"\0")
		return b[:sfarsit if sfarsit >= 0 else len(b)].decode("utf-8", "replace")

	cai = []
	for k in rpath:
		cai.extend(x for x in nume(k).split(":") if x)
	return {"needed": [nume(k) for k in needed], "rpath": cai, "soname": nume(soname[0]) if soname else ""}


def legaturi(cale):
	"""legaturiDinFisier pentru o cale, cu memoria (cale, marime, ora); None si cand fisierul nu se poate citi."""
	try:
		st = os.stat(cale)
	except (OSError, ValueError, TypeError):
		return None
	cheie = (st.st_size, getattr(st, "st_mtime_ns", st.st_mtime))
	vechi = _cache.get(cale)
	if vechi is not None and vechi[0] == cheie:
		return vechi[1]
	rez = None
	try:
		with open(cale, "rb") as f:
			rez = legaturiDinFisier(f)
	except (OSError, ValueError):
		rez = None
	if len(_cache) >= MAX_CACHE:
		_cache.clear()
	_cache[cale] = (cheie, rez)
	return rez


def altPythonDirect(cale):
	"""Versiunea celuilalt Python ("3.7") pentru care e facut fisierul (e chiar libpythonX.Y sau il cere direct), sau
	None. Fara biblioteci vecine."""
	v = _strain(cale)
	if v:
		return v
	l = legaturi(cale)
	if not l:
		return None
	for n in l["needed"]:
		v = _strain(n)
		if v:
			return v
	return None


def altPython(cale):
	"""(versiune, prin) cand fisierul e legat de alt Python: direct (prin = None) sau printr-o biblioteca din dosarul lui
	ori din RPATH/RUNPATH (prin = calea ei); altfel None."""
	v = _strain(cale)
	if v:
		return v, None
	l = legaturi(cale)
	if not l:
		return None
	for n in l["needed"]:
		v = _strain(n)
		if v:
			return v, None
	dosar = os.path.dirname(os.path.abspath(cale))
	dosare = [dosar] + [r.replace("$ORIGIN", dosar).replace("${ORIGIN}", dosar) for r in l["rpath"]]
	vazute = 0
	for n in l["needed"]:
		if "/" in n or _RUNTIME.match(n):
			continue
		for d in dosare:
			c = os.path.join(d, n)
			if not os.path.isfile(c):
				continue
			vazute += 1
			v = altPythonDirect(c)
			if v:
				return v, c
			break
		if vazute >= MAX_VECINI:
			break
	return None


def altPythonOcteti(date):
	"""Versiunea celuilalt Python pentru un fisier ELF dat ca octeti (copia setarilor, un .ipk), sau None."""
	import io
	l = legaturiDinFisier(io.BytesIO(date))
	if not l:
		return None
	for n in l["needed"]:
		v = _strain(n)
		if v:
			return v
	return _strain(l["soname"]) if l["soname"] else None


def eElf(date):
	return date[:4] == b"\x7fELF"


def exceptieDinLant(exc):
	"""Exceptia care poarta hdsAltPython (AltPython sau OSError-ul din ctypes): ea insasi sau una din lantul ei
	(__cause__, __context__), cand pluginul a prins-o si a dat alta; altfel None."""
	vazute = 0
	while exc is not None and vazute < 16:
		if getattr(exc, "hdsAltPython", None):
			return exc
		exc = exc.__cause__ or exc.__context__
		vazute += 1
	return None


def versiuneDinExceptie(exc):
	"""Versiunea celuilalt Python ("3.7") din exceptie sau din lantul ei, altfel None."""
	e = exceptieDinLant(exc)
	return e.hdsAltPython if e is not None else None


# ------------------------------------------------------------------ paza

def verificaModul(cale, nume=None):
	"""AltPython cand modulul de la cale e legat de alt Python; altfel nimic (si cand nu se stie)."""
	try:
		r = altPython(cale) if cale else None
	except Exception:
		r = None
	if r:
		print("[HdsAltPython] %s nu se incarca: e facut pentru Python %s%s" % (cale, r[0], (" (prin %s)" % r[1]) if r[1] else ""))
		raise AltPython(cale, r[0], nume, r[1])


def _numeDlopen(nume):
	"""(versiune, prin) pentru ce primeste dlopen-ul din ctypes, sau None"""
	if nume is None:
		return None
	if isinstance(nume, bytes):
		nume = os.fsdecode(nume)
	if not isinstance(nume, str):
		return None
	v = _strain(nume)
	if v:
		return v, None
	if ("/" in nume or os.sep in nume) and os.path.isfile(nume):
		return altPython(nume)
	return None


def dlopenPazit(dlopen):
	"""dlopen-ul din _ctypes, cu paza (o singura data)."""
	if getattr(dlopen, "hdsPazit", False):
		return dlopen

	def pazit(nume, *a, **k):
		try:
			r = _numeDlopen(nume)
		except Exception:
			r = None
		if r:
			print("[HdsAltPython] ctypes: %s nu se incarca: e facut pentru Python %s" % (nume, r[0]))
			e = OSError("%s: built for Python %s, this image has Python %s; not loaded" % (nume, r[0], textVersiune(ACUM)))
			e.hdsAltPython = r[0]
			raise e
		return dlopen(nume, *a, **k)

	pazit.hdsPazit = True
	pazit.__name__ = getattr(dlopen, "__name__", "dlopen")
	pazit.__doc__ = getattr(dlopen, "__doc__", None)
	return pazit


def _pazesteCtypes():
	m = sys.modules.get("_ctypes")
	if m is not None and hasattr(m, "dlopen"):
		m.dlopen = dlopenPazit(m.dlopen)
	c = sys.modules.get("ctypes")
	if c is not None and hasattr(c, "_dlopen"):
		c._dlopen = dlopenPazit(c._dlopen)


def pazeste():
	"""Pune paza o singura data. True daca e pusa (acum sau inainte)."""
	if _pazit[0]:
		return True
	from importlib import machinery
	L = machinery.ExtensionFileLoader
	creeaza, executa = L.create_module, L.exec_module

	def create_module(self, spec):
		verificaModul(getattr(spec, "origin", None) or getattr(self, "path", None), getattr(spec, "name", None))
		return creeaza(self, spec)

	def exec_module(self, module):
		executa(self, module)
		if getattr(module, "__name__", "") == "_ctypes":
			_pazesteCtypes()

	create_module.hdsPazit = True
	L.create_module = create_module
	L.exec_module = exec_module
	_pazesteCtypes()
	_pazit[0] = True
	return True
