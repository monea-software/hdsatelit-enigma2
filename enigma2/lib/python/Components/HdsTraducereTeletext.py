# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsTraducereTeletext - traducerea paginii de teletext aratate pe televizor (Screens/HdsTeletext.py), prin
# Components/HdsTraducereTexte.py (instanta "teletext", setarea "Tradu teletextul", oprita din fabrica).
# Fisierul nu cere enigma2 la incarcare: probele de pe PC dau celulele paginii si traducatorul lor.
#
# CE SE TRADUCE: randurile 1-24 ale paginii (antetul, cu numarul paginii, numele si ceasul, nu), numai celulele cu
# litere: nu mozaicul, nu ce e ascuns (se vede numai cu INFO), nu jumatatile literelor duble. Un rand se imparte in
# bucati: literele cu cel mult un spatiu intre ele, de aceeasi culoare, pe acelasi fundal si de aceeasi marime; doua
# spatii, alta culoare, mozaicul sau o celula ascunsa despart bucatile. Raman pe loc, netraduse: numarul unei pagini
# (100-899) de la inceputul sau capatul unei bucati, ora de la inceputul ei ("20:15"), punctele sau liniutele care duc
# la numarul paginii, liniile de puncte sau liniute si bucatile fara litere (scoruri, numere). Randurile urmatoare care
# continua acelasi text (aceeasi coloana de inceput, aceeasi culoare si marime, iar primul lor cuvant n-ar fi incaput pe
# randul de dinainte) se lipesc intr-un paragraf, care se traduce intreg; despartirea in silabe de la capatul randului
# ("Bundes-" + "regierung") se reface.
#
# ASEZAREA (modul "pagina"): fiecare paragraf tradus se rupe pe cuvinte pe locurile lui (celulele textului si spatiile
# libere de dupa el, pe randurile lui; la un rand de cuprins si punctele spre numarul paginii, refacute dupa text: un
# spatiu, apoi punctele pana la numar); ce nu incape continua pe randurile goale de dedesubt (aceleasi coloane, acelasi
# fundal, nimic scris acolo), cu culoarea textului; ce nu incape nici asa se taie la un cuvant, cu "...". Nucleul pune
# literele peste celule (eHdsTeletextWidget.setTraducere), cu fundalul si atributele lor, numai cat pagina aratata are
# amprenta corpului pentru care s-a facut asezarea (amprenta: zlib.crc32 al celulelor randurilor 1-24, ca
# eHdsTeletextWidget.amprentaCorp), deci o pagina schimbata in carusel nu primeste traducerea alteia.
# PANOUL (modul "panou"): pagina originala si traducerea intreaga in randuri de citit (bucatile fiecarui rand in ordine,
# fiecare paragraf o singura data, la primul lui rand).
#
# MEMORIA: paragrafele in memoria traducatorului (serviciu, limba, amprenta textului; in RAM si pe un mediu extern),
# deci un text la fel nu se cere de doua ori, nici pe alta pagina; pagina asezata in RAM dupa (canal, pagina, subpagina,
# amprenta corpului, limba), deci o pagina la fel nu se mai aseaza (cel mult MAX_PAGINI).
#
# API: amprenta(octeti), imparte(randuri) -> (unitati, parti), aseaza(unitati, traduceri, randuri, parti) -> (litere,
#   culori), textPanou(parti, unitati, traduceri), traducere() = TraducereTeletext comuna tuturor ecranelor (paginile
#   asezate raman si dupa inchiderea teletextului), .pagina(ref, numar, subcod, octeti, cine, forteaza=False) -> Rezultat

from __future__ import absolute_import

import re
import zlib
from collections import OrderedDict

from Components import HdsTeletext as TT

COLOANE, RANDURI = TT.COLOANE, TT.RANDURI
CORP = (RANDURI - 1) * COLOANE      # celulele randurilor 1-24, in sirurile date nucleului
RAMANE = u"\x01"                     # la litere: celula ramane cum e
FARA_CULOARE = u"-"                  # la culori: culoarea celulei
PUNCTE = u"…"                   # la capatul unui text taiat
RAND_FASTTEXT = 24                   # randul legaturilor colorate: bucatile lui nu se lipesc cu altele
MAX_PAGINI = 64
MARIME = TT.A_DUBLA_INALTIME | TT.A_DUBLA_LATIME

