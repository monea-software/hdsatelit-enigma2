# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsEditorCanaleDate.py: datele editorului de canale (ecranele de pe televizor si pagina web /editor-canale): lista de
# servicii (lamedb), buchetele, controlul parental (blacklist, whitelist) si numele pozitiilor din satellites.xml.
#
# Citirea si scrierea urmeaza lib/dvb/db.cpp al imaginii:
# - lamedb: se citeste orice versiune dupa antet (3, 4 si 5, aceasta din urma numai la import: parserul imaginii e cel
#   de 4), se scrie numai formatul 4. Un transponder are blocul lui (cheie, randurile de parametri, „/”), un serviciu trei
#   randuri (cheia sid:ns:tsid:onid:tip:numar, numele, datele p:,c:,C:,f:). Ce nu s-a schimbat se scrie octet cu octet
#   din randurile citite; ce s-a schimbat se scrie in forma lui saveServicelist (hex mic, %04x / %08x);
# - fgets cu tampon de 256: un rand de 255 de octeti sau mai mult se rupe si strica tot restul fisierului, deci numele,
#   furnizorul si randurile buchetelor scrise de aici se scurteaza (pe granita unui caracter UTF-8) sub LUNGIME_MAXIMA;
# - buchetele: „#NAME”, apoi „#SERVICE <referinta>” cu „#DESCRIPTION <text>” numai imediat dupa el; citirea se opreste la
#   primul rand gol, deci nu se scrie niciun rand gol; enigma2 scrie CRLF (eBouquet::flushChanges), la fel aici. Un
#   buchet se incarca recursiv din oricare referinta cu FROM BOUQUET (sub-buchete, alternative). Fisierele
#   userbouquet.* care nu sunt legate in nicio lista nu se incarca singure in aceasta imagine („nelegate”);
# - referinta: tip:steaguri:8 campuri hex:cale[:nume], cu „:” din cale si din nume scrise %3a.
#
# Obiectele sunt nemodificabile dupa facere (Serviciu, Transponder, Intrare): o schimbare face un obiect nou, iar
# anularea (Components/HdsEditorCanale.py) tine obiectul vechi. Buchetul e o lista de intrari, fiecare cu un id stabil.
#
# Nimic din enigma2 la incarcare: modulul se probeaza pe PC.

import os
import re
import unicodedata

ANTET4 = "eDVB services /4/"
SFARSIT = "Have a lot of bugs!"
LUNGIME_MAXIMA = 250          # octeti pe rand, sub tamponul de 256 al lui fgets (cu sfarsitul de rand)
DIRECTOR = "/etc/enigma2"
SATELITI = "/etc/tuxbox/satellites.xml"

# steagurile referintei (eServiceReference)
DOSAR = 1                     # isDirectory
COBORARE = 7                  # isDirectory | mustDescent | canDescent
MARCAJ = 64                   # isMarker
GRUP = 128                    # isGroup (alternative)
NUMEROTAT = 256               # marcaj numerotat
INVIZIBIL = 512               # marcaj ascuns (rand gol)

# steagurile serviciului (f: in lamedb, idvb.h)
DX_NOSDT = 1
DX_ASCUNS = 2                 # dxDontshow
DX_NODVB = 4
DX_PASTREAZA_NUMELE = 8       # dxHoldName: scanarea nu mai schimba numele
DX_NOU = 64                   # dxNewFound

TIPURI_RADIO = (2, 10)
TIPURI_TV = (1, 4, 5, 6, 11, 16, 17, 22, 25, 27, 31, 134, 195)
TIPURI_UHD = (31,)
TIPURI_HD = (17, 22, 25, 27, 134)
# c: din lamedb (idvb.h, cacheID): 0 video, 1 MPEG, 4 AC3, 12..17 celelalte formate de sunet
CACHE_VIDEO = (0,)
CACHE_SUNET = (1, 4, 12, 13, 14, 15, 16, 17)

POZ_CABLU = "cablu"
POZ_TERESTRU = "terestru"

FELURI = ("canal", "marcaj", "spatiu", "subbuchet", "alternative", "flux", "altul")

_FROM = re.compile(r'FROM BOUQUET "([^"]{1,200})"')
_NUME_FISIER = re.compile(r"^[A-Za-z0-9_.\-]{1,120}$")
_POLARIZARE = {0: "H", 1: "V", 2: "L", 3: "R"}


class Stricat(ValueError):
	"""Un fisier care nu are structura citita de enigma2."""


# ---------------------------------------------------------------- texte

