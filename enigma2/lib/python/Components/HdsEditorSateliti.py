# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsEditorSateliti.py: lista satelitilor si a transponderelor lor (satellites.xml) pentru editorul de canale (pagina
# web /editor-canale, modul avansat): citirea, satelit nou / schimbat / sters, transponder nou / schimbat / sters,
# scrierea cu copie de siguranta si reincarcarea in NimManager.
#
# LOCUL: nucleul citeste numai /etc/tuxbox/satellites.xml (lib/dvb/db.cpp, eDVBDB::readSatellites, cale fixa), chemat
# din NimManager.readTransponders la pornire. Arborele e libxml2 strict (lib/base/xmltree.h: xmlReadFile fara RECOVER):
# un fisier rau inseamna niciun satelit, deci nimic nu se scrie fara recitirea lui si fara verificarea formei (expat).
# Nucleul ia ca satelit orice copil al radacinii cu name si position (vestul cu minus devine 3600 + x) si ca
# transponder orice copil al satelitului cu frequency, symbol_rate si polarization (fara unul din ele e sarit fara
# mesaj); celelalte atribute au valori implicite (DVB-S, QPSK, FEC auto). Aici se lucreaza cu <sat> si <transponder>;
# restul (declaratia, comentariile, alte elemente, atributele necunoscute) se pastreaza.
#
# CITIREA SI SCRIEREA: fisierul se imparte in bucati (text, comentarii, etichete) si fiecare element tine textul lui
# citit. La scriere un element neschimbat iese octet cu octet din textul citit; unul schimbat se face din nou, cu
# atributele neschimbate in forma lor citita si in ordinea lor, cele noi la sfarsit, cu spatiile luate de la vecini. Un
# fisier citit si scris fara schimbari iese identic. Codarea vine din declaratie (UTF-8 implicit); ce nu are loc in ea
# se scrie &#N;.
#
# DUBLURILE: doua transpondere ale aceluiasi satelit sunt unul singur cand au aceeasi polarizare, frecventele la cel
# mult DOI_MHZ si acelasi flux (is_id si t2mi_plp_id: fluxurile unui multistream stau pe aceeasi frecventa). Regula se
# aplica numai unui transponder nou si unuia caruia i se schimba frecventa, polarizarea sau fluxul: listele obisnuite
# au perechi apropiate (DVB-S si DVB-S2 pe aceeasi frecventa) care raman cum sunt.
#
# REINCARCAREA (reincarca): NimManager tine lista satelitilor (satList), iar alegerile din configurarea tunerelor s-au
# facut o data, la pornire, din ea: diseqcA..D se citesc dupa indicele din lista de la pornire (getSatListForNim:
# satList[diseqcA.index - 1]), iar modul avansat are cate o sectiune pe pozitie (advanced.sat[pozitie] in
# SecConfigure.update). Un satelit nou sau unul sters muta indicii sau lasa o pozitie fara sectiune, deci atunci nu se
# atinge nimic si lista noua se vede dupa repornirea interfetei. Cand pozitiile raman aceleasi (nume, flags,
# transpondere), lista se citeste din nou si se pune in NimManager; transponders e alt obiect, ca
# Components/HdsMotorPlafon.py sa puna din nou transponderele motorului in nucleu. Numele din alegerile configurarii
# tunerelor raman cele de la pornire.
#
# Nimic din enigma2 la incarcare: modulul se probeaza pe PC.

import os
import re
import stat
import time
import zlib

try:
	from Components import HdsEditorCanaleDate as D
except ImportError:  # pe PC, in probe
	import HdsEditorCanaleDate as D

try:
	try:
		from Components.HdsEditorCanale import Eroare as _EroareEditor
	except ImportError:
		from HdsEditorCanale import Eroare as _EroareEditor
except Exception:
	_EroareEditor = None

CALE = D.SATELITI                     # /etc/tuxbox/satellites.xml, singurul citit de nucleu
DOSAR_COPII = "/etc/enigma2/hds-copii-canale"
MAX_COPII = 5
LOC_MINIM = 512 * 1024
DOI_MHZ = 2000                        # kHz
LUNGIME_NUME = 100

FRECVENTA = (2000000, 30000000)       # kHz: de la banda S pana la banda Ka
RATA = (50000, 70000000)              # simboluri pe secunda
POLARIZARI = {"H": 0, "V": 1, "L": 2, "R": 3}
LITERA_POL = {0: "H", 1: "V", 2: "L", 3: "R"}
SISTEME = {"DVB-S": 0, "DVB-S2": 1}
MODULATII_DVBS = (0, 1)               # Auto, QPSK
FEC_DVBS = (0, 1, 2, 3, 4, 5)         # Auto, 1/2, 2/3, 3/4, 5/6, 7/8
# celelalte valori citite de nucleu ca numere (lib/dvb/db.cpp), cu intervalul primit
INTERVALE = {
	"fec_inner": (0, 15), "modulation": (0, 9), "rolloff": (0, 2), "pilot": (0, 2), "inversion": (0, 2),
	"is_id": (-1, 255), "pls_mode": (0, 2), "pls_code": (0, 0x3FFFF), "t2mi_plp_id": (-1, 255),
	"t2mi_pid": (0, 8191), "tsid": (-1, 65535), "onid": (-1, 65535)}
# ordinea atributelor la un transponder nou (cea din listele obisnuite), apoi cele necunoscute
ORDINE_TP = ("frequency", "symbol_rate", "polarization", "fec_inner", "system", "modulation", "rolloff", "pilot",
	"inversion", "is_id", "pls_mode", "pls_code", "t2mi_plp_id", "t2mi_pid", "tsid", "onid")