FEL_OPRIT, FEL_LUCRU, FEL_TRADUS, FEL_DEJA, FEL_GOL = "oprit", "lucru", "tradus", "deja", "gol"

_LITERA = re.compile(u"[^\\W\\d_]", re.U)
_LINIE = re.compile(u"[.\\-_=*~]{4,}")                       # o linie de puncte sau liniute
_SPRE_PAGINA = re.compile(u"(?:^|(?<=\\s))[.\\-_=*~]+\\s*$")     # punctele dinaintea numarului paginii
_PAGINA_SFARSIT = re.compile(u"(?:^|(?<=[\\s.:>]))[<>]?[1-8][0-9]{2}[<>+]?$")
_PAGINA_INCEPUT = re.compile(u"^[<>]?[1-8][0-9]{2}[<>]?(?=\\s)")
_ORA_INCEPUT = re.compile(u"^[0-2]?[0-9][:.][0-5][0-9](?=\\s|$)")
_UMPLERE = re.compile(u"^([.\\-_=*~])\\1*$")


def amprenta(octeti):
	"""amprenta corpului (randurile 1-24) din cei 8000 de octeti ai paginii, ca eHdsTeletextWidget.amprentaCorp()"""
	return zlib.crc32(bytes(octeti[COLOANE * 8:RANDURI * COLOANE * 8])) & 0x7FFFFFFF


def areLitere(text):
	return len(_LITERA.findall(text or u"")) >= 2


# ------------------------------------------------------------------ impartirea paginii


class Parte(object):
	"""o bucata a unui rand: fixa (ramane pe loc) sau o linie a unei unitati de tradus"""
	__slots__ = ("rand", "coloane", "text", "fix", "cheie", "unitate", "prima", "umplere", "spre")

	def __init__(self, rand, coloane, text, fix, cheie):
		self.rand, self.coloane, self.text, self.fix, self.cheie = rand, coloane, text, fix, cheie
		self.unitate = None       # indicele unitatii (partile de tradus)
		self.prima = False        # prima linie a unitatii
		self.umplere = None       # la punctele spre numarul paginii: semnul lor
		self.spre = None          # la un text urmat de punctele spre numarul paginii: partea punctelor


class Unitate(object):
	"""un text de tradus: o bucata sau un paragraf de pe mai multe randuri; umplere[i]: semnul punctelor refacute dupa
	textul liniei i (None = spatii)"""
	__slots__ = ("linii", "text", "fata", "fundal", "marime", "parti", "umplere")

	def __init__(self, parte, coloane_libere, umplere=None):
		self.linii = [(parte.rand, list(parte.coloane) + list(coloane_libere))]
		self.umplere = [umplere]
		self.text = parte.text
		self.fata, self.fundal, self.marime = parte.cheie
		self.parti = [parte]

	def adauga(self, parte, coloane_libere, umplere=None):
		self.linii.append((parte.rand, list(parte.coloane) + list(coloane_libere)))
		self.umplere.append(umplere)
		self.parti.append(parte)
		vechi = self.text
		if len(vechi) > 1 and vechi.endswith(u"-") and vechi[-2].isalpha() and parte.text[:1].islower():
			self.text = vechi[:-1] + parte.text          # despartirea in silabe se reface
		else:
			self.text = vechi + u" " + parte.text


def _sloturi(rand):
	"""celulele unui rand ca sloturi (coloana, litera, fata, fundal, marime), None = o celula care desparte (mozaic,
	ascuns, jumatatea de jos a unei litere duble); jumatatile din dreapta ale literelor duble lipsesc (sunt ale literei
	din stanga)"""
	rez = []
	for c, (cod, mozaic, fata, fundal, atribute) in enumerate(rand):
		if atribute & TT.A_JUMATATE_DREAPTA:
			continue
		if mozaic or atribute & (TT.A_ASCUNS | TT.A_JUMATATE_JOS) or cod < 0x20:
			rez.append(None)
			continue
		try:
			litera = chr(cod)
		except (ValueError, OverflowError):
			rez.append(None)
			continue
		rez.append((c, litera, fata, fundal, atribute & MARIME))
	return rez