def taie_octeti(text, maxim):
	"""Textul scurtat (pe granita unui caracter) ca UTF-8 sa aiba cel mult `maxim` octeti."""
	b = text.encode("utf-8", "surrogateescape")
	if len(b) <= maxim:
		return text
	b = b[:maxim]
	while b and (b[-1] & 0xC0) == 0x80:
		b = b[:-1]
	if b and b[-1] >= 0xC0:
		b = b[:-1]
	return b.decode("utf-8", "surrogateescape")


def curat_nume(text, maxim=LUNGIME_MAXIMA - 10):
	"""Un nume scris de om: fara sfarsituri de rand si caractere de control, fara spatii la capete, scurtat."""
	text = "".join(" " if (c in "\r\n\t" or unicodedata.category(c) == "Cc") else c for c in (text or ""))
	return taie_octeti(text.strip(), maxim)


def fara_diacritice(text):
	if text.isascii():
		return text
	return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


_SEMNE = re.compile(r"[\W_]+", re.UNICODE)
_NUME_SCANARE = re.compile(r"^\d+[HV]? SID 0X[0-9A-F]+$")


def cheie_sortare(nume):
	"""Ordinea dupa nume, aceeasi cu a indexului cautarii (HdsIndexCanale.Index): fara diacritice, fara majuscule si
	fara semne („Pro TV” langa „ProSieben”); numele fara nicio litera sau cifra („.”, „-”, „/////”, gol) spre sfarsit,
	iar numele facute la scanare cand lipseste SDT („12271H SID 0x200”) la coada."""
	t = fara_diacritice(nume or "").upper().strip()
	litere = _SEMNE.sub("", t)
	return (1 if _NUME_SCANARE.match(t) else 0, 0 if litere else 1, litere, t)


def decodeaza(text):
	"""%xx din cale si din numele unei referinte (eServiceReference::decode)."""
	if "%" not in text:
		return text
	return re.sub(r"%([0-9A-Fa-f]{2})", lambda m: chr(int(m.group(1), 16)), text)


def codeaza(text):
	"""Inversul lui decodeaza pentru caracterele care strica referinta (eServiceReference::encode)."""
	rez = []
	for c in text:
		if c == ":" or c == "%" or ord(c) < 32:
			rez.append("%%%02x" % ord(c))
		else:
			rez.append(c)
	return "".join(rez)


# ---------------------------------------------------------------- referinte

class Referinta(object):
	"""Campurile unei referinte de buchet (textul ramane cel din fisier)."""
	__slots__ = ("text", "tip", "steaguri", "date", "cale", "nume")

	def __init__(self, text):
		self.text = text
		parti = text.split(":", 11)
		self.tip, self.steaguri, self.date, self.cale, self.nume = -1, 0, [0] * 8, "", ""
		if len(parti) < 10:
			return
		try:
			self.tip = int(parti[0])
			self.steaguri = int(parti[1])
			self.date = [int(p or "0", 16) for p in parti[2:10]]
		except ValueError:
			self.tip = -1
			return
		if len(parti) > 10:
			self.cale = parti[10]
		if len(parti) > 11:
			self.nume = decodeaza(parti[11])

	@property
	def valida(self):
		return self.tip >= 0

	def fisier(self):
		m = _FROM.search(self.cale)
		return m.group(1) if m else None

	def fel(self):
		if not self.valida:
			return "altul"
		st = self.steaguri
		if st & MARCAJ:
			return "spatiu" if st & INVIZIBIL else "marcaj"
		if (st & (DOSAR | 4)) and self.fisier():
			# canDescent (4): alternativele au 134 (grup, fara bitul de dosar), buchetele 7
			return "alternative" if st & GRUP else "subbuchet"
		if self.cale:
			c = decodeaza(self.cale)
			if "://" in c:
				return "flux"
			return "altul"
		if self.tip == 1 and any(self.date[1:5]):
			return "canal"
		return "altul"

	def cheie(self):
		"""sid:ns:tsid:onid (hex mic), aceeasi cu HdsIndexCanale.cheie_din_ref; None pentru ce nu e canal DVB."""
		if self.tip != 1 or self.cale or (self.steaguri & (COBORARE | MARCAJ | GRUP)):
			return None
		d = self.date
		return "%x:%x:%x:%x" % (d[1], d[4], d[2], d[3])


def ref_serviciu(sid, ns, tsid, onid, tip):
	"""Referinta de buchet a unui serviciu DVB, ca toString (hex mare)."""
	return "1:0:%X:%X:%X:%X:%X:0:0:0:" % (tip, sid, tsid, onid, ns)


def ref_buchet(fisier, alternative=False):
	radio = fisier.endswith(".radio")
	return '1:%d:%d:0:0:0:0:0:0:0:FROM BOUQUET "%s" ORDER BY bouquet' % (134 if alternative else 7, 2 if radio else 1,
		fisier)