OBLIGATORII = ("frequency", "symbol_rate", "polarization")
# valorile implicite ale nucleului, scrise la un transponder nou care nu le are: FEC auto, DVB-S, QPSK
IMPLICITE_TP = (("fec_inner", "0"), ("system", "0"), ("modulation", "1"))
FLAGS_IMPLICIT = 1                    # al listelor obisnuite

_NUME = r"[A-Za-z_:][-A-Za-z0-9_.:]*"
_VAL = r"(?:\"[^\"]*\"|'[^']*')"
_START = re.compile(r"<(%s)((?:\s+%s\s*=\s*%s)*)(\s*/?)>" % (_NUME, _NUME, _VAL))
_ATR = re.compile(r"(\s+)(%s)\s*=\s*(%s)" % (_NUME, _VAL))
_END = re.compile(r"</(%s)\s*>" % _NUME)
_NUME_ATR = re.compile(r"^[A-Za-z_][-A-Za-z0-9_.]*$")
_ENT = re.compile(r"&(#[0-9]+|#[xX][0-9A-Fa-f]+|amp|lt|gt|quot|apos);")
_ENT_NUME = {"amp": "&", "lt": "<", "gt": ">", "quot": '"', "apos": "'"}
_DECLARATIE = re.compile(br"^(?:\xef\xbb\xbf)?\s*<\?xml[^>]*?encoding\s*=\s*[\"']([A-Za-z0-9._-]+)[\"']")
_POZ_TEXT = re.compile(r"^(\d{1,3}(?:\.\d)?)([EW])$")
_POZ_NUMAR = re.compile(r"^-?\d{1,4}$")
_COPIE = re.compile(r"^satellites-(\d{8}-\d{6})(?:-(\d+))?\.xml$")


def _t(text):
	"""Traducerea enigma2 (_ din builtins); pe PC textul asa cum e."""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _jurnal(text):
	print("[HdsEditorSateliti] %s" % text)


if _EroareEditor is not None:
	class Eroare(_EroareEditor):
		"""O operatie care nu se poate face; mesaj() e textul pentru om (tradus). Copil al erorii editorului, ca
		pagina web sa o trateze la fel."""
else:
	class Eroare(Exception):
		"""O operatie care nu se poate face; mesaj() e textul pentru om (tradus)."""

		def __init__(self, mesaj):
			Exception.__init__(self, mesaj)
			self.text = mesaj

		def mesaj(self):
			return self.text


# ---------------------------------------------------------------- texte si valori

def _dez(valoare):
	"""Valoarea unui atribut asa cum o vede un parser XML: spatiile albe devin spatiu, entitatile se inlocuiesc."""
	valoare = valoare.replace("\r\n", " ").replace("\t", " ").replace("\n", " ").replace("\r", " ")

	def inlocuieste(m):
		e = m.group(1)
		if e[0] == "#":
			try:
				return chr(int(e[2:], 16) if e[1] in "xX" else int(e[1:]))
			except (ValueError, OverflowError):
				return m.group(0)
		return _ENT_NUME[e]
	return _ENT.sub(inlocuieste, valoare)


def _scapa(valoare, codare):
	"""Valoarea scrisa intr-un atribut intre ghilimele duble."""
	rez = []
	for c in valoare:
		if c == "&":
			rez.append("&amp;")
		elif c == "<":
			rez.append("&lt;")
		elif c == ">":
			rez.append("&gt;")
		elif c == '"':
			rez.append("&quot;")
		elif c in "\t\n\r":
			rez.append("&#%d;" % ord(c))
		elif ord(c) < 128:
			rez.append(c)
		else:
			try:
				c.encode(codare)
				rez.append(c)
			except (UnicodeError, LookupError):
				rez.append("&#%d;" % ord(c))
	return "".join(rez)


def _bun_de_scris(text):
	"""Fara caractere de control si fara jumatati de pereche (nu se pot scrie intr-un fisier XML)."""
	for c in text:
		o = ord(c)
		if o < 32 or 0xD800 <= o <= 0xDFFF or o in (0xFFFE, 0xFFFF):
			return False
	return True


def _intreg(nume, valoare):
	if isinstance(valoare, bool):
		raise Eroare(_t("Valoarea pentru %s trebuie să fie un număr întreg.") % nume)
	if isinstance(valoare, int):
		return valoare
	try:
		return int(("%s" % (valoare,)).strip(), 10)
	except ValueError:
		raise Eroare(_t("Valoarea pentru %s trebuie să fie un număr întreg.") % nume)


def _int_sau_none(text):
	try:
		return int(text, 10)
	except (TypeError, ValueError):
		return None


def norm(poz):
	"""Pozitia ca in NimManager: 0..3599 (vestul cu minus din fisier devine 3600 + x)."""
	return poz + 3600 if poz < 0 else poz


def pozitie(valoare):
	"""192, "192", "-300", "3300", "19.2E", "19,2°E", "30W", "30.0 W" -> pozitia scrisa in fisier: zecimi de grad,
	vestul cu minus (192, -300). Un numar intre 1801 si 3599 e vestul scris ca in NimManager. Altfel Eroare."""
	if isinstance(valoare, bool):
		raise Eroare(_t("Poziția „%s” nu e bună. Scrie-o ca 19,2E sau 30,0W.") % (valoare,))
	if isinstance(valoare, int):
		p = valoare
	else:
		text = ("%s" % (valoare,)).strip().upper().replace(",", ".").replace(u"°", "").replace(" ", "")
		m = _POZ_TEXT.match(text)
		if m:
			p = int(round(float(m.group(1)) * 10))
			if p > 1800:
				raise Eroare(_t("Poziția trebuie să fie între 180,0W și 180,0E."))
			if m.group(2) == "W":
				p = -p
		elif _POZ_NUMAR.match(text):
			p = int(text)
		else:
			raise Eroare(_t("Poziția „%s” nu e bună. Scrie-o ca 19,2E sau 30,0W.") % (valoare,))
	if 1800 < p < 3600:
		p -= 3600
	if not -1800 <= p <= 1800:
		raise Eroare(_t("Poziția trebuie să fie între 180,0W și 180,0E."))
	return p