def _cheie(slot):
	return slot[2], slot[3], slot[4]


def _segmente(sloturi):
	"""indicii sloturilor fiecarei bucati: literele cu cel mult un spatiu intre ele, aceeasi cheie (culoare, fundal,
	marime)"""
	rez = []
	cur = None
	spatii = []
	for i, s in enumerate(sloturi):
		if s is None:
			if cur:
				rez.append(cur)
			cur, spatii = None, []
			continue
		if s[1] == u" ":
			if cur is not None:
				spatii.append(i)
			continue
		if cur is not None and len(spatii) <= 1 and _cheie(sloturi[cur[0]]) == _cheie(s):
			cur.extend(spatii)
			cur.append(i)
		else:
			if cur:
				rez.append(cur)
			cur = [i]
		spatii = []
	if cur:
		rez.append(cur)
	return rez


def _bucatiFixe(text):
	"""intervalele [a, b) ale textului unei bucati care raman pe loc: liniile de puncte sau liniute, numarul paginii de
	la inceput sau de la capat (si punctele dinaintea lui), ora de la inceput"""
	rez = [(m.start(), m.end()) for m in _LINIE.finditer(text)]
	for tipar in (_PAGINA_INCEPUT, _ORA_INCEPUT):
		m = tipar.search(text)
		if m:
			rez.append((m.start(), m.end()))
	m = _PAGINA_SFARSIT.search(text)
	if m:
		rez.append((m.start(), m.end()))
		p = _SPRE_PAGINA.search(text[:m.start()])
		if p:
			rez.append((p.start(), p.start() + len(p.group().rstrip())))
	rez.sort()
	unite = []
	for a, b in rez:
		if unite and a <= unite[-1][1]:
			unite[-1] = (unite[-1][0], max(b, unite[-1][1]))
		else:
			unite.append((a, b))
	return unite


def _partiRand(r, sloturi):
	"""partile unui rand, in ordinea coloanelor"""
	rez = []
	for seg in _segmente(sloturi):
		text = u"".join(sloturi[i][1] for i in seg)
		cheie = _cheie(sloturi[seg[0]])
		fixe = _bucatiFixe(text)
		bucati = []
		poz = 0
		for a, b in fixe:
			if a > poz:
				bucati.append((poz, a, False))
			bucati.append((a, b, True))
			poz = b
		if poz < len(text):
			bucati.append((poz, len(text), False))
		for a, b, fix in bucati:
			# fara spatiile de la capete
			while a < b and text[a] == u" ":
				a += 1
			while b > a and text[b - 1] == u" ":
				b -= 1
			if a >= b:
				continue
			bucata = text[a:b]
			fix = fix or not areLitere(bucata)
			rez.append(Parte(r, [sloturi[i][0] for i in seg[a:b]], bucata, fix, cheie))
	# punctele spre numarul paginii: textul de dinaintea lor le poate lua locul (se refac dupa el)
	for k in range(1, len(rez) - 1):
		p, inainte, dupa = rez[k], rez[k - 1], rez[k + 1]
		if p.fix and _UMPLERE.match(p.text) and dupa.fix and not inainte.fix and \
				p.coloane[0] - inainte.coloane[-1] <= 2 and _PAGINA_SFARSIT.search(dupa.text):
			p.umplere = p.text[0]
			inainte.spre = p
	return rez


def _libere(sloturi, ultima_coloana, cheie, pana_la_capat=False):
	"""coloanele spatiilor libere de dupa o bucata (aceeasi cheie), pana la urmatoarea litera sau desparțire; ultimul se
	lasa gol cand urmeaza ceva pe rand (pana_la_capat: toate, numai ca sa se numere)"""
	rez = []
	motiv = "capat"
	inceput = None
	for k, s in enumerate(sloturi):
		if s is not None and s[0] == ultima_coloana:
			inceput = k + 1
			break
	if inceput is None:
		return rez
	for s in sloturi[inceput:]:
		if s is None or s[1] != u" " or _cheie(s) != cheie:
			motiv = "altceva"
			break
		rez.append(s[0])
	if motiv != "capat" and rez and not pana_la_capat:
		rez.pop()
	return rez