def ref_marcaj(nume, numar, numerotat=False):
	"""Ca ChannelSelection.addMarker: numarul marcajului (unic in buchet) in primul camp de date."""
	return "1:%d:%X:0:0:0:0:0:0:0::%s" % (MARCAJ | (NUMEROTAT if numerotat else 0), numar, codeaza(nume))


def ref_spatiu(numar):
	return "1:%d:%X:0:0:0:0:0:0:0:" % (MARCAJ | NUMEROTAT | INVIZIBIL, numar)


def cheie_din_ref(text):
	return Referinta(text).cheie()


# ---------------------------------------------------------------- lamedb

class Transponder(object):
	__slots__ = ("ns", "tsid", "onid", "randuri", "brut")

	def __init__(self, ns, tsid, onid, randuri, brut=None):
		self.ns, self.tsid, self.onid = ns, tsid, onid
		self.randuri = tuple(randuri)       # randurile de parametri, fara cheie si fara „/” (de obicei unul: "\ts ...")
		self.brut = brut                     # randul cheii asa cum a fost citit (None: scris din campuri)

	@property
	def cheie(self):
		return (self.ns, self.tsid, self.onid)

	def cheie_text(self):
		return "%08x:%04x:%04x" % (self.ns, self.tsid, self.onid)

	def _parametri(self):
		for r in self.randuri:
			r = r.strip()
			if len(r) > 2 and r[1] == " ":
				return r[0], r[2:].split(":")
		return "", []

	@property
	def fel(self):
		return self._parametri()[0]

	def _int(self, i):
		try:
			return int(self._parametri()[1][i])
		except (IndexError, ValueError):
			return None

	@property
	def poz(self):
		fel = self.fel
		if fel == "s":
			p = self._int(4)
			if p is None:
				return None
			return p + 3600 if p < 0 else p
		if fel == "c":
			return POZ_CABLU
		if fel == "t":
			return POZ_TERESTRU
		return None

	@property
	def frecv(self):
		"""Frecventa in MHz (satelit: kHz in lamedb; cablu: kHz; terestru: Hz)."""
		f = self._int(0)
		if f is None:
			return None
		if self.fel == "t":
			return (f + 500000) // 1000000
		return (f + 500) // 1000

	@property
	def pol(self):
		if self.fel != "s":
			return ""
		return _POLARIZARE.get(self._int(2), "")

	@property
	def sr(self):
		if self.fel not in ("s", "c"):
			return None
		v = self._int(1)
		return None if v is None else v // 1000

	def text(self):
		"""„11538 H 22000” / „346 MHz” (rata de simbol rotunjita la 500 cand e la cel mult 5 kS/s de ea: 27497 ->
		27500, cum o scrie toata lumea)."""
		f = self.frecv
		if f is None:
			return ""
		if self.fel == "s":
			sr = self.sr
			if sr:
				r = int(round(sr / 500.0)) * 500
				if abs(r - sr) <= 5:
					sr = r
			return ("%d %s %s" % (f, self.pol, sr or "")).strip()
		return "%d MHz" % f

	# campurile randului „s” din lamedb, in ordine (frecventa kHz, rata de simbol simboluri/s, ...)
	CAMPURI_S = ("frecventa", "sr", "pol", "fec", "pozitie", "inversiune", "steaguri", "sistem", "modulatie", "rolloff",
		"pilot", "is_id", "pls_cod", "pls_mod", "t2mi_plp", "t2mi_pid")

	def campuri(self):
		"""{nume: int} al randului de parametri (numai satelit; altfel {})."""
		fel, valori = self._parametri()
		if fel != "s":
			return {}
		rez = {}
		for nume, v in zip(self.CAMPURI_S, valori):
			try:
				rez[nume] = int(v)
			except ValueError:
				pass
		return rez

	def cu_campuri(self, valori):
		"""Un transponder nou (aceeasi cheie) cu parametrii de satelit schimbati; randurile in plus raman."""
		vechi = self._parametri()[1] if self.fel == "s" else []
		v = list(vechi) + [""] * (len(self.CAMPURI_S) - len(vechi))
		for i, nume in enumerate(self.CAMPURI_S):
			if nume in valori and valori[nume] is not None:
				v[i] = str(int(valori[nume]))
		while v and v[-1] == "":
			v.pop()
		v = [x or "0" for x in v]
		alte = [r for r in self.randuri if not (len(r.strip()) > 2 and r.strip()[1] == " ")]
		return Transponder(self.ns, self.tsid, self.onid, ["\ts " + ":".join(v)] + alte)