def _text_frecventa(khz):
	if khz % 1000 == 0:
		return "%d" % (khz // 1000)
	return ("%.3f" % (khz / 1000.0)).rstrip("0").rstrip(".").replace(".", ",")


# ---------------------------------------------------------------- elementele

class _Element(object):
	"""Un element din fisier. atr: [[nume, valoare, brut]], cu brut = textul citit al atributului (cu spatiul
	dinainte), None dupa o schimbare. copii: text (str) si elemente, in ordinea din fisier. coada: ce sta intre
	ultimul atribut si ">" (" /", "/", "")."""

	def __init__(self, tag, atr=None, gol=False, start=None, coada=None):
		self.tag = tag
		self.atr = atr if atr is not None else []
		self.copii = []
		self.gol = gol
		self._start = start
		self._coada = coada
		self._sfarsit = None
		self._orig = self._semn() if start is not None else None

	def _semn(self):
		return (tuple((a[0], a[1]) for a in self.atr), self.gol)

	@property
	def atribute(self):
		"""[(nume, valoare)] ca text, in ordinea din fisier."""
		return [(a[0], a[1]) for a in self.atr]

	def get(self, nume, implicit=None):
		for a in self.atr:
			if a[0] == nume:
				return a[1]
		return implicit

	def _pune(self, nume, valoare):
		for a in self.atr:
			if a[0] == nume:
				if a[1] != valoare:
					a[1], a[2] = valoare, None
				return
		self.atr.append([nume, valoare, None])

	def _eticheta(self, codare):
		parti = ["<", self.tag]
		for nume, valoare, brut in self.atr:
			parti.append(brut if brut is not None else ' %s="%s"' % (nume, _scapa(valoare, codare)))
		coada = self._coada
		if self.gol:
			parti.append(coada if coada and "/" in coada else " /")
		elif coada and "/" not in coada:
			parti.append(coada)
		parti.append(">")
		return "".join(parti)

	def _text(self, out, codare):
		if self._start is not None and self._semn() == self._orig:
			out.append(self._start)
		else:
			out.append(self._eticheta(codare))
		if not self.gol:
			for c in self.copii:
				if isinstance(c, str):
					out.append(c)
				else:
					c._text(out, codare)
			out.append(self._sfarsit or "</%s>" % self.tag)


class Transponder(_Element):
	"""Un <transponder>: atributele ca text (atribute, get); frequency, symbol_rate, polarization... ca text sau None."""

	def __getattr__(self, nume):
		if nume in ORDINE_TP:
			return self.get(nume)
		raise AttributeError(nume)

	def _identitate(self):
		"""(polarizare, frecventa kHz, is_id, t2mi_plp_id) pentru regula dublurilor; None fara frecventa/polarizare."""
		f, p = _int_sau_none(self.get("frequency")), _int_sau_none(self.get("polarization"))
		if f is None or p is None:
			return None
		isi, plp = _int_sau_none(self.get("is_id")), _int_sau_none(self.get("t2mi_plp_id"))
		return (p, f, isi if isi is not None and 0 <= isi <= 255 else -1,
			plp if plp is not None and 0 <= plp <= 255 else -1)


class Satelit(_Element):
	"""Un <sat>: name, flags (text sau None), position (intreg, ca in fisier), poz (0..3599), transpondere."""

	@property
	def name(self):
		return self.get("name", "")

	@property
	def flags(self):
		return self.get("flags")

	@property
	def position(self):
		return _int_sau_none(self.get("position"))

	@property
	def poz(self):
		p = self.position
		return None if p is None else norm(p)

	@property
	def transpondere(self):
		return [c for c in self.copii if isinstance(c, Transponder)]

	def chei(self):
		"""[(cheie, transponder)]. Cheia vine din continut (frecventa, polarizarea si suma tuturor atributelor), deci
		e aceeasi la o noua citire a fisierului, iar o cheie veche nu nimereste alt transponder; doua transpondere
		identice primesc #2, #3."""
		vazute = {}
		rez = []
		for tp in self.transpondere:
			semn = "\x00".join("%s=%s" % a for a in tp.atribute).encode("utf-8", "surrogatepass")
			k = "%s-%s-%08x" % (tp.get("frequency", ""), tp.get("polarization", ""), zlib.crc32(semn) & 0xFFFFFFFF)
			n = vazute.get(k, 0) + 1
			vazute[k] = n
			rez.append((k if n == 1 else "%s#%d" % (k, n), tp))
		return rez

	def cheie(self, tp):
		for k, t in self.chei():
			if t is tp:
				return k
		return None

	def transponder(self, cheie):
		for k, t in self.chei():
			if k == cheie:
				return t
		raise Eroare(_t("Transponderul nu mai există pe %s. Deschide din nou lista.") % D.text_pozitie(self.poz))


def _fabrica(tag, parinte, radacina):
	if tag == "sat" and radacina is not None and parinte is radacina:
		return Satelit
	if tag == "transponder" and isinstance(parinte, Satelit):
		return Transponder
	return _Element


# ---------------------------------------------------------------- citirea

def _codarea(date):
	"""(codarea, erorile) pentru decode si encode: din declaratie, UTF-8 implicit."""
	m = _DECLARATIE.match(date)
	nume = m.group(1).decode("ascii").lower().replace("_", "-") if m else "utf-8"
	if nume in ("utf-8", "utf8"):
		return "utf-8", "surrogateescape"
	if nume in ("iso-8859-1", "latin-1", "latin1", "iso8859-1", "l1"):
		return "latin-1", "strict"
	try:
		date.decode(nume)
		return nume, "strict"
	except (LookupError, UnicodeError):
		return "latin-1", "strict"   # fiecare octet ramane el insusi


class _Stricat(Exception):
	def __init__(self, rand):
		Exception.__init__(self, rand)
		self.rand = rand


def _analizeaza(text):
	"""text -> (bucatile de pe primul nivel, radacina). Ridica _Stricat(rand) la o forma pe care nu o inteleg."""
	noduri = []
	stiva = []
	radacina = None
	i, n = 0, len(text)

	def adauga(x):
		(stiva[-1].copii if stiva else noduri).append(x)

	def rand(k):
		return text.count("\n", 0, k) + 1
	while i < n:
		j = text.find("<", i)
		if j < 0:
			j = n
		if j > i:
			adauga(text[i:j])
			i = j
			continue
		if text.startswith("<!--", i):
			k = text.find("-->", i + 4)
			if k < 0:
				raise _Stricat(rand(i))
			adauga(text[i:k + 3])
			i = k + 3
		elif text.startswith("<?", i):
			k = text.find("?>", i + 2)
			if k < 0:
				raise _Stricat(rand(i))
			adauga(text[i:k + 2])
			i = k + 2
		elif text.startswith("<![CDATA[", i):
			k = text.find("]]>", i + 9)
			if k < 0:
				raise _Stricat(rand(i))
			adauga(text[i:k + 3])
			i = k + 3
		elif text.startswith("<!", i):
			k = text.find(">", i)
			if k >= 0 and "[" in text[i:k]:
				k = text.find("]>", i)
				k = k + 1 if k >= 0 else -1
			if k < 0:
				raise _Stricat(rand(i))
			adauga(text[i:k + 1])
			i = k + 1
		elif text.startswith("</", i):
			m = _END.match(text, i)
			if not m or not stiva or stiva[-1].tag != m.group(1):
				raise _Stricat(rand(i))
			stiva.pop()._sfarsit = m.group(0)
			i = m.end()
		else:
			m = _START.match(text, i)
			if not m:
				raise _Stricat(rand(i))
			atr = []
			vazute = set()
			for a in _ATR.finditer(m.group(2)):
				nume = a.group(2)
				if nume in vazute:
					raise _Stricat(rand(i))
				vazute.add(nume)
				atr.append([nume, _dez(a.group(3)[1:-1]), a.group(0)])
			gol = m.group(3).endswith("/")
			parinte = stiva[-1] if stiva else None
			if parinte is None and radacina is not None:
				raise _Stricat(rand(i))      # al doilea element pe primul nivel
			el = _fabrica(m.group(1), parinte, radacina)(m.group(1), atr, gol, m.group(0), m.group(3))
			adauga(el)
			if parinte is None:
				radacina = el
			if not gol:
				stiva.append(el)
			i = m.end()
	if stiva:
		raise _Stricat(rand(n))
	return noduri, radacina


class Sateliti(object):
	"""Lista satelitilor citita dintr-un satellites.xml. lista: satelitii folositi de nucleu (<sat> cu name si position
	intreaga), in ordinea din fisier. Operatiile schimba obiectul pe loc; o valoare gresita ridica Eroare (cu textul
	pentru om) inainte de orice schimbare."""

	def __init__(self, date, cale=None):
		self.cale = cale
		self.codare, self._erori = _codarea(date)
		text = date.decode(self.codare, self._erori)
		try:
			self._noduri, self._radacina = _analizeaza(text)
		except _Stricat as e:
			raise Eroare(_t("Lista sateliților (%s) nu se poate citi: e stricată pe rândul %d.") % (cale or "-", e.rand))
		if self._radacina is None:
			raise Eroare(_t("Lista sateliților (%s) e goală sau nu are forma unui satellites.xml.") % (cale or "-"))
		self._original = date
		self._nl = "\r\n" if "\r\n" in text else "\n"
		self.schimbari = 0

	# ------------------------------------------------ vederea

	@property
	def lista(self):
		return [c for c in self._radacina.copii if isinstance(c, Satelit) and c.poz is not None and
			c.get("name") is not None]

	def gaseste(self, poz):
		"""Satelitul de pe `poz` (0..3599, ca in fisier sau ca text: 192, -300, 3300, "30W") sau None."""
		try:
			p = norm(pozitie(poz))
		except Eroare:
			return None
		for s in self.lista:
			if s.poz == p:
				return s
		return None

	def satelit(self, poz):
		"""Ca gaseste, dar Eroare cand nu exista."""
		s = self.gaseste(poz)
		if s is None:
			try:
				text = D.text_pozitie(norm(pozitie(poz)))
			except Eroare:
				text = "%s" % (poz,)
			raise Eroare(_t("Nu există niciun satelit pe %s.") % text)
		return s

	def octeti(self):
		"""Fisierul de acum, ca octeti."""
		out = []
		for c in self._noduri:
			if isinstance(c, str):
				out.append(c)
			else:
				c._text(out, self.codare)
		return "".join(out).encode(self.codare, self._erori)

	def structura(self):
		"""[(atributele satelitului, [atributele fiecarui transponder])] ale tuturor <sat>, pentru comparatii."""
		return [(tuple(s.atribute), [tuple(t.atribute) for t in s.transpondere])
			for s in self._radacina.copii if isinstance(s, Satelit)]

	# ------------------------------------------------ spatiile

	def _spatiu_sat(self):
		copii = self._radacina.copii
		for i, c in enumerate(copii):
			if isinstance(c, Satelit) and i > 0 and isinstance(copii[i - 1], str) and not copii[i - 1].strip():
				return copii[i - 1]
		return self._nl + "\t"

	def _spatiu_tp(self):
		for s in self._radacina.copii:
			if isinstance(s, Satelit):
				for i, c in enumerate(s.copii):
					if isinstance(c, Transponder) and i > 0 and isinstance(s.copii[i - 1], str) and \
							not s.copii[i - 1].strip():
						return s.copii[i - 1]
		return self._spatiu_sat() + "\t"

	def _coada_tp(self):
		for s in self._radacina.copii:
			if isinstance(s, Satelit):
				for t in s.transpondere:
					if t.gol and t._coada:
						return t._coada
		return " /"

	@staticmethod
	def _scoate_din(parinte, el):
		"""Elementul si spatiul dinaintea lui."""
		copii = parinte.copii
		for i, c in enumerate(copii):
			if c is el:
				j = i - 1 if i > 0 and isinstance(copii[i - 1], str) and not copii[i - 1].strip() else i
				del copii[j:i + 1]
				return

	@staticmethod
	def _pune_in(parinte, el, inainte_de, spatiu, spatiu_inchidere):
		"""Elementul inaintea lui `inainte_de` (None: dupa ultimul element), cu spatiile vecinilor."""
		copii = parinte.copii
		if parinte.gol:
			parinte.gol = False
			parinte._sfarsit = "</%s>" % parinte.tag
		if inainte_de is not None:
			for i, c in enumerate(copii):
				if c is inainte_de:
					prec = copii[i - 1] if i > 0 and isinstance(copii[i - 1], str) and not copii[i - 1].strip() \
						else spatiu
					copii[i:i] = [el, prec]
					return
		ultim = -1
		for i, c in enumerate(copii):
			if isinstance(c, type(el)):
				ultim = i
		if ultim >= 0:
			copii[ultim + 1:ultim + 1] = [spatiu, el]      # dupa ultimul frate de acelasi fel
		elif copii and isinstance(copii[-1], str) and not copii[-1].strip():
			copii[len(copii) - 1:len(copii) - 1] = [spatiu, el]   # inaintea spatiului de dinainte de inchidere
		else:
			copii.extend([spatiu, el, spatiu_inchidere])

	# ------------------------------------------------ satelitii

	@staticmethod
	def _ordine(p):
		p = norm(p)
		return p - 3600 if p > 1800 else p

	def _locul_satelitului(self, p):
		"""Primul satelit de dupa pozitia p (de la vest la est, ca NimManager.sortFunc) sau None."""
		cheie = self._ordine(p)
		for s in self.lista:
			if self._ordine(s.position) > cheie:
				return s
		return None

	@staticmethod
	def _verifica_nume(nume):
		nume = ("%s" % (nume if nume is not None else "",)).strip()
		if not nume:
			raise Eroare(_t("Scrie numele satelitului."))
		if len(nume) > LUNGIME_NUME:
			raise Eroare(_t("Numele satelitului e prea lung: cel mult %d de caractere.") % LUNGIME_NUME)
		if not _bun_de_scris(nume):
			raise Eroare(_t("Numele satelitului are un caracter care nu se poate scrie în listă."))
		return nume

	@staticmethod
	def _verifica_flags(flags):
		try:
			f = _intreg("flags", flags)
		except Eroare:
			f = -1
		if not 0 <= f <= 255:
			raise Eroare(_t("Câmpul flags trebuie să fie un număr între 0 și 255."))
		return f

	def _ocupata(self, p, fara=None):
		for s in self.lista:
			if s is not fara and s.poz == norm(p):
				raise Eroare(_t("Pe %s există deja satelitul %s.") % (D.text_pozitie(norm(p)), s.name))

	def satelit_nou(self, nume, poz, flags=FLAGS_IMPLICIT):
		"""Satelit nou, fara transpondere, pus la locul lui de la vest la est (flags None = FLAGS_IMPLICIT). -> Satelit"""
		nume = self._verifica_nume(nume)
		p = pozitie(poz)
		f = self._verifica_flags(FLAGS_IMPLICIT if flags is None else flags)
		self._ocupata(p)
		s = Satelit("sat", [["name", nume, None], ["flags", "%d" % f, None], ["position", "%d" % p, None]])
		s._sfarsit = "</sat>"
		spatiu = self._spatiu_sat()
		s.copii = [spatiu]
		self._pune_in(self._radacina, s, self._locul_satelitului(p), spatiu, self._nl)
		self.schimbari += 1
		return s

	def schimba_satelit(self, poz, nume=None, pozitie_noua=None, flags=None):
		"""Numele, pozitia si/sau flags (None = ramane). La alta pozitie satelitul se muta la locul ei. -> Satelit"""
		s = self.satelit(poz)
		nume = self._verifica_nume(nume) if nume is not None else None
		p = pozitie(pozitie_noua) if pozitie_noua is not None else None
		f = self._verifica_flags(flags) if flags is not None else None
		if p is not None and norm(p) != s.poz:
			self._ocupata(p, s)
		if nume is not None:
			s._pune("name", nume)
		if f is not None and _int_sau_none(s.get("flags")) != f:
			s._pune("flags", "%d" % f)
		if p is not None and p != s.position:
			mutat = norm(p) != s.poz
			s._pune("position", "%d" % p)
			if mutat:
				self._scoate_din(self._radacina, s)
				spatiu = self._spatiu_sat()
				self._pune_in(self._radacina, s, self._locul_satelitului(p), spatiu, self._nl)
		self.schimbari += 1
		return s

	def sterge_satelit(self, poz):
		"""Satelitul cu toate transponderele lui. -> satelitul scos"""
		s = self.satelit(poz)
		self._scoate_din(self._radacina, s)
		self.schimbari += 1
		return s

	# ------------------------------------------------ transponderele

	@staticmethod
	def _valoare_tp(nume, valoare):
		"""Valoarea unui atribut ca text, verificata; Eroare cu textul pentru om."""
		if nume == "frequency":
			v = _intreg(nume, valoare)
			if v < FRECVENTA[0] and FRECVENTA[0] <= v * 1000 <= FRECVENTA[1]:
				raise Eroare(_t("Frecvența pare scrisă în MHz. Scrie-o în kHz: %d.") % (v * 1000))
			if not FRECVENTA[0] <= v <= FRECVENTA[1]:
				raise Eroare(_t("Frecvența trebuie să fie în kHz, între %d și %d.") % FRECVENTA)
			return "%d" % v
		if nume == "symbol_rate":
			v = _intreg(nume, valoare)
			if v < RATA[0] and RATA[0] <= v * 1000 <= RATA[1]:
				raise Eroare(_t("Rata de simbol pare scrisă în kS/s. Scrie-o în simboluri pe secundă: %d.") % (v * 1000))
			if not RATA[0] <= v <= RATA[1]:
				raise Eroare(_t("Rata de simbol trebuie să fie în simboluri pe secundă, între %d și %d.") % RATA)
			return "%d" % v
		if nume in ("polarization", "system"):
			text = ("%s" % (valoare,)).strip().upper()
			tabel, valide = (POLARIZARI, (0, 1, 2, 3)) if nume == "polarization" else (SISTEME, (0, 1))
			if text in tabel:
				return "%d" % tabel[text]
			try:
				v = _intreg(nume, valoare)
			except Eroare:
				v = -1
			if v not in valide:
				if nume == "polarization":
					raise Eroare(_t("Polarizarea trebuie să fie H, V, L sau R (0, 1, 2 sau 3)."))
				raise Eroare(_t("Sistemul trebuie să fie DVB-S sau DVB-S2 (0 sau 1)."))
			return "%d" % v
		if nume in INTERVALE:
			v = _intreg(nume, valoare)
			mic, mare = INTERVALE[nume]
			if not mic <= v <= mare:
				raise Eroare(_t("Valoarea pentru %s trebuie să fie între %d și %d.") % (nume, mic, mare))
			return "%d" % v
		if not _NUME_ATR.match(nume or "") or nume.lower().startswith("xml"):
			raise Eroare(_t("Numele atributului „%s” nu e bun.") % (nume,))
		text = "%s" % (valoare,)
		if not _bun_de_scris(text):
			raise Eroare(_t("Valoarea atributului %s are un caracter care nu se poate scrie în listă.") % nume)
		return text

	@staticmethod
	def _verifica_dvbs(atr, schimbate):
		"""DVB-S: numai QPSK (sau auto) si FEC-urile lui; se cere numai cand se pun sistemul, modulatia sau FEC-ul."""
		if not schimbate & set(("system", "modulation", "fec_inner")):
			return
		valori = dict((a[0], a[1]) for a in atr)
		if _int_sau_none(valori.get("system", "0")) != 0:
			return
		if _int_sau_none(valori.get("modulation", "1")) not in MODULATII_DVBS:
			raise Eroare(_t("La DVB-S modulația e numai QPSK (1) sau Auto (0)."))
		if _int_sau_none(valori.get("fec_inner", "0")) not in FEC_DVBS:
			raise Eroare(_t("La DVB-S FEC-ul e Auto (0), 1/2, 2/3, 3/4, 5/6 sau 7/8 (1-5)."))

	@staticmethod
	def _verifica_dublura(s, tp, exclus):
		ident = tp._identitate()
		if ident is None:
			return
		for alt in s.transpondere:
			if alt is exclus:
				continue
			a = alt._identitate()
			if a is not None and a[0] == ident[0] and a[2:] == ident[2:] and abs(a[1] - ident[1]) <= DOI_MHZ:
				raise Eroare(_t("Pe %s există deja transponderul %s, cu aceeași polarizare, la cel mult 2 MHz.") %
					(D.text_pozitie(s.poz), "%s %s" % (_text_frecventa(a[1]), LITERA_POL.get(a[0], "%d" % a[0]))))

	@staticmethod
	def _locul_transponderului(s, tp):
		"""Primul transponder cu frecventa mai mare (None: la sfarsit)."""
		f = _int_sau_none(tp.get("frequency"))
		for alt in s.transpondere:
			fa = _int_sau_none(alt.get("frequency"))
			if alt is not tp and f is not None and fa is not None and fa > f:
				return alt
		return None

	def transponder_nou(self, poz, valori):
		"""valori: {atribut: valoare} (numerele ca int sau text; polarizarea si ca H/V/L/R, sistemul si ca DVB-S /
		DVB-S2). Se cer frequency (kHz), symbol_rate (simboluri/s) si polarization; fec_inner, system si modulation
		lipsa se scriu cu valorile implicite ale nucleului. Se pune in ordinea frecventelor. -> Transponder"""
		s = self.satelit(poz)
		valori = dict(valori or {})
		for nume in OBLIGATORII:
			if valori.get(nume) in (None, ""):
				raise Eroare(_t("Transponderul are nevoie de frecvență, rată de simbol și polarizare."))
		curate = {}
		for nume, valoare in valori.items():
			if valoare is not None:
				curate[nume] = self._valoare_tp(nume, valoare)
		for nume, implicit in IMPLICITE_TP:
			curate.setdefault(nume, implicit)
		atr = [[n, curate[n], None] for n in ORDINE_TP if n in curate]
		atr += [[n, v, None] for n, v in curate.items() if n not in ORDINE_TP]
		self._verifica_dvbs(atr, set(curate))
		tp = Transponder("transponder", atr, True, None, self._coada_tp())
		self._verifica_dublura(s, tp, None)
		self._pune_in(s, tp, self._locul_transponderului(s, tp), self._spatiu_tp(), self._spatiu_sat())
		self.schimbari += 1
		return tp

	def schimba_transponder(self, poz, cheie, valori):
		"""valori: {atribut: valoare}; None (sau "") scoate atributul (frecventa, rata si polarizarea nu se pot scoate).
		Atributele neschimbate raman cum erau scrise; cele noi se pun la sfarsit. La alta frecventa transponderul se
		muta la locul ei. -> Transponder"""
		s = self.satelit(poz)
		tp = s.transponder(cheie)
		atr = [list(a) for a in tp.atr]
		schimbate = set()
		for nume, valoare in (valori or {}).items():
			if valoare is None or valoare == "":
				if nume in OBLIGATORII:
					raise Eroare(_t("Transponderul are nevoie de frecvență, rată de simbol și polarizare."))
				if any(a[0] == nume for a in atr):
					atr = [a for a in atr if a[0] != nume]
					schimbate.add(nume)
				continue
			text = self._valoare_tp(nume, valoare)
			for a in atr:
				if a[0] == nume:
					if a[1] != text:
						a[1], a[2] = text, None
						schimbate.add(nume)
					break
			else:
				atr.append([nume, text, None])
				schimbate.add(nume)
		if not schimbate:
			return tp
		self._verifica_dvbs(atr, schimbate)
		nou = Transponder("transponder", atr)
		if nou._identitate() != tp._identitate():
			self._verifica_dublura(s, nou, tp)
		frecventa = tp.get("frequency")
		tp.atr = atr
		if tp.get("frequency") != frecventa:
			self._scoate_din(s, tp)
			self._pune_in(s, tp, self._locul_transponderului(s, tp), self._spatiu_tp(), self._spatiu_sat())
		self.schimbari += 1
		return tp

	def sterge_transponder(self, poz, cheie):
		"""-> transponderul scos"""
		s = self.satelit(poz)
		tp = s.transponder(cheie)
		self._scoate_din(s, tp)
		self.schimbari += 1
		return tp


# ---------------------------------------------------------------- fisierul

def citeste(cale=None):
	"""Lista satelitilor din `cale` (implicit CALE, fisierul citit de nucleu). -> Sateliti; Eroare daca lipseste sau
	e stricat."""
	cale = cale or CALE
	try:
		with open(cale, "rb") as f:
			date = f.read()
	except (IOError, OSError):
		raise Eroare(_t("Nu pot citi lista sateliților (%s).") % cale)
	return Sateliti(date, cale)


def _scrie_sigur(cale, date, mod=None):
	nou = cale + ".nou"
	try:
		with open(nou, "wb") as f:
			f.write(date)
			f.flush()
			os.fsync(f.fileno())
		if mod is not None:
			try:
				os.chmod(nou, mod)
			except OSError:
				pass
		os.replace(nou, cale)
	except Exception:
		try:
			os.remove(nou)
		except OSError:
			pass
		raise


def _fsync_dosar(dosar):
	try:
		fd = os.open(dosar, os.O_RDONLY)
		try:
			os.fsync(fd)
		finally:
			os.close(fd)
	except (OSError, AttributeError):
		pass


def _loc_liber(dosar):
	try:
		st = os.statvfs(dosar)
		return st.f_bavail * st.f_frsize
	except (OSError, AttributeError):
		return None


def _bine_format(date):
	"""True / False dupa expat; None cand expat lipseste."""
	try:
		import xml.parsers.expat as expat
	except ImportError:
		return None
	p = expat.ParserCreate()
	try:
		p.Parse(date, True)
		return True
	except Exception:
		return False


def dosar_copii(cale):
	"""DOSAR_COPII pentru fisierul nucleului, altfel hds-copii-canale langa fisier."""
	if os.path.abspath(cale) == os.path.abspath(CALE):
		return DOSAR_COPII
	return os.path.join(os.path.dirname(os.path.abspath(cale)), "hds-copii-canale")


def lista_copii(dosar):
	"""[(nume, cale)] ale copiilor satellites-AAAAMMZZ-HHMMSS[-n].xml din `dosar`, cea mai noua intai."""
	try:
		nume = os.listdir(dosar)
	except OSError:
		return []
	rez = []
	for f in nume:
		m = _COPIE.match(f)
		if m:
			rez.append(((m.group(1), int(m.group(2) or 1)), f))
	rez.sort(reverse=True)
	return [(f, os.path.join(dosar, f)) for _k, f in rez]


def _fa_copie(cale, dosar):
	"""Copia datata a fisierului de acum; raman ultimele MAX_COPII, iar cea abia facuta nu se sterge niciodata
	(ceasul receptorului poate fi in urma). -> calea copiei sau None (nu era fisier)."""
	try:
		with open(cale, "rb") as f:
			vechi = f.read()
	except (IOError, OSError):
		return None
	try:
		os.makedirs(dosar)
	except OSError:
		pass
	liber = _loc_liber(dosar)
	if liber is not None and liber < len(vechi) + LOC_MINIM:
		raise Eroare(_t("Nu e loc destul în memoria receptorului pentru lista sateliților."))
	baza = "satellites-" + time.strftime("%Y%m%d-%H%M%S", time.localtime())
	copie = os.path.join(dosar, baza + ".xml")
	k = 2
	while os.path.exists(copie):
		copie = os.path.join(dosar, "%s-%d.xml" % (baza, k))
		k += 1
	_scrie_sigur(copie, vechi)
	_fsync_dosar(dosar)
	ramase = [c for _f, c in lista_copii(dosar) if c != copie]
	for c in ramase[max(0, MAX_COPII - 1):]:
		try:
			os.remove(c)
		except OSError:
			pass
	return copie


def scrie(sateliti, cale=None, copie_in=None):
	"""Copia fisierului vechi (in `copie_in`, implicit dosar_copii(cale)), apoi scrierea sigura (.nou, fsync, rename).
	-> calea copiei; None cand nu era fisier vechi sau cand pe disc e deja exact aceeasi lista (nu se scrie nimic).
	Eroare cu textul pentru om cand fisierul s-a schimbat pe disc de la citire, cand nu e loc sau cand scrierea nu
	merge; fisierul vechi ramane atunci neatins."""
	cale = cale or sateliti.cale or CALE
	date = sateliti.octeti()
	# lista scrisa trebuie sa se citeasca inapoi la fel si sa fie XML bun (nucleul nu iarta nicio greseala)
	try:
		inapoi = Sateliti(date, cale)
	except Eroare:
		inapoi = None
	if inapoi is None or inapoi.structura() != sateliti.structura() or \
			(_bine_format(date) is False and _bine_format(sateliti._original) is not False):
		_jurnal("lista facuta nu se citeste inapoi la fel; nu se scrie")
		raise Eroare(_t("Lista nouă a sateliților nu a ieșit bine, așa că nu s-a scris. Fișierul vechi a rămas cum era."))
	acum = None
	try:
		with open(cale, "rb") as f:
			acum = f.read()
	except (IOError, OSError):
		pass
	if acum is not None and sateliti.cale and os.path.abspath(cale) == os.path.abspath(sateliti.cale) and \
			acum != sateliti._original:
		raise Eroare(_t("Lista sateliților s-a schimbat între timp pe receptor. Deschide-o din nou, ca să nu pierzi schimbările de acolo."))
	if acum == date:
		return None
	dosar = os.path.dirname(os.path.abspath(cale))
	liber = _loc_liber(dosar)
	if liber is not None and liber < len(date) + LOC_MINIM:
		raise Eroare(_t("Nu e loc destul în memoria receptorului pentru lista sateliților."))
	copie = None
	if acum is not None:
		try:
			copie = _fa_copie(cale, copie_in or dosar_copii(cale))
		except Eroare:
			raise
		except Exception as e:
			raise Eroare(_t("Copia de siguranță a listei sateliților nu s-a putut face (%s). Nu s-a scris nimic.") % e)
	mod = None
	try:
		mod = stat.S_IMODE(os.stat(cale).st_mode)
	except OSError:
		pass
	try:
		_scrie_sigur(cale, date, mod)
	except Exception as e:
		raise Eroare(_t("Lista sateliților nu s-a putut scrie (%s). Fișierul vechi a rămas cum era.") % e)
	_fsync_dosar(dosar)
	sateliti.cale = cale
	sateliti._original = date
	_jurnal("%s scris (%d sateliti), copia: %s" % (cale, len(sateliti.lista), copie))
	return copie


# ---------------------------------------------------------------- reincarcarea

def _reincarca_in(nimmanager, db):
	"""Lista din fisier pusa in NimManager, numai cand pozitiile sunt aceleasi (vezi antetul). -> bool"""
	if not nimmanager.hasNimType("DVB-S"):
		return True                       # fara tuner de satelit lista nu se foloseste
	lista, nume, transpondere = [], {}, {}
	if not db.readSatellites(lista, nume, transpondere):
		return False
	lista.sort(key=nimmanager.sortFunc)
	if [x[0] for x in lista] != [x[0] for x in nimmanager.satList]:
		_jurnal("alte pozitii in satellites.xml: se folosesc dupa repornirea interfetei")
		return False
	nimmanager.satList[:] = lista
	nimmanager.satellites = nume
	nimmanager.transponders = transpondere
	_jurnal("satellites.xml recitit (%d sateliti)" % len(lista))
	return True


def reincarca():
	"""Pe receptor, de pe firul enigma2, dupa scrie() pe fisierul nucleului. -> True cand lista noua e deja folosita;
	False cand se vede numai dupa repornirea interfetei (satelit nou sau sters, alta pozitie) si pe PC."""
	try:
		from enigma import eDVBDB
		from Components.NimManager import nimmanager
	except Exception:
		return False
	try:
		return bool(_reincarca_in(nimmanager, eDVBDB.getInstance()))
	except Exception as e:
		_jurnal("reincarcarea nu a mers: %r" % (e,))
		return False


# ---------------------------------------------------------------- pentru pagina web

def _json_sat(s):
	return {"poz": s.poz, "position": s.position, "text": D.text_pozitie(s.poz), "nume": s.name, "flags": s.flags,
		"atribute": dict(s.atribute), "transpondere": len(s.transpondere)}


def json(sateliti):
	"""[{poz (0..3599), position (ca in fisier), text (19,2°E), nume, flags (text sau None), atribute (toate, text),
	transpondere (numarul lor)}], in ordinea din fisier."""
	return [_json_sat(s) for s in sateliti.lista]


def json_satelit(sateliti, poz):
	"""Satelitul de pe `poz` cu transponderele lui: {poz, position, text, nume, flags, atribute, transpondere:
	[{cheie, atribute: {nume: valoare text, in ordinea din fisier}}]}. Eroare cand nu exista."""
	s = sateliti.satelit(poz)
	rez = _json_sat(s)
	rez["transpondere"] = [{"cheie": k, "atribute": dict(t.atribute)} for k, t in s.chei()]
	return rez