def _acoperite(randuri):
	"""randurile de sub un rand cu litere de dubla inaltime (acoperite de ele)"""
	rez = set()
	for r in range(1, RANDURI - 1):
		if any(atr & TT.A_DUBLA_INALTIME for _c, _m, _f, _b, atr in randuri[r]):
			rez.add(r + 1)
	return rez


def imparte(randuri):
	"""celulele paginii (TT.decodeaza: 25 de randuri a cate 40) -> (unitati, parti): unitatile de tradus in ordinea
	citirii si partile fiecarui rand vazut {rand: [Parte]}"""
	acoperite = _acoperite(randuri)
	vazute = [r for r in range(1, RANDURI) if r not in acoperite]
	sloturi = dict((r, _sloturi(randuri[r])) for r in vazute)
	parti = dict((r, _partiRand(r, sloturi[r])) for r in vazute)
	unitati = []
	deschisa = None           # (unitatea, partea ultimei ei linii, coloana de inceput)
	for k, r in enumerate(vazute):
		pr = parti[r]
		urmator = vazute[k + 1] if k + 1 < len(vazute) else None
		continuare = None
		if deschisa is not None and pr and not pr[0].fix and r != RAND_FASTTEXT:
			u, ultima, col0 = deschisa
			p = pr[0]
			cuvant = p.text.split(u" ")[0]
			libere = len(_libere(sloturi[ultima.rand], ultima.coloane[-1], ultima.cheie, True))
			if p.cheie == ultima.cheie and p.coloane[0] == col0 and libere < len(cuvant) + 1:
				continuare = u
		deschisa = None
		for j, p in enumerate(pr):
			if p.fix:
				continue
			ultima_pe_rand = j == len(pr) - 1
			umplere = None
			if p.spre is not None:
				# pana la capatul punctelor spre numarul paginii (refacute dupa text)
				libere = list(range(p.coloane[-1] + 1, p.spre.coloane[-1] + 1))
				umplere = p.spre.umplere
			else:
				libere = _libere(sloturi[r], p.coloane[-1], p.cheie)
			if j == 0 and continuare is not None:
				u = continuare
				u.adauga(p, libere, umplere)
				p.unitate = unitati.index(u)
			else:
				u = Unitate(p, libere, umplere)
				p.unitate = len(unitati)
				p.prima = True
				unitati.append(u)
			if ultima_pe_rand and r != RAND_FASTTEXT and urmator is not None and urmator == r + 1 + (1 if r + 1 in acoperite else 0):
				deschisa = (u, p, u.parti[0].coloane[0])
	return unitati, parti


# ------------------------------------------------------------------ asezarea traducerii


def _rupe(text, latimi):
	"""cuvintele textului puse pe randuri de latimile date -> (randurile, cuvintele ramase); un cuvant mai lung decat
	randul gol se rupe"""
	cuvinte = text.split()
	rez = []
	for w in latimi:
		linie = u""
		while cuvinte:
			c = cuvinte[0]
			if not linie:
				if len(c) <= w:
					linie = c
					cuvinte.pop(0)
				else:
					linie = c[:w]
					cuvinte[0] = c[w:]
					break
			elif len(linie) + 1 + len(c) <= w:
				linie += u" " + c
				cuvinte.pop(0)
			else:
				break
		rez.append(linie)
	return rez, cuvinte


def _taie(text, w):
	"""textul cu "..." la capat, in w semne (taiat la un cuvant cand se poate)"""
	if w <= 1:
		return PUNCTE[:w]
	if len(text) + 1 <= w:
		return text + PUNCTE
	t = text[:w - 1]
	k = t.rfind(u" ")
	if k >= w // 2:
		t = t[:k]
	return t.rstrip() + PUNCTE


def _ocupate(parti):
	rez = set()
	for pr in parti.values():
		for p in pr:
			for c in p.coloane:
				rez.add((p.rand, c))
	return rez