class Serviciu(object):
	"""Un serviciu din lamedb. `cheie_rand` = randul cheii asa cum a fost citit (None cand s-a schimbat)."""
	__slots__ = ("sid", "ns", "tsid", "onid", "tip", "rest", "nume", "date", "brut", "_d")

	def __init__(self, sid, ns, tsid, onid, tip, nume, date, rest="0", brut=None):
		self.sid, self.ns, self.tsid, self.onid, self.tip = sid, ns, tsid, onid, tip
		self.rest = rest                    # campurile cheii de dupa tip (numarul si ce mai urmeaza), ca text
		self.nume = nume
		self.date = date                    # randul 3, intreg
		self.brut = brut                    # (cheie, nume, date) citite; None: se scrie din campuri
		self._d = None

	@property
	def k5(self):
		return (self.sid, self.ns, self.tsid, self.onid, self.tip)

	@property
	def cheie(self):
		return "%x:%x:%x:%x" % (self.sid, self.ns, self.tsid, self.onid)

	@property
	def ref(self):
		return ref_serviciu(self.sid, self.ns, self.tsid, self.onid, self.tip)

	@property
	def tp_cheie(self):
		return (self.ns, self.tsid, self.onid)

	def _desparte(self):
		"""(furnizor, steaguri, caid-uri, {cache: valoare}, alte campuri)."""
		if self._d is not None:
			return self._d
		furnizor, steaguri, caids, cache, alte = "", 0, [], {}, []
		date = self.date
		if len(date) > 1 and date[1] == ":":
			for camp in date.split(","):
				if len(camp) < 2 or camp[1] != ":":
					alte.append(camp)
					continue
				lit, val = camp[0], camp[2:]
				try:
					if lit == "p":
						furnizor = val
					elif lit == "f":
						steaguri = int(val, 16)
					elif lit == "C":
						caids.append(int(val, 16))
					elif lit == "c":
						cache[int(val[:2])] = int(val[2:], 16)
					else:
						alte.append(camp)
				except ValueError:
					alte.append(camp)
		else:
			furnizor = date
		self._d = (furnizor, steaguri, caids, cache, alte)
		return self._d

	@property
	def furnizor(self):
		return self._desparte()[0]

	@property
	def steaguri(self):
		return self._desparte()[1]

	@property
	def caids(self):
		return self._desparte()[2]

	@property
	def cache(self):
		return self._desparte()[3]

	@property
	def ascuns(self):
		return bool(self.steaguri & DX_ASCUNS)

	@property
	def radio(self):
		return self.tip in TIPURI_RADIO

	@property
	def fel_tip(self):
		if self.tip in TIPURI_RADIO:
			return "radio"
		if self.tip in TIPURI_TV:
			return "tv"
		return "date"

	@property
	def hd(self):
		if self.tip in TIPURI_RADIO:
			return ""
		if self.tip in TIPURI_UHD or "UHD" in self.nume or "4K" in self.nume:
			return "UHD"
		if self.tip in TIPURI_HD or " HD" in (" " + self.nume):
			return "HD"
		if self.tip in TIPURI_TV:
			return "SD"
		return ""

	@property
	def are_video(self):
		if self.tip in TIPURI_RADIO:
			return False
		c = self.cache
		if not c:
			return None
		return any(k in c for k in CACHE_VIDEO)

	@property
	def are_sunet(self):
		c = self.cache
		if not c:
			return None
		return any(k in c for k in CACHE_SUNET)

	def cu(self, nume=None, steaguri=None, furnizor=None):
		"""Un serviciu nou, cu numele, steagurile sau furnizorul schimbate (restul datelor raman)."""
		f, st, caids, cache, alte = self._desparte()
		if nume is not None:
			nume = curat_nume(nume)
		if furnizor is not None:
			f = curat_nume(furnizor)
		if steaguri is not None:
			st = steaguri
		if furnizor is None and steaguri is None:
			date = self.date
		else:
			date = scrie_date(f, cache, caids, st, alte)
		return Serviciu(self.sid, self.ns, self.tsid, self.onid, self.tip, self.nume if nume is None else nume, date,
			self.rest)

	def randuri(self):
		if self.brut is not None:
			return self.brut
		cheie = "%04x:%08x:%04x:%04x:%d:%s" % (self.sid, self.ns, self.tsid, self.onid, self.tip, self.rest or "0")
		return (cheie, taie_octeti(self.nume, LUNGIME_MAXIMA), _date_scurtate(self.date))


def scrie_date(furnizor, cache, caids, steaguri, alte=()):
	"""Randul 3 in forma lui saveServicelist: p:, c:%02d%04x, C:%04x, f:%x."""
	parti = ["p:" + furnizor]
	for k in sorted(cache):
		parti.append("c:%02d%04x" % (k, cache[k]))
	for c in caids:
		parti.append("C:%04x" % c)
	if steaguri:
		parti.append("f:%x" % steaguri)
	parti.extend(alte)
	return ",".join(parti)


