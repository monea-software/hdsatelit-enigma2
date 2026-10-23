# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsRadioDesen.py: vizualizatoarele ecranului radio, desenate cu eCanvas (Sources/CanvasSource + Renderer/Canvas).
#
# Datele vin numai din analizor (Components/HdsRadioAnaliza.py): nivelul fiecarei subbande de fs/64 din cadrele postului,
# pe orice format de sunet (factorii de scala MPEG sau nucleul lib/dvb/hdsspectru.cpp), deci sunetul adevarat al
# postului. Unde nu sunt date, nu se deseneaza nimic miscat.
#
# De la subbenzi la bare: barele din stanga iau cate o subbanda (750 Hz la 48 kHz), cele din dreapta aduna mai
# multe, cu latimi care cresc (grupe()). Barele nu sunt mai multe decat subbenzile cu date: un flux cu 8 subbenzi
# (debit mic) are cel mult 8 bare, mai late.
#
# Desenul e incremental: panza (pixmap-ul lui eCanvas) pastreaza ce s-a desenat, iar la fiecare cadru se trimit numai
# umplerile care schimba ceva: partea cu care a crescut sau a scazut fiecare bara, varful vechi sters si cel nou
# desenat. Cel mult cateva umpleri pe bara, fara stergerea intregii zone. Culoarea unui rand depinde numai de
# inaltimea lui (trei zone), deci bucatile adaugate se potrivesc cu ce era. Umplerile mari si copierile le face placa
# 2D cand accelerarea e pornita, altfel procesorul: rezerva e a stratului de desen, nu a acestui fisier.
# Cercul foloseste liniile netede din nucleu (drawLine, drawRing) si se sterge in patratul lui la fiecare cadru.
#
# Fisierul nu importa nimic din enigma2 la incarcare (probele de pe PC).

import math

# fundalul ferestrei radio; acelasi ca backgroundColor din blocul HdsEcranRadio al skinului
FUNDAL = 0x0A0F1A
FUNDAL_ODIHNA = 0x0A0F1A

# 0 dB = semnal plin; sub DB_JOS bara e goala. 27 de trepte de 2 dB ale factorilor de scala.
DB_JOS = -54.0
# nivelul stanga / dreapta: scala de 20 dB a indicatoarelor de nivel. Masurat pe muzica codata MP2 (40 s, ferestre de
# 3 cadre ca pe ecran): varful e intre -14 dB (5% din timp mai jos) si -2 dB (5% mai sus), deci indicatorul merge intre
# 0,3 si 0,9; pe scala de 54 dB a barelor ar fi stat mereu intre 0,75 si 0,96.
DB_NIVEL_JOS = -20.0
# contrastul minim al culorilor barelor fata de fundal (elemente grafice: 3:1)
CONTRAST_BARE = 3.0
ZONA_MIJLOC = 0.62
ZONA_SUS = 0.86
CADERE = 1.5                 # cat coboara o bara pe secunda (1.0 = toata inaltimea)
VARF_TINUT = 0.35            # cat sta varful sus inainte sa cada
VARF_CADERE = 0.45
NIVEL_CADERE = 1.2
NIVEL_VARF_TINUT = 1.5
GROSIME_VARF = 4
SUBBENZI_20KHZ = 27          # la 48 kHz: 27 x 750 Hz = 20,25 kHz

# (jos, mijloc, sus, varf); fara alb curat (arderea ecranului)
TEME = {
	"skin": (0x374EA1, 0x9FB4FF, 0xF5B83D, 0xD8E0F0),
	"clasic": (0x2FB84F, 0xE8C53A, 0xE5484D, 0xD9DDE3),
	"albastru": (0x1E4FA8, 0x3A7BD5, 0x7FB8FF, 0xC9DDF5),
	"foc": (0x8B1A00, 0xE8590C, 0xFFC53D, 0xF2E3B3),
	"discret": (0x394150, 0x566072, 0x7A8394, 0x98A0AE),
}
# culorile skinului cautate pentru tema „skin” (skin.colorNames), in ordinea (jos, mijloc, sus, varf)
CULORI_SKIN = ("hdsBrand", "hdsBrandLight", "hdsAmber", "hdsText2")


def _luminanta(c):
	def canal(v):
		v = v / 255.0
		return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
	return 0.2126 * canal((c >> 16) & 255) + 0.7152 * canal((c >> 8) & 255) + 0.0722 * canal(c & 255)