def _randuriGoale(u, randuri, ocupate, acoperite, latime):
	"""randurile goale de sub unitate pe care poate continua: aceleasi coloane, fundalul ei, numai spatii, nimic
	scris acolo -> [(rand, coloane)]"""
	if u.marime:
		return []
	col0 = u.linii[0][1][0]
	if col0 + latime > COLOANE:
		latime = COLOANE - col0
	rez = []
	r = u.linii[-1][0] + 1
	while r < RAND_FASTTEXT:
		if r in acoperite:
			break
		bune = True
		for c in range(col0, col0 + latime):
			cod, mozaic, _fata, fundal, atribute = randuri[r][c]
			if cod != 0x20 or mozaic or fundal != u.fundal or atribute or (r, c) in ocupate:
				bune = False
				break
		if not bune:
			break
		rez.append((r, list(range(col0, col0 + latime))))
		r += 1
	return rez


def aseaza(unitati, traduceri, randuri, parti=None):
	"""traducerile asezate pe pagina -> (litere, culori): cate CORP semne pentru eHdsTeletextWidget.setTraducere
	(RAMANE / FARA_CULOARE = celula neatinsa); traducerea None sau egala cu originalul lasa unitatea neatinsa"""
	litere = [RAMANE] * CORP
	culori = [FARA_CULOARE] * CORP
	ocupate = _ocupate(parti) if parti is not None else set()
	acoperite = _acoperite(randuri)
	for u, tr in zip(unitati, traduceri):
		if tr is None or tr == u.text:
			continue
		tr = u" ".join(tr.split())
		linii = list(u.linii)
		latimi = [len(c) for _r, c in linii]
		bucati, rest = _rupe(tr, latimi)
		extra = []
		if rest:
			extra = _randuriGoale(u, randuri, ocupate, acoperite, max(latimi))
			if extra:
				b2, rest = _rupe(u" ".join(rest), [len(c) for _r, c in extra])
				extra = [(e, b) for e, b in zip(extra, b2) if b]
				for (r, cols), _b in extra:
					for c in cols:
						ocupate.add((r, c))
		if rest:
			# ce nu incape: ultimul rand scris se taie la un cuvant, cu "..."
			if extra:
				(r, cols), b = extra[-1]
				extra[-1] = ((r, cols), _taie(b, len(cols)))
			else:
				k = max(i for i, b in enumerate(bucati) if b) if any(bucati) else len(bucati) - 1
				bucati[k] = _taie(bucati[k], latimi[k])
		for (r, cols), b, umplere in zip(linii, bucati, u.umplere):
			for k, c in enumerate(cols):
				if k < len(b):
					litere[(r - 1) * COLOANE + c] = b[k]
				else:
					litere[(r - 1) * COLOANE + c] = umplere if umplere and k > len(b) else u" "
		for (r, cols), b in extra:
			for k, c in enumerate(cols):
				i = (r - 1) * COLOANE + c
				litere[i] = b[k] if k < len(b) else u" "
				culori[i] = u"%d" % (u.fata & 7)
	return u"".join(litere), u"".join(culori)


def textPanou(parti, unitati, traduceri):
	"""randurile panoului: pe fiecare rand al paginii bucatile lui in ordine (fixele cum sunt, paragraful tradus o
	singura data, la primul lui rand); randurile goale despart (unul singur intre doua bucati)"""
	rez = []
	for r in sorted(parti):
		bucati = []
		for p in parti[r]:
			if p.umplere:
				continue			# punctele spre numarul paginii: numai pe pagina
			if p.fix:
				bucati.append(p.text)
			elif p.prima:
				tr = traduceri[p.unitate] if p.unitate < len(traduceri) else None
				bucati.append(tr if tr else unitati[p.unitate].text)
		if bucati:
			rez.append(u"  ".join(bucati))
		elif rez and rez[-1]:
			rez.append(u"")
	while rez and not rez[-1]:
		rez.pop()
	return rez


# ------------------------------------------------------------------ pagina pentru ecran