def _date_scurtate(date):
	"""Randul de date sub LUNGIME_MAXIMA: intai se scurteaza furnizorul, apoi pleaca CAID-urile de la coada."""
	if len(date.encode("utf-8", "surrogateescape")) <= LUNGIME_MAXIMA:
		return date
	parti = date.split(",")
	if parti and parti[0].startswith("p:"):
		parti[0] = "p:" + taie_octeti(parti[0][2:], 40)
	while len(",".join(parti).encode("utf-8", "surrogateescape")) > LUNGIME_MAXIMA:
		for i in range(len(parti) - 1, -1, -1):
			if parti[i].startswith("C:"):
				del parti[i]
				break
		else:
			break
	return taie_octeti(",".join(parti), LUNGIME_MAXIMA)


class Lamedb(object):
	"""Transponderele si serviciile, in ordinea din fisier (cele noi la coada)."""

	def __init__(self):
		self.versiune = 4
		self.transpondere = {}      # (ns, tsid, onid) -> Transponder
		self.servicii = {}          # (sid, ns, tsid, onid, tip) -> Serviciu
		self.versiune_date = 0      # creste la fiecare schimbare (memoriile editorului)
		self._pe_cheie = None

	def copie(self):
		n = Lamedb()
		n.versiune = self.versiune
		n.transpondere = dict(self.transpondere)
		n.servicii = dict(self.servicii)
		return n

	def pe_cheie(self):
		"""{cheie sid:ns:tsid:onid: [k5]} (de obicei un singur serviciu pe cheie)."""
		if self._pe_cheie is None:
			d = {}
			for k5, s in self.servicii.items():
				d.setdefault(s.cheie, []).append(k5)
			self._pe_cheie = d
		return self._pe_cheie

	def schimbat(self):
		self._pe_cheie = None
		self.versiune_date += 1

	def pune(self, s):
		nou = s.k5 not in self.servicii
		self.servicii[s.k5] = s
		self.versiune_date += 1
		if nou:
			self._pe_cheie = None

	def scoate(self, k5):
		if self.servicii.pop(k5, None) is not None:
			self._pe_cheie = None
			self.versiune_date += 1

	def dupa_cheie(self, cheie):
		return [self.servicii[k] for k in self.pe_cheie().get(cheie, ()) if k in self.servicii]

	def text(self):
		"""Fisierul in formatul 4."""
		r = [ANTET4, "transponders"]
		for t in self.transpondere.values():
			r.append(t.brut if t.brut is not None else t.cheie_text())
			r.extend(t.randuri)
			r.append("/")
		r.append("end")
		r.append("services")
		for s in self.servicii.values():
			r.extend(s.randuri())
		r.append("end")
		r.append(SFARSIT)
		return "\n".join(r) + "\n"


def _int16(text):
	return int(text, 16)


def citeste_lamedb(text):
	"""Textul unui lamedb (3, 4 sau 5) -> Lamedb. Ridica Stricat cand nu se intelege."""
	if isinstance(text, bytes):
		text = text.decode("utf-8", "surrogateescape")
	text = text.replace("\r", "")
	randuri = text.split("\n")
	m = re.match(r"^eDVB services /(\d+)/", randuri[0] if randuri else "")
	if not m:
		raise Stricat("antet")
	versiune = int(m.group(1))
	if versiune == 5:
		return _citeste5(randuri)
	db = Lamedb()
	db.versiune = versiune
	n = len(randuri)
	if n < 2 or randuri[1] != "transponders":
		raise Stricat("transponders")
	i = 2
	while i < n and randuri[i] != "end":
		cheie = randuri[i]
		parti = cheie.split(":")
		try:
			ns, tsid, onid = _int16(parti[0]), _int16(parti[1]), _int16(parti[2])
		except (ValueError, IndexError):
			raise Stricat("transponder %r" % cheie)
		i += 1
		par = []
		while i < n and randuri[i] != "/":
			if randuri[i] == "end":
				raise Stricat("transponder fara /")
			par.append(randuri[i])
			i += 1
		if i >= n:
			raise Stricat("transponder neterminat")
		i += 1
		if versiune == 3:
			par = [_s3_in_4(p) for p in par]
			brut = None
		else:
			brut = cheie
		db.transpondere[(ns, tsid, onid)] = Transponder(ns, tsid, onid, par, brut)
	if i + 1 >= n or randuri[i + 1] != "services":
		raise Stricat("services")
	i += 2
	while i < n and randuri[i] != "end":
		if i + 2 >= n:
			raise Stricat("serviciu neterminat")
		cheie, nume, date = randuri[i], randuri[i + 1], randuri[i + 2]
		i += 3
		parti = cheie.split(":")
		try:
			sid, ns, tsid, onid = _int16(parti[0]), _int16(parti[1]), _int16(parti[2]), _int16(parti[3])
			tip = int(parti[4])
			rest = ":".join(parti[5:]) or "0"
			int(parti[5])
		except (ValueError, IndexError):
			continue      # db.cpp sare cheia fara numar (si decaleaza; aici blocul se sare intreg)
		s = Serviciu(sid, ns, tsid, onid, tip, nume, date, rest, (cheie, nume, date) if versiune == 4 else None)
		if s.k5 not in db.servicii:      # addService: primul castiga
			db.servicii[s.k5] = s
	if i >= n:
		raise Stricat("services neterminat")
	return db