def contrast(a, b):
	"""Raportul de contrast WCAG intre doua culori 0xRRGGBB."""
	la, lb = _luminanta(a), _luminanta(b)
	return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def amestec(a, b, parte):
	"""Culoarea a amestecata cu b (parte = cat din b)."""
	rez = 0
	for deplasare in (16, 8, 0):
		x = (a >> deplasare) & 255
		y = (b >> deplasare) & 255
		rez |= int(round(x + (y - x) * parte)) << deplasare
	return rez


def cu_contrast(culoare, spre, fundal=FUNDAL, minim=CONTRAST_BARE):
	"""Culoarea, deschisa pas cu pas spre `spre` pana are contrastul `minim` fata de fundal (baza barelor sta cea mai
	mare parte din timp pe ecran, deci trebuie sa se vada)."""
	c = culoare
	for pas in range(1, 11):
		if contrast(c, fundal) >= minim:
			return c
		c = amestec(culoare, spre, pas / 10.0)
	return c


_TEME_GATA = {}


def tema(nume, colorNames=None):
	"""Culorile temei. „skin”: culorile skinului care se folosesc, daca le are, altfel cele de rezerva. Culoarea de
	jos a barelor are cel putin CONTRAST_BARE fata de fundal (se deschide spre culoarea din mijloc cand nu are).
	Se cheama la fiecare cadru: fara colorNames dat, rezultatul se tine minte (culorile skinului nu se schimba cat
	merge enigma2)."""
	if colorNames is None and nume in _TEME_GATA:
		return _TEME_GATA[nume]
	rez = _tema(nume, colorNames)
	if colorNames is None:
		_TEME_GATA[nume] = rez
	return rez


def _tema(nume, colorNames=None):
	baza = TEME.get(nume, TEME["skin"])
	rez = list(baza)
	if nume == "skin":
		if colorNames is None:
			try:
				from skin import colorNames
			except Exception:
				colorNames = None
		if colorNames is not None:
			for i, cheie in enumerate(CULORI_SKIN):
				c = colorNames.get(cheie) if hasattr(colorNames, "get") else None
				try:
					rez[i] = c.argb() & 0xFFFFFF if c is not None else baza[i]
				except Exception:
					rez[i] = baza[i]
	rez[0] = cu_contrast(rez[0], rez[1])
	return tuple(rez)


def intunecat(culoare, parte=0.5):
	"""Culoarea mai inchisa (pentru ecranul de odihna)."""
	r = int(((culoare >> 16) & 255) * parte)
	g = int(((culoare >> 8) & 255) * parte)
	b = int((culoare & 255) * parte)
	return (r << 16) | (g << 8) | b


def grupe(bare, subbenzi):
	"""[(prima subbanda, dupa ultima)] pentru fiecare bara; latimile cresc spre dreapta. Cel mult cate o bara pe
	subbanda."""
	subbenzi = max(1, subbenzi)
	n = max(1, min(bare, subbenzi))
	margini = [0]
	for j in range(1, n + 1):
		e = int(round(subbenzi * (float(j) / n) ** 1.6))
		e = max(e, margini[-1] + 1)
		e = min(e, subbenzi - (n - j))
		margini.append(e)
	margini[-1] = subbenzi
	return [(margini[k], margini[k + 1]) for k in range(n)]


def subbenzi_utile(subbenzi, esantionare):
	"""Subbenzile afisate: la 44,1 si 48 kHz pana la 20 kHz, altfel toate cu date."""
	if esantionare and esantionare >= 44100:
		return min(subbenzi, SUBBENZI_20KHZ)
	return subbenzi


def db_din_factor(indice):
	if indice >= 63:
		return -120.0
	return 6.02 - 2.0069 * indice


def normat(db):
	v = (db - DB_JOS) / -DB_JOS
	return 0.0 if v < 0 else (1.0 if v > 1 else v)


def tinte_bare(nivele, bare, esantionare=48000):
	"""Din (subbenzi, f0, f1) al analizorului: inaltimea tinta (0..1) a fiecarei bare, cu varful din amandoua
	canalele. -> lista, sau [] fara date."""
	if not nivele:
		return []
	subbenzi, f0, f1 = nivele
	s = subbenzi_utile(subbenzi, esantionare)
	rez = []
	for a, b in grupe(bare, s):
		m = min(f0[a:b])
		if f1 is not None:
			m = min(m, min(f1[a:b]))
		rez.append(normat(db_din_factor(m)))
	return rez