class Rezultat(object):
	"""ce arata ecranul pentru o pagina: fel (FEL_*), amprenta, litere si culori (FEL_TRADUS), randurile panoului"""
	__slots__ = ("fel", "amprenta", "litere", "culori", "panou", "texte")

	def __init__(self, fel, amprenta_=None, litere=None, culori=None, panou=None, texte=0):
		self.fel, self.amprenta, self.litere, self.culori = fel, amprenta_, litere, culori
		self.panou = panou or []
		self.texte = texte


def _X():
	from Components import HdsTraducereTexte
	return HdsTraducereTexte


def _limba():
	try:
		from Components import HdsTraducereSubtitrari
		return HdsTraducereSubtitrari.limbaTinta()
	except Exception:
		return u""


class TraducereTeletext(object):
	"""traducerea paginilor pentru un ecran al teletextului: pagina asezata, tinuta minte (cel mult MAX_PAGINI)"""

	def __init__(self, traducator=None, limba=None):
		self._pagini = OrderedDict()
		self._ultima = (None, None)       # (cheia, rezultatul) cererii de dinainte
		self._traducator = traducator     # probele: (texte, cine, cere) -> (lista, stare)
		self._limba = limba
		try:
			_X().ascultaSchimbarile(self._setariSchimbate)
		except Exception:
			pass

	def _setariSchimbate(self, element=None):
		self.uita()

	def uita(self):
		"""setarile s-au schimbat (serviciul, limba): paginile se aseaza din nou"""
		self._pagini.clear()
		self._ultima = (None, None)

	def _traduceri(self, texte, cine):
		if self._traducator is not None:
			return self._traducator(texte, cine, True)
		return _X().traduceri("teletext", texte, cine, True)

	def pornita(self):
		if self._traducator is not None:
			return True
		return _X().poartaDeschisa("teletext")

	def pagina(self, ref, numar, subcod, octeti, cine=None, forteaza=False):
		"""Rezultatul paginii (octetii din eHdsTeletext.pagina). Aceeasi pagina ca la chemarea de dinainte, inca in
		lucru, nu se cere din nou (forteaza: a venit o traducere); o pagina asezata vine din memorie."""
		if octeti is None or len(octeti) < RANDURI * COLOANE * 8:
			return Rezultat(FEL_GOL)
		amp = amprenta(octeti)
		if not self.pornita():
			return Rezultat(FEL_OPRIT, amp)
		limba = self._limba if self._limba is not None else _limba()
		cheie = (ref or u"", numar, subcod, amp, limba)
		gata = self._pagini.get(cheie)
		if gata is not None:
			self._pagini.move_to_end(cheie)
			self._ultima = (cheie, gata)
			return gata
		vechea, rez_vechi = self._ultima
		if vechea == cheie and rez_vechi is not None and not forteaza:
			return rez_vechi
		randuri = TT.decodeaza(octeti)
		unitati, parti = imparte(randuri)
		texte = [u.text for u in unitati]
		if not texte:
			rez = Rezultat(FEL_GOL, amp)
			self._tine(cheie, rez)
			return rez
		lista, stare = self._traduceri(texte, cine)
		if stare == "lucru":
			rez = Rezultat(FEL_LUCRU, amp, texte=len(texte))
			self._ultima = (cheie, rez)
			return rez
		if stare == "oprit":
			rez = Rezultat(FEL_OPRIT, amp, texte=len(texte))
			self._ultima = (cheie, rez)
			return rez
		if stare != "tradus":
			rez = Rezultat(FEL_DEJA, amp, texte=len(texte))
			self._tine(cheie, rez)
			return rez
		litere, culori = aseaza(unitati, lista, randuri, parti)
		rez = Rezultat(FEL_TRADUS, amp, litere, culori, textPanou(parti, unitati, lista), len(texte))
		self._tine(cheie, rez)
		return rez

	def _tine(self, cheie, rez):
		self._pagini[cheie] = rez
		self._ultima = (cheie, rez)
		while len(self._pagini) > MAX_PAGINI:
			self._pagini.popitem(last=False)


_TRADUCERE = [None]


def traducere():
	"""TraducereTeletext comuna ecranelor teletextului"""
	if _TRADUCERE[0] is None:
		_TRADUCERE[0] = TraducereTeletext()
	return _TRADUCERE[0]