def _s3_in_4(rand):
	"""Randul de satelit din formatul 3 (fara steaguri) in formatul 4: steagurile 0 dupa inversiune."""
	r = rand.strip()
	if not r.startswith("s "):
		return rand
	c = r[2:].split(":")
	if len(c) >= 6:
		c = c[:6] + ["0"] + c[6:]
	return "\ts " + ":".join(c)


def _citeste5(randuri):
	"""lamedb /5/: t:ns:tsid:onid,<fel>:<parametri>[,MIS/PLS:...][,T2MI:...] si s:sid:ns:tsid:onid:tip:nr[:sursa],"nume",..."""
	db = Lamedb()
	db.versiune = 5
	for rand in randuri[1:]:
		if rand.startswith("t:"):
			bucati = rand[2:].split(",")
			parti = bucati[0].split(":")
			try:
				ns, tsid, onid = _int16(parti[0]), _int16(parti[1]), _int16(parti[2])
			except (ValueError, IndexError):
				continue
			if len(bucati) < 2 or len(bucati[1]) < 3 or bucati[1][1] != ":":
				continue
			fel, valori = bucati[1][0], bucati[1][2:].split(":")
			mis = t2mi = None
			for b in bucati[2:]:
				if b.startswith("MIS/PLS:"):
					mis = b[8:].split(":")
				elif b.startswith("T2MI:"):
					t2mi = b[5:].split(":")
			if fel == "s" and (mis or t2mi):
				# multistream si T2-MI numai in DVB-S2: sistemul, modulatia, rolloff-ul si pilotul implicite
				valori = (valori + ["0"] * 7)[:7] if len(valori) < 11 else valori[:11]
				if len(valori) == 7:
					valori += ["1", "1", "0", "2"]
				valori += list(mis or ("-1", "0", "1"))
				if t2mi:
					valori += list(t2mi)
			db.transpondere[(ns, tsid, onid)] = Transponder(ns, tsid, onid, ["\t%s %s" % (fel, ":".join(valori))])
		elif rand.startswith("s:"):
			poz = rand.find(',"')
			if poz < 0:
				continue
			parti = rand[2:poz].split(":")
			sfarsit = rand.find('"', poz + 2)
			if sfarsit < 0:
				continue
			nume = rand[poz + 2:sfarsit]
			rest_date = rand[sfarsit + 1:]
			if rest_date.startswith(","):
				rest_date = rest_date[1:]
			try:
				sid, ns, tsid, onid = _int16(parti[0]), _int16(parti[1]), _int16(parti[2]), _int16(parti[3])
				tip = int(parti[4])
			except (ValueError, IndexError):
				continue
			furnizor, cache, caids, steaguri, alte = "", {}, [], 0, []
			for camp in (rest_date.split(",") if rest_date else []):
				if len(camp) < 2 or camp[1] != ":":
					continue
				lit, val = camp[0], camp[2:]
				try:
					if lit == "p":
						furnizor = val
					elif lit == "c":
						cache[int(val[:2])] = int(val[2:], 16)
					elif lit == "C":
						caids.append(int(val, 16))
					elif lit == "f":
						steaguri = int(val, 16)
					else:
						alte.append(camp)
				except ValueError:
					continue
			s = Serviciu(sid, ns, tsid, onid, tip, nume, scrie_date(furnizor, cache, caids, steaguri, alte), "0")
			if s.k5 not in db.servicii:
				db.servicii[s.k5] = s
	return db


# ---------------------------------------------------------------- buchetele

