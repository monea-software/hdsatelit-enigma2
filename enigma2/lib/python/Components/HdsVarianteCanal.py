# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Variantele aceluiasi canal pe acelasi satelit (alt transponder, alt SID, SD si HD, criptat si necriptat).

In listele facute din lamedb (Toate canalele, un satelit, un furnizor, blocurile listei "Sateliți") un canal gasit de
mai multe ori pe acelasi satelit se arata O SINGURA DATA; celelalte variante raman rezerva (trecerea singura pe
urmatoarea: Components/HdsDvbIRezerva.py, Paznic) si se aleg de mana la MENU, "Alte variante (N)". lamedb si buchetele
omului nu se schimba: gruparea e numai in afisare, iar buchetele (si numerele lor) raman cum le-a facut omul.

Aceeasi grupa: acelasi nume (normalizat ca in cautare, HdsIndexCanale.normalizeaza, fara un HD / FHD / SD la coada:
"Antena 1" si "Antena 1 HD"), aceeasi pozitie de satelit, acelasi fel (TV sau radio). Acelasi canal de pe alt satelit,
de pe cablu sau terestru ramane separat; un serviciu fara nume (numele facut la scanare, "12271H SID 0x200") nu intra.

Varianta aratata (prima din ordine()): intai una care nu a cazut ultima oara, apoi alegerea omului de la "Alte
variante", apoi necriptata, apoi una care a dat imagine (notata aici de rezerva sau masurata in baza unica,
HdsBazaCanale grupa vd), apoi cu furnizorul scris, apoi HD; la egalitate frecventa si SID-ul (aceeasi ordine la fiecare
citire).

Ce se tine minte (FISIER, mic, JSON): alegerea omului pe grupa si, pe canal, ora ultimei imagini si a ultimei cazute
vazute de rezerva. Scris sigur (temporar + fsync + os.replace), numai cand se schimba ceva; un fisier care nu se poate
citi nu se scrie peste.