def normat_nivel(db):
	v = (db - DB_NIVEL_JOS) / -DB_NIVEL_JOS
	return 0.0 if v < 0 else (1.0 if v > 1 else v)


def niveluri_canale(nivele):
	"""(stanga, dreapta) intre 0 si 1: varful fiecarui canal pe toate subbenzile, pe scala de 20 dB a indicatoarelor
	de nivel (DB_NIVEL_JOS). Mono: acelasi in amandoua."""
	if not nivele:
		return (0.0, 0.0)
	subbenzi, f0, f1 = nivele
	st = normat_nivel(db_din_factor(min(f0)))
	dr = normat_nivel(db_din_factor(min(f1))) if f1 is not None else st
	return (st, dr)


class Dinamica(object):
	"""Barele urca pe loc si coboara lin; varfurile stau putin sus si cad incet."""

	def __init__(self, cadere=CADERE, varf_tinut=VARF_TINUT, varf_cadere=VARF_CADERE):
		self.cadere = cadere
		self.varf_tinut = varf_tinut
		self.varf_cadere = varf_cadere
		self.v = []
		self.varf = []
		self.pana_la = []
		self.t = None

	def reset(self, n=0):
		self.v = [0.0] * n
		self.varf = [0.0] * n
		self.pana_la = [0.0] * n
		self.t = None

	def pas(self, tinte, acum):
		n = len(tinte)
		if n != len(self.v):
			self.reset(n)
		dt = 0.05 if self.t is None else max(0.0, min(0.5, acum - self.t))
		self.t = acum
		for i in range(n):
			v = self.v[i] - self.cadere * dt
			if tinte[i] > v:
				v = tinte[i]
			if v < 0:
				v = 0.0
			self.v[i] = v
			if v >= self.varf[i]:
				self.varf[i] = v
				self.pana_la[i] = acum + self.varf_tinut
			elif acum > self.pana_la[i]:
				p = self.varf[i] - self.varf_cadere * dt
				self.varf[i] = p if p > v else v
		return self.v, self.varf