class Intrare(object):
	"""Un rand de buchet. id = numarul stabil din sesiune; ref = textul referintei; descriere = #DESCRIPTION sau None."""
	__slots__ = ("id", "ref", "descriere", "_r")

	def __init__(self, id_, ref, descriere=None):
		self.id = id_
		self.ref = ref
		self.descriere = descriere
		self._r = None

	@property
	def r(self):
		if self._r is None:
			self._r = Referinta(self.ref)
		return self._r

	@property
	def fel(self):
		return self.r.fel()

	@property
	def cheie(self):
		return self.r.cheie()

	@property
	def fisier(self):
		return self.r.fisier()

	def cu(self, ref=None, descriere=False):
		"""O intrare noua cu acelasi id (descriere=False: ramane cea de acum)."""
		return Intrare(self.id, self.ref if ref is None else ref, self.descriere if descriere is False else descriere)

	def randuri(self):
		r = ["#SERVICE " + self.ref]
		if self.descriere:
			r.append("#DESCRIPTION " + taie_octeti(self.descriere, LUNGIME_MAXIMA - 13))
		return r


class Buchet(object):
	"""Un fisier de buchet: nume (#NAME intreg, cu „ (TV)” cand il are), intrari (tuplu de Intrare)."""
	__slots__ = ("id", "nume", "intrari", "crlf")

	def __init__(self, id_, nume, intrari, crlf=True):
		self.id = id_
		self.nume = nume
		self.intrari = tuple(intrari)
		self.crlf = crlf

	@property
	def radio(self):
		return self.id.endswith(".radio")

	def cu(self, nume=None, intrari=None):
		return Buchet(self.id, self.nume if nume is None else nume, self.intrari if intrari is None else intrari,
			self.crlf)

	def text(self):
		sf = "\r\n" if self.crlf else "\n"
		r = ["#NAME " + taie_octeti(self.nume, LUNGIME_MAXIMA - 6)]
		for i in self.intrari:
			r.extend(i.randuri())
		return sf.join(r) + sf


def citeste_buchet(fisier, text, numar_id):
	"""Textul unui buchet -> Buchet. numar_id() da id-urile intrarilor. Citirea se opreste la primul rand gol."""
	if isinstance(text, bytes):
		text = text.decode("utf-8", "surrogateescape")
	crlf = "\r\n" in text
	nume = ""
	intrari = []
	ultima = None
	for rand in text.split("\n"):
		if rand.endswith("\r"):
			rand = rand[:-1]
		if not rand:
			break
		if not rand.startswith("#"):
			continue
		if rand.startswith("#SERVICE"):
			ref = rand[10:] if rand[8:9] == ":" else rand[9:]
			ref = ref.strip()
			if not Referinta(ref).valida:
				ultima = None
				continue
			intrari.append([ref, None])
			ultima = intrari[-1]
		elif rand.startswith("#DESCRIPTION") and ultima is not None:
			ultima[1] = rand[14:] if rand[12:13] == ":" else rand[13:]
			ultima = None
		elif rand.startswith("#NAME "):
			nume = rand[6:]
			ultima = None
		else:
			ultima = None
	return Buchet(fisier, nume, [Intrare(numar_id(), r, d) for r, d in intrari], crlf)


def fara_mod(nume):
	for coada in (" (TV)", " (Radio)"):
		if nume.endswith(coada):
			return nume[:-len(coada)]
	return nume


def cu_mod(nume, radio):
	return "%s (%s)" % (nume, "Radio" if radio else "TV")


def id_buchet_nou(nume, radio, existente, prefix="userbouquet"):
	"""Numele fisierului unui buchet nou: userbouquet.<nume curat>.tv, unic."""
	baza = re.sub(r"[^a-z0-9]+", "_", fara_diacritice(nume).lower()).strip("_")[:40] or "buchet"
	coada = "radio" if radio else "tv"
	cand = "%s.%s.%s" % (prefix, baza, coada)
	n = 2
	while cand in existente:
		cand = "%s.%s_%d.%s" % (prefix, baza, n, coada)
		n += 1
	return cand


# ---------------------------------------------------------------- dosarul /etc/enigma2 intreg

class Date(object):
	"""Tot ce citeste editorul: lamedb, buchetele (cele legate si cele nelegate), listele parentale, satelitii."""

	def __init__(self):
		self.lamedb = Lamedb()
		self.buchete = {}           # id fisier -> Buchet
		self.originale = {}         # id fisier -> textul de pe disc (None pentru buchetele facute acum)
		self.blacklist = ()         # randurile fisierului, in ordine
		self.whitelist = ()
		self.sateliti = {}          # pozitie 0..3599 -> nume
		self.lamedb5 = False        # exista /etc/enigma2/lamedb5 (nu se scrie; intra numai in copia de siguranta)
		self._id = [0]

	def id_nou(self):
		self._id[0] += 1
		return self._id[0]