Grupele se fac din textul lamedb (citire usoara: numai randurile serviciilor si pozitiile transponderelor), o data pe
semnatura fisierului (data si marimea). Nimic din enigma2 la incarcare: probele de pe PC il incarca direct."""
from __future__ import absolute_import, unicode_literals

import json
import os
import re
import time

try:
	from Components import HdsIndexCanale as X
except ImportError:  # pe PC, in teste, Components e chiar dosarul modulului
	import HdsIndexCanale as X

DIRECTOR = "/etc/enigma2"
LAMEDB = "lamedb"
FISIER = "/etc/enigma2/hds_variante_canale.json"
MAX_NOTE = 600
MAX_ALESE = 400
# tipurile cu imagine HD dupa EN 300 468 (MPEG-2 HD, H.264 HD, H.265, H.265 UHD)
TIPURI_HD = frozenset((0x11, 0x19, 0x1F, 0x20))
# HD / FHD / SD la coada numelui (cuvant intreg, si in paranteze): "TLC HD", "Kanal Yek SD", "Pro TV (HD)"; 4K si UHD
# raman in nume (de cele mai multe ori alt program)
_SUFIX = re.compile(r"^(.*?[^\s_.\-(\[])[\s_.\-]*[(\[]?\s*(?:F?HD|SD)\s*[)\]]?\s*$", re.I)
_HD_IN_NUME = re.compile(r"(?<![0-9a-z])(f?hd|uhd|4k)(?![0-9a-z])", re.I)


def _t(text):
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def N_(text):
	return text


T_ALTE = N_("Alte variante (%d)")
T_TITLU = N_("Alte variante ale canalului")
T_ACUM = N_("acum")
T_CRIPTAT = N_("Criptat")


def _jurnal(text):
	print("[HdsVarianteCanal] %s" % text)


def nume_de_baza(nume):
	"""Numele fara HD / FHD / SD la coada ("Antena 1 HD" -> "Antena 1"); un nume care ar ramane prea scurt (sub doua
	litere sau cifre) ramane intreg."""
	n = (nume or "").strip()
	for _i in range(3):
		m = _SUFIX.match(n)
		if not m:
			break
		baza = m.group(1).strip()
		if len(X.normalizeaza(baza)) < 2:
			break
		n = baza
	return n


def cheie_grupa(nume, poz, tip):
	return "%s|%d|%s" % (X.normalizeaza(nume_de_baza(nume)), poz, tip)


class Varianta(object):
	__slots__ = ("ref", "cheie", "nume", "poz", "tip", "criptat", "furnizor", "hd", "tp", "tpk", "frecv", "sid",
		"stype", "grupa")

	def __init__(self, ref, cheie, nume, poz, tip, criptat, furnizor, hd, tp, tpk, frecv, sid, stype, grupa):
		self.ref = ref                  # referinta, scrisa ca nucleul ("1:0:19:283D:3FB:1:C00000:0:0:0:")
		self.cheie = cheie              # "sid:ns:tsid:onid" (HdsIndexCanale.cheie_din_ref)
		self.nume = nume
		self.poz = poz
		self.tip = tip                  # 'tv' sau 'radio'
		self.criptat = criptat
		self.furnizor = furnizor        # furnizorul din SDT ('' pentru cel facut la scanare din transponder)
		self.hd = hd
		self.tp = tp                    # "11538 H"
		self.tpk = tpk                  # "ns:tsid:onid": acelasi transponder
		self.frecv = frecv
		self.sid = sid
		self.stype = stype
		self.grupa = grupa

	def __repr__(self):
		return "Varianta(%r, %r)" % (self.nume, self.ref)


# ---------------------------------------------------------------- citirea usoara a lamedb

def _transpondere(randuri, i, n):
	"""-> ({(ns, tsid, onid) si textul cheii ("00c00000:03fb:0001"): (poz, tp, frecv)}, indicele de dupa "end")."""
	rez = {}
	while i < n and randuri[i].strip() != "end":
		cheie = randuri[i].strip().lower()
		date = randuri[i + 1].strip() if i + 1 < n else ""
		if date.startswith("s "):
			try:
				p = cheie.split(":")
				k = (int(p[0], 16), int(p[1], 16), int(p[2], 16))
				rez[cheie] = None
				c = date[2:].split(":")
				poz = int(c[4])
				if poz < 0:
					poz += 3600
				frecv = int(c[0])
				rez[cheie] = rez[k] = (poz, X.text_transponder(date), frecv)
			except (ValueError, IndexError):
				pass
		i += 1
		while i < n and randuri[i].strip() not in ("/", "end"):
			i += 1
		if i < n and randuri[i].strip() == "/":
			i += 1
	return rez, i + 1


def grupe_din_lamedb(text):
	"""Textul lamedb -> {cheia grupei: [Varianta]} numai pentru grupele cu cel putin doua variante. Un fisier care nu se
	intelege da {}."""
	randuri = (text or "").split("\n")
	n = len(randuri)
	if n < 3 or not randuri[0].startswith("eDVB services /") or randuri[1].strip() != "transponders":
		return {}
	tps, i = _transpondere(randuri, 2, n)
	if i >= n or randuri[i].strip() != "services":
		return {}
	i += 1
	pe_grupa = {}
	norm = X.normalizeaza
	tv, radio = X.TIPURI_TV, X.TIPURI_RADIO
	while i + 2 < n:
		k = randuri[i].strip()
		if k == "end":
			break
		nume = randuri[i + 1].rstrip("\r").strip()
		date = randuri[i + 2].rstrip("\r")
		i += 3
		p = k.split(":")
		if len(p) < 6 or not nume:
			continue
		try:
			stype = int(p[4])
		except ValueError:
			continue
		if stype in tv:
			tip = "tv"
		elif stype in radio:
			tip = "radio"
		else:
			continue
		# cheile din lamedb au aceeasi forma la transpondere si la servicii (lib/dvb/db.cpp: %08x:%04x:%04x)
		tp = tps.get(("%s:%s:%s" % (p[1], p[2], p[3])).lower())
		if tp is not None:
			poz = tp[0]
		else:
			try:
				poz = int(p[1], 16) >> 16
			except ValueError:
				continue
			if not 0 <= poz < 3600:
				continue
		if " SID 0x" in nume and X._NUME_SCANARE.match(nume):
			continue
		coada = nume[-3:].lower()
		baza = nume_de_baza(nume) if (coada[-2:] in ("hd", "sd") or coada[-1:] in (")", "]")) else nume
		g = "%s|%d|%s" % (norm(baza), poz, tip)
		pe_grupa.setdefault(g, []).append((p, stype, nume, date, tp))
	rez = {}
	for g, lista in pe_grupa.items():
		if len(lista) < 2:
			continue
		variante = []
		for p, stype, nume, date, tp in lista:
			try:
				sid, ns, tsid, onid = int(p[0], 16), int(p[1], 16), int(p[2], 16), int(p[3], 16)
			except ValueError:
				continue
			if tp is None:
				tp = tps.get((ns, tsid, onid))
			furnizor, criptat, steaguri = "", False, 0
			if len(date) > 1 and date[1] == ":":
				for camp in date.split(","):
					if len(camp) < 2 or camp[1] != ":":
						continue
					if camp[0] == "p":
						furnizor = camp[2:]
					elif camp[0] == "C":
						criptat = True
					elif camp[0] == "f":
						try:
							steaguri = int(camp[2:], 16)
						except ValueError:
							pass
			else:
				furnizor = date.strip()
			if steaguri & X.DX_DONTSHOW or furnizor in X.FURNIZORI_PURTATORI:
				continue
			if furnizor.startswith("DVB-") and X._FURNIZOR_SCANARE.match(furnizor):
				furnizor = ""
			hd = stype in TIPURI_HD or bool(_HD_IN_NUME.search(nume))
			ref = "1:0:%X:%X:%X:%X:%X:0:0:0:" % (stype, sid, tsid, onid, ns)
			cheie = "%x:%x:%x:%x" % (sid, ns, tsid, onid)
			variante.append(Varianta(ref, cheie, nume, int(g.rsplit("|", 2)[1]), g.rsplit("|", 1)[1], criptat,
				furnizor, hd, tp[1] if tp else "", "%x:%x:%x" % (ns, tsid, onid), tp[2] if tp else 0, sid, stype, g))
		if len(variante) >= 2:
			rez[g] = variante
	return rez


# ---------------------------------------------------------------- starea tinuta minte (alegerile si notele)

class Stare(object):
	def __init__(self, cale=FISIER, ceas=None):
		self.cale = cale
		self.ceas = ceas or time.time
		self.ales = {}      # grupa -> cheia variantei alese de om
		self.note = {}      # cheia canalului -> [ora ultimei imagini, ora ultimei cazute]
		self.versiune = 0
		self._citit = False
		self._numai_citire = False

	def _asigura(self):
		if self._citit:
			return
		self._citit = True
		if not self.cale:
			# numai in memorie (probele)
			self.versiune += 1
			return
		try:
			with open(self.cale, "rb") as f:
				d = json.loads(f.read().decode("utf-8"))
			if isinstance(d, dict):
				a = d.get("ales")
				if isinstance(a, dict):
					self.ales = dict((str(k), str(v)) for k, v in a.items() if isinstance(v, str))
				no = d.get("note")
				if isinstance(no, dict):
					for k, v in no.items():
						if isinstance(v, list) and len(v) == 2:
							try:
								self.note[str(k)] = [float(v[0]), float(v[1])]
							except (TypeError, ValueError):
								pass
		except (IOError, OSError) as e:
			if getattr(e, "errno", None) not in (2, 20):
				# un fisier care nu s-a putut citi nu se scrie peste (ce se afla ramane in memorie)
				self._numai_citire = True
				_jurnal("nu pot citi %s: %s" % (self.cale, e))
		except ValueError as e:
			_jurnal("%s stricat (%s): il scriu din nou" % (self.cale, e))
		self.versiune += 1

	def alegere(self, grupa):
		self._asigura()
		return self.ales.get(grupa)

	def nota(self, cheie):
		self._asigura()
		return self.note.get(cheie)

	def alege(self, grupa, cheie):
		self._asigura()
		self.ales[grupa] = cheie
		# alegerea omului incepe curata: o cazuta veche a variantei nu o mai trimite la urma
		n = self.note.get(cheie)
		if n is not None and n[1] > n[0]:
			n[1] = 0.0
		while len(self.ales) > MAX_ALESE:
			self.ales.pop(next(iter(self.ales)))
		self._scrie()

	def noteaza(self, cheie, merge):
		self._asigura()
		n = self.note.setdefault(cheie, [0.0, 0.0])
		vechi = list(n)
		n[0 if merge else 1] = float(int(self.ceas()))
		if merge and vechi[0] > vechi[1] and vechi[0] > 0:
			# era deja bun: nicio scriere pentru fiecare vizionare
			n[0] = vechi[0]
			return False
		while len(self.note) > MAX_NOTE:
			vechea = min(self.note.items(), key=lambda kv: max(kv[1]))[0]
			del self.note[vechea]
		self._scrie()
		return True

	def _scrie(self):
		self.versiune += 1
		if self._numai_citire or not self.cale:
			return
		d = {"v": 1, "ales": self.ales, "note": self.note}
		nou = self.cale + ".nou"
		try:
			with open(nou, "wb") as f:
				f.write(json.dumps(d, ensure_ascii=True, sort_keys=True).encode("ascii"))
				f.flush()
				os.fsync(f.fileno())
			os.replace(nou, self.cale)
		except (IOError, OSError) as e:
			_jurnal("nu pot scrie %s: %s" % (self.cale, e))


# ---------------------------------------------------------------- grupele, ordinea si listele

class Variante(object):
	"""Grupele unui lamedb, cu ordinea variantelor (stare: alegerile si notele; stiute(): cheile cu imagine masurata)."""

	def __init__(self, grupe, stare=None, stiute=None):
		self.grupe = grupe
		self.stare = stare if stare is not None else Stare(cale=None)
		self.stiute = stiute or (lambda: frozenset())
		self.pe_ref = {}
		self.pe_cheie = {}
		for g, lista in grupe.items():
			for v in lista:
				self.pe_ref[v.ref] = g
				self.pe_cheie[v.cheie] = g
		self._ordini = {}
		self._versiune = None

	def _cheie_ordine(self, v, ales, stiute):
		n = self.stare.nota(v.cheie)
		cazut = bool(n and n[1] > n[0])
		merge = bool(n and n[0] > n[1]) or (v.cheie in stiute and not cazut)
		return (cazut, v.cheie != ales, v.criptat, not merge, not v.furnizor, not v.hd, v.frecv, v.sid)

	def ordine(self, g):
		"""Variantele grupei, prima cea aratata."""
		lista = self.grupe.get(g)
		if not lista:
			return []
		stiute = self.stiute()
		versiune = (self.stare.versiune, id(stiute))
		if versiune != self._versiune:
			self._ordini = {}
			self._versiune = versiune
		o = self._ordini.get(g)
		if o is None:
			ales = self.stare.alegere(g)
			o = sorted(lista, key=lambda v: self._cheie_ordine(v, ales, stiute))
			self._ordini[g] = o
		return o

	def grupa(self, ref):
		"""Cheia grupei unei referinte (text), sau None."""
		if not ref:
			return None
		g = self.pe_ref.get(ref)
		if g is not None:
			return g
		k = X.cheie_din_ref(ref)
		return self.pe_cheie.get(k) if k else None

	def toate(self, ref):
		"""Toate variantele canalului (si el), in ordine; [] pentru un canal fara variante."""
		g = self.grupa(ref)
		return list(self.ordine(g)) if g is not None else []

	def alternative(self, ref):
		"""Celelalte variante ale canalului, in ordine."""
		k = X.cheie_din_ref(ref) if ref else None
		return [v for v in self.toate(ref) if v.cheie != k]

	def ascunse(self, texte):
		"""texte: referintele unei liste (in orice ordine) -> {referinta ascunsa: referinta aratata in locul ei}: dintre
		variantele aceleiasi grupe aflate in lista ramane prima in ordine, celelalte se ascund."""
		pe_ref = self.pe_ref
		pe_grupa = {}
		for s in texte:
			g = pe_ref.get(s)
			if g is not None:
				pe_grupa.setdefault(g, []).append(s)
		rez = {}
		for g, l in pe_grupa.items():
			if len(l) < 2:
				continue
			prezente = set(l)
			cap = None
			for v in self.ordine(g):
				if v.ref in prezente:
					cap = v.ref
					break
			for s in l:
				if s != cap:
					rez[s] = cap
		return rez

	def ascunse_pe_pozitii(self, tip):
		"""{pozitie: cate variante se ascund} in lista unui satelit, pentru felul dat ('tv' / 'radio')."""
		rez = {}
		for g, lista in self.grupe.items():
			if lista[0].tip == tip:
				rez[lista[0].poz] = rez.get(lista[0].poz, 0) + len(lista) - 1
		return rez

	def aratata(self, ref):
		"""Varianta aratata in locul referintei (in liste cu toate variantele grupei), sau None."""
		o = self.toate(ref)
		return o[0] if o else None


def locuri_din_canale(canale, stare_=None, stiute=None):
	"""Canalele editorului de canale (Components/HdsEditorCanale.CanalInfo: cheie, ref, nume, poz, tip, acces, furnizor,
	frecv, sid, stype, tp_cheie, tp_text) -> {cheie: (numarul grupei, locul in grupa)}, numai pentru grupele cu cel putin
	doua variante; aceeasi grupa si aceeasi ordine ca listele (grupe_din_lamedb, Variante.ordine)."""
	pe_grupa = {}
	for c in canale:
		poz = getattr(c, "poz", None)
		if not isinstance(poz, int) or isinstance(poz, bool) or not 0 <= poz < 3600:
			continue
		tip = getattr(c, "tip", "")
		nume = (getattr(c, "nume", "") or "").strip()
		if tip not in ("tv", "radio") or not nume or (" SID 0x" in nume and X._NUME_SCANARE.match(nume)):
			continue
		pe_grupa.setdefault(cheie_grupa(nume, poz, tip), []).append(c)
	grupe = {}
	for g, lista in pe_grupa.items():
		if len(lista) < 2:
			continue
		variante = []
		for c in lista:
			furnizor = getattr(c, "furnizor", "") or ""
			if furnizor.startswith("DVB-") and X._FURNIZOR_SCANARE.match(furnizor):
				furnizor = ""
			tpc = getattr(c, "tp_cheie", None)
			tpk = "%x:%x:%x" % tuple(tpc) if tpc else ""
			stype = getattr(c, "stype", 0) or 0
			hd = stype in TIPURI_HD or bool(_HD_IN_NUME.search(c.nume or ""))
			variante.append(Varianta(c.ref, c.cheie, (c.nume or "").strip(), c.poz, c.tip, c.acces == "criptat",
				furnizor, hd, getattr(c, "tp_text", "") or "", tpk, getattr(c, "frecv", 0) or 0, getattr(c, "sid", 0) or 0,
				stype, g))
		grupe[g] = variante
	v = Variante(grupe, stare_ if stare_ is not None else stare(), stiute or _stiute)
	rez = {}
	for n, g in enumerate(sorted(grupe), 1):
		for loc, x in enumerate(v.ordine(g)):
			rez[x.cheie] = (n, loc)
	return rez


def text_varianta(v, acum=False):
	"""Randul unei variante in alegerea de la MENU si in web: numele, transponderul, furnizorul (altfel SID-ul), FTA sau
	Criptat."""
	parti = [v.nume]
	if v.tp:
		parti.append(v.tp)
	parti.append(v.furnizor or "SID %d" % v.sid)
	parti.append(_t(T_CRIPTAT) if v.criptat else "FTA")
	if acum:
		parti.append(_t(T_ACUM))
	return u" · ".join(parti)


# ---------------------------------------------------------------- instanta procesului (receptorul)

_MEMORIE = {"sem": None, "variante": None}
_STARE = []
_STIUTE = {"cheie": None, "set": frozenset()}


def stare():
	if not _STARE:
		_STARE.append(Stare(cale=FISIER))
	return _STARE[0]


def _semnatura(cale):
	try:
		st = os.stat(cale)
		return (int(st.st_mtime), st.st_size)
	except (IOError, OSError):
		return None


def _stiute():
	"""Cheile canalelor cu imagine masurata in baza unica (grupa vd), numai daca baza procesului exista deja; tinute
	pana la urmatoarea schimbare a grupei vd."""
	try:
		import sys
		B = sys.modules.get("Components.HdsBazaCanale") or sys.modules.get("HdsBazaCanale")
		b = B.baza_existenta() if B is not None else None
		if b is None:
			return _STIUTE["set"]
		cheie = (id(b), b.versiune_grupe(("vd",)))
		if cheie != _STIUTE["cheie"]:
			_STIUTE["set"] = frozenset(b.chei_cu(("vd",)))
			_STIUTE["cheie"] = cheie
	except Exception as e:
		_jurnal("baza unica: %r" % (e,))
	return _STIUTE["set"]


def variante(director=None):
	"""Grupele lamedb-ului de acum (citite din nou numai cand se schimba fisierul)."""
	cale = os.path.join(director or DIRECTOR, LAMEDB)
	sem = _semnatura(cale)
	if sem is not None:
		sem = (cale,) + sem
	if sem is not None and sem == _MEMORIE["sem"] and _MEMORIE["variante"] is not None:
		return _MEMORIE["variante"]
	inceput = time.time()
	grupe = {}
	if sem is not None:
		try:
			with open(cale, "rb") as f:
				grupe = grupe_din_lamedb(f.read().decode("utf-8", "replace"))
		except (IOError, OSError) as e:
			_jurnal("lamedb: %s" % e)
	v = Variante(grupe, stare(), _stiute)
	_MEMORIE["sem"], _MEMORIE["variante"] = sem, v
	durata = (time.time() - inceput) * 1000
	_jurnal("%d grupe, %d variante in %.0f ms" % (len(grupe), sum(len(l) for l in grupe.values()), durata))
	return v


def uita():
	_MEMORIE["sem"], _MEMORIE["variante"] = None, None


def alternative(ref):
	try:
		return variante().alternative(ref)
	except Exception as e:
		_jurnal("alternative: %r" % (e,))
		return []


def toate(ref):
	try:
		return variante().toate(ref)
	except Exception as e:
		_jurnal("variantele: %r" % (e,))
		return []


def ascunse(texte):
	try:
		return variante().ascunse(texte)
	except Exception as e:
		_jurnal("ascunse: %r" % (e,))
		return {}


def ascunse_pe_pozitii(tip):
	try:
		return variante().ascunse_pe_pozitii(tip)
	except Exception as e:
		_jurnal("numerele: %r" % (e,))
		return {}


def alege(ref):
	"""Varianta aleasa de om la "Alte variante": ea se arata de acum in liste."""
	try:
		v = variante()
		g = v.grupa(ref)
		k = X.cheie_din_ref(ref)
		if g is not None and k:
			stare().alege(g, k)
			return True
	except Exception as e:
		_jurnal("alegerea: %r" % (e,))
	return False


def noteaza(ref, merge):
	"""Rezerva a vazut canalul cu imagine (merge=True) sau cazut; numai pentru canalele cu variante."""
	try:
		v = variante()
		k = X.cheie_din_ref(ref)
		if k and v.grupa(ref) is not None:
			return stare().noteaza(k, merge)
	except Exception as e:
		_jurnal("nota: %r" % (e,))
	return False