class Panza(object):
	"""Starea desenata a unui vizualizator si umplerile de la un cadru la altul. Operatiile:
	("f", x, y, l, i, culoare), ("l", x0, y0, x1, y1, grosime, culoare), ("r", cx, cy, raza, grosime, culoare),
	("t", x, y, l, i, culoare, fundal, font, text)."""

	def __init__(self, latime, inaltime, fel="varfuri", culori=None, fundal=FUNDAL):
		self.L = int(latime)
		self.I = int(inaltime)
		self.fel = fel
		self.culori = culori or TEME["skin"]
		self.fundal = fundal
		self.curata = True          # la primul cadru si dupa o schimbare: toata zona o data
		self.desenat = []           # inaltimea desenata a fiecarei bare (pixeli)
		self.varf_desenat = []      # pozitia desenata a varfului (pixeli de la baza) sau None
		self.coloane = []           # (x, latime) pentru fiecare bara
		self.din = Dinamica()
		self.nivel = Dinamica(cadere=NIVEL_CADERE, varf_tinut=NIVEL_VARF_TINUT, varf_cadere=2.0)

	def schimba(self, fel=None, culori=None):
		if fel is not None and fel != self.fel:
			self.fel = fel
			self.curata = True
		if culori is not None and tuple(culori) != tuple(self.culori):
			self.culori = tuple(culori)
			self.curata = True

	def goleste(self):
		"""Zona goala (fara date): un singur fill, apoi nimic pana vin date."""
		self.curata = True
		self.desenat = []
		self.varf_desenat = []
		self.din.reset()
		self.nivel.reset()
		return [("f", 0, 0, self.L, self.I, self.fundal)]

	# ---- ajutoare

	def _culoare(self, parte):
		c = self.culori
		if parte < ZONA_MIJLOC:
			return c[0]
		if parte < ZONA_SUS:
			return c[1]
		return c[2]

	def _randuri(self, a, b, maxim):
		"""Bucatile [a, b) (pixeli de la baza) taiate la granitele zonelor: [(a, b, culoare)]."""
		if b <= a:
			return []
		z1 = int(maxim * ZONA_MIJLOC)
		z2 = int(maxim * ZONA_SUS)
		rez = []
		for lo, hi, c in ((0, z1, self.culori[0]), (z1, z2, self.culori[1]), (z2, maxim + 1, self.culori[2])):
			x0 = max(a, lo)
			x1 = min(b, hi)
			if x1 > x0:
				rez.append((x0, x1, c))
		return rez

	def _coloane(self, n, latime):
		spatiu = max(2, int(latime / float(n) * 0.18))
		l = (latime - spatiu * (n - 1)) / float(n)
		self.coloane = []
		for i in range(n):
			x0 = int(round(i * (l + spatiu)))
			x1 = int(round(i * (l + spatiu) + l))
			self.coloane.append((x0, max(1, x1 - x0)))

	# ---- barele (in sus sau in oglinda)

	def _bare(self, tinte, acum, oglinda=False, cu_varfuri=True):
		ops = []
		n = len(tinte)
		if self.curata or len(self.desenat) != n:
			ops.append(("f", 0, 0, self.L, self.I, self.fundal))
			self._coloane(n, self.L)
			self.desenat = [0] * n
			self.varf_desenat = [None] * n
			self.curata = False
		v, varf = self.din.pas(tinte, acum)
		if oglinda:
			maxim = self.I // 2
			baza = self.I // 2
		else:
			maxim = self.I - GROSIME_VARF - 1
			baza = self.I
		for i in range(n):
			x, l = self.coloane[i]
			h = int(round(v[i] * maxim))
			h0 = self.desenat[i]
			if h > h0:
				for a, b, c in self._randuri(h0, h, maxim):
					ops.extend(self._dreptunghi(x, l, a, b, c, baza, oglinda))
			elif h < h0:
				ops.extend(self._dreptunghi(x, l, h, h0, self.fundal, baza, oglinda))
			self.desenat[i] = h
			if not cu_varfuri or oglinda:
				continue
			p = int(round(varf[i] * maxim))
			if p < h:
				p = h
			p0 = self.varf_desenat[i]
			if p0 == p and h <= p:
				continue
			if p0 is not None and p0 != p:
				# varful vechi: se pune la loc ce e sub el (bara sau fundalul)
				lo, hi = p0, p0 + GROSIME_VARF
				if hi > h:
					ops.extend(self._dreptunghi(x, l, max(lo, h), hi, self.fundal, baza, False))
			if p > 0 or h > 0:
				ops.append(("f", x, baza - p - GROSIME_VARF, l, GROSIME_VARF, self.culori[3]))
				self.varf_desenat[i] = p
			else:
				self.varf_desenat[i] = None
		return ops

	def _dreptunghi(self, x, l, a, b, c, baza, oglinda):
		"""Randurile [a, b) de la baza, ca umpleri; in oglinda, simetric fata de mijloc."""
		if b <= a:
			return []
		if oglinda:
			return [("f", x, baza - b, l, b - a, c), ("f", x, baza + a, l, b - a, c)]
		return [("f", x, baza - b, l, b - a, c)]

	# ---- cercul

	def _cerc(self, tinte, acum):
		"""Cercul in oglinda: basurile jos, frecventele inalte sus, aceleasi benzi pe partea stanga si pe cea dreapta
		(nicio raza nu sta fix la ora 12). Inelul ia o cincime din inaltime, razele restul."""
		ops = []
		n = len(tinte)
		cx = self.L / 2.0
		cy = self.I / 2.0
		r0 = self.I * 0.2
		lung = self.I * 0.5 - r0 - 4
		latura = int(2 * (r0 + lung + 8))
		if self.curata or len(self.desenat) != n:
			ops.append(("f", 0, 0, self.L, self.I, self.fundal))
			self.desenat = [0] * n
			self.curata = False
		v, varf = self.din.pas(tinte, acum)
		ops.append(("f", int(cx - latura / 2), max(0, int(cy - latura / 2)), latura, min(self.I, latura), self.fundal))
		ops.append(("r", cx, cy, r0 - 4, 2.0, self.culori[0]))
		grosime = max(3.0, min(14.0, math.pi * r0 / n * 0.55))
		for i in range(n):
			abatere = 180.0 * (i + 0.5) / n
			d = 4 + v[i] * lung
			culoare = self._culoare(v[i])
			for grade in (90.0 - abatere, 90.0 + abatere):
				unghi = math.radians(grade)
				c = math.cos(unghi)
				s = math.sin(unghi)
				ops.append(("l", cx + r0 * c, cy + r0 * s, cx + (r0 + d) * c, cy + (r0 + d) * s, grosime, culoare))
		return ops

	# ---- nivelul stanga / dreapta

	def _nivel(self, canale, acum, font=None):
		ops = []
		eticheta = 60 if font is not None else 0
		latime = self.L - eticheta
		inalt = int(self.I * 0.28)
		rand = ((self.I // 2 - inalt - 8), (self.I // 2 + 8))
		if self.curata or len(self.desenat) != 2:
			ops.append(("f", 0, 0, self.L, self.I, self.fundal))
			self.desenat = [0, 0]
			self.varf_desenat = [None, None]
			self.curata = False
			for k, text in enumerate(("S", "D")):
				if font is not None:
					ops.append(("t", 0, rand[k], eticheta - 12, inalt, self.culori[3], self.fundal, font, text))
			# gradatia: cate un semn la fiecare 5 dB, sub fiecare rand
			for k in range(2):
				for pas in range(0, int(-DB_NIVEL_JOS) + 1, 5):
					x = eticheta + int(latime * (1.0 - pas / -DB_NIVEL_JOS)) - 1
					ops.append(("f", max(eticheta, x), rand[k] + inalt + 2, 2, 6, self.culori[0]))
		v, varf = self.nivel.pas(list(canale), acum)
		# bara are loc pana la latime - GROSIME_VARF - 1, ca semnul varfului sa incapa mereu dupa ea
		maxim = latime - GROSIME_VARF - 1
		for k in range(2):
			w = int(round(v[k] * maxim))
			w0 = self.desenat[k]
			y = rand[k]
			if w > w0:
				for a, b, c in self._randuri(w0, w, maxim):
					ops.append(("f", eticheta + a, y, b - a, inalt, c))
			elif w < w0:
				ops.append(("f", eticheta + w, y, w0 - w, inalt, self.fundal))
			self.desenat[k] = w
			p = max(w, int(round(varf[k] * maxim)))
			p0 = self.varf_desenat[k]
			if p0 != p:
				if p0 is not None and p0 + GROSIME_VARF > w:
					a = max(p0, w)
					ops.append(("f", eticheta + a, y, p0 + GROSIME_VARF - a, inalt, self.fundal))
				if p > 0:
					ops.append(("f", eticheta + p, y, GROSIME_VARF, inalt, self.culori[3]))
					self.varf_desenat[k] = p
				else:
					self.varf_desenat[k] = None
		return ops

	# ---- un cadru

	def cadru(self, nivele, bare, acum, esantionare=48000, font=None):
		"""Operatiile de desen ale unui cadru pentru `nivele` (de la analizor). Fara nivele: cadrul nu schimba nimic
		(zona ramane cum e; ecranul o goleste o data cu goleste() cand datele se opresc)."""
		if self.fel == "oprit" or not nivele:
			return []
		if self.fel == "nivel":
			return self._nivel(niveluri_canale(nivele), acum, font)
		tinte = tinte_bare(nivele, bare, esantionare)
		if not tinte:
			return []
		if self.fel == "cerc":
			return self._cerc(tinte, acum)
		return self._bare(tinte, acum, oglinda=(self.fel == "oglinda"), cu_varfuri=(self.fel == "varfuri"))


def aplica(sursa, ops):
	"""Operatiile pe un CanvasSource: o lista noua de desen (clear), umplerile, apoi flush. Lista nu creste de la un
	cadru la altul: Renderer/Canvas o deseneaza pe toata cand i se schimba secventa."""
	sursa.clear()
	for op in ops:
		fel = op[0]
		if fel == "f":
			sursa.fill(int(op[1]), int(op[2]), int(op[3]), int(op[4]), op[5])
		elif fel == "l":
			sursa.drawLine(op[1], op[2], op[3], op[4], op[5], op[6])
		elif fel == "r":
			sursa.drawRing(op[1], op[2], op[3], op[4], op[5])
		elif fel == "t":
			sursa.writeText(int(op[1]), int(op[2]), int(op[3]), int(op[4]), op[5], op[6], op[7], op[8], 1 | 8)   # RT_HALIGN_RIGHT | RT_VALIGN_CENTER
	sursa.flush()