def _citeste_fisier(cale):
	try:
		with open(cale, "rb") as f:
			return f.read()
	except (IOError, OSError):
		return None


def citeste_dosar(director=DIRECTOR, lamedb_memorie=None, sateliti=SATELITI, date=None):
	"""Dosarul -> Date. lamedb_memorie = octetii listei din memoria enigma2 (saveServicelist), folositi in locul celor
	de pe disc cand se inteleg (au PID-urile invatate de la ultima scriere)."""
	d = date or Date()
	db = None
	if lamedb_memorie:
		try:
			db = citeste_lamedb(lamedb_memorie)
		except Stricat:
			db = None
	if db is None:
		text = _citeste_fisier(os.path.join(director, "lamedb"))
		if text:
			db = citeste_lamedb(text)
		else:
			db = Lamedb()
	d.lamedb = db
	d.lamedb5 = os.path.exists(os.path.join(director, "lamedb5"))
	vazute = set()

	def incarca(fisier):
		if fisier in vazute or not _NUME_FISIER.match(fisier):
			return
		vazute.add(fisier)
		text = _citeste_fisier(os.path.join(director, fisier))
		if text is None:
			if fisier in ("bouquets.tv", "bouquets.radio"):
				d.buchete[fisier] = Buchet(fisier, "Bouquets (%s)" % ("Radio" if fisier.endswith("radio") else "TV"),
					())
				d.originale[fisier] = None
			return
		b = citeste_buchet(fisier, text, d.id_nou)
		d.buchete[fisier] = b
		d.originale[fisier] = text
		for i in b.intrari:
			f = i.fisier
			if f and i.fel in ("subbuchet", "alternative"):
				incarca(f)

	incarca("bouquets.tv")
	incarca("bouquets.radio")
	try:
		nume = sorted(os.listdir(director))
	except OSError:
		nume = []
	for f in nume:
		if f in vazute:
			continue
		if (f.startswith("userbouquet.") or f.startswith("subbouquet.")) and (f.endswith(".tv") or f.endswith(".radio")):
			text = _citeste_fisier(os.path.join(director, f))
			if text is not None and _NUME_FISIER.match(f):
				d.buchete[f] = citeste_buchet(f, text, d.id_nou)
				d.originale[f] = text
	d.blacklist = _citeste_lista(os.path.join(director, "blacklist"))
	d.whitelist = _citeste_lista(os.path.join(director, "whitelist"))
	d.sateliti = citeste_sateliti(sateliti)
	return d


def _citeste_lista(cale):
	text = _citeste_fisier(cale)
	if not text:
		return ()
	return tuple(r.strip() for r in text.decode("utf-8", "surrogateescape").split("\n") if r.strip())


_SAT = re.compile(r"<sat\b([^>]*)>", re.S)
_ATR = re.compile(r'(\w+)="([^"]*)"')


def citeste_sateliti(cale=SATELITI):
	"""{pozitie 0..3599: nume} din satellites.xml (numai etichetele <sat>, fara transpondere)."""
	text = _citeste_fisier(cale)
	if not text:
		return {}
	try:
		text = text.decode("utf-8")
	except UnicodeDecodeError:
		text = text.decode("latin-1")
	rez = {}
	for m in _SAT.finditer(text):
		a = dict(_ATR.findall(m.group(1)))
		try:
			p = int(a.get("position", ""))
		except ValueError:
			continue
		if p < 0:
			p += 3600
		nume = a.get("name", "").replace("&amp;", "&").replace("&quot;", '"').replace("&lt;", "<").replace("&gt;", ">")
		rez[p] = nume
	return rez


def _t(text):
	"""Traducerea enigma2 (_ din builtins); pe PC textul asa cum e."""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def text_pozitie(poz):
	"""19,2°E / 30,0°W / Cablu / Terestru."""
	if poz == POZ_CABLU:
		return _t("Cablu")
	if poz == POZ_TERESTRU:
		return _t("Terestru")
	if poz is None:
		return ""
	if poz > 1800:
		return ("%.1f°W" % ((3600 - poz) / 10.0)).replace(".", ",")
	return ("%.1f°E" % (poz / 10.0)).replace(".", ",")


def poz_din_ns(ns):
	sus = ns >> 16
	if sus == 0xFFFF:
		return POZ_CABLU
	if sus == 0xEEEE:
		return POZ_TERESTRU
	if 0 <= sus < 3600:
		return sus
	return None


def ordine_pozitie(poz):
	"""Cablul, terestrul, apoi de la vest la est."""
	if poz == POZ_CABLU:
		return (0, 0)
	if poz == POZ_TERESTRU:
		return (1, 0)
	if poz is None:
		return (3, 0)
	return (2, poz - 3600 if poz > 1800 else poz)
