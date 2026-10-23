# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsQr: cod QR (ISO/IEC 18004) pentru o adresa scurta, fara biblioteci straine: modul octeti, nivelul de corectie M,
# versiunile 1-10 (cel mult 213 octeti). Iese o matrice de 0/1 (1 = patrat inchis), fara marginea alba; desenul
# il face ecranul, cu CanvasSource.fill() (deseneaza()). Modul comun al imaginii: ecranele traducerii subtitrarilor
# (Screens/HdsTraducereSubtitrari.py: telefonul asociat prin cod, paginile oficiale ale cheilor) si navigatorul
# (Plugins/Extensions/HdsNavigator: rezerva spre pagina „Interfețe CAM”).
#
# Pasii: bitii datelor (modul 0100, lungimea, octetii, terminatorul, completarea 0xEC/0x11), corectia Reed-Solomon
# pe GF(256) (polinomul 0x11D) pe fiecare bloc, intreteserea blocurilor, asezarea in matrice (tiparele de gasire, de
# aliniere, de sincronizare, modulul inchis, informatia de format si de versiune), apoi masca cu penalizarea cea mai
# mica dintre cele opt.

# (cuvinte de corectie pe bloc, [(blocuri, cuvinte de date pe bloc), ...]) pentru nivelul M, versiunile 1-10
_BLOCURI_M = {
	1: (10, [(1, 16)]),
	2: (16, [(1, 28)]),
	3: (26, [(1, 44)]),
	4: (18, [(2, 32)]),
	5: (24, [(2, 43)]),
	6: (16, [(4, 27)]),
	7: (18, [(4, 31)]),
	8: (22, [(2, 38), (2, 39)]),
	9: (22, [(3, 36), (2, 37)]),
	10: (26, [(4, 43), (1, 44)]),
}

_ALINIERE = {
	1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34],
	7: [6, 22, 38], 8: [6, 24, 42], 9: [6, 26, 46], 10: [6, 28, 50],
}

# biti ramasi dupa cuvinte, pe versiune
_REST = {1: 0, 2: 7, 3: 7, 4: 7, 5: 7, 6: 7, 7: 0, 8: 0, 9: 0, 10: 0}

_NIVEL_M = 0  # bitii nivelului de corectie in informatia de format (L=1, M=0, Q=3, H=2)

VERSIUNE_MAXIMA = 10

# ---------------------------------------------------------------- GF(256)

_EXP = [0] * 512
_LOG = [0] * 256
_x = 1
for _i in range(255):
	_EXP[_i] = _x
	_LOG[_x] = _i
	_x <<= 1
	if _x & 0x100:
		_x ^= 0x11D
for _i in range(255, 512):
	_EXP[_i] = _EXP[_i - 255]
del _x, _i


def _inmulteste(a, b):
	if a == 0 or b == 0:
		return 0
	return _EXP[_LOG[a] + _LOG[b]]


def _generator(grad):
	"""Coeficientii polinomului generator (x - a^0)(x - a^1)...(x - a^(grad-1)), fara cel dominant."""
	g = [1]
	for i in range(grad):
		nou = [0] * (len(g) + 1)
		for j, c in enumerate(g):
			nou[j] ^= c
			nou[j + 1] ^= _inmulteste(c, _EXP[i])
		g = nou
	return g[1:]


def corectie(date, grad):
	"""Cuvintele de corectie Reed-Solomon pentru un bloc."""
	g = _generator(grad)
	rest = [0] * grad
	for octet in date:
		factor = octet ^ rest[0]
		rest = rest[1:] + [0]
		if factor:
			for i in range(grad):
				rest[i] ^= _inmulteste(g[i], factor)
	return rest


# ---------------------------------------------------------------- datele

def _capacitate(versiune):
	grad, grupe = _BLOCURI_M[versiune]
	return sum(n * k for n, k in grupe)


def _biti_lungime(versiune):
	return 8 if versiune < 10 else 16


def versiunea_pentru(octeti):
	"""Cea mai mica versiune in care incap `octeti` octeti, sau None."""
	for v in range(1, VERSIUNE_MAXIMA + 1):
		if 4 + _biti_lungime(v) + 8 * octeti <= 8 * _capacitate(v):
			return v
	return None


def _cuvinte_date(date, versiune):
	biti = []

	def pune(valoare, lungime):
		for i in range(lungime - 1, -1, -1):
			biti.append((valoare >> i) & 1)

	pune(0x4, 4)
	pune(len(date), _biti_lungime(versiune))
	for o in date:
		pune(o, 8)
	capacitate = 8 * _capacitate(versiune)
	pune(0, min(4, capacitate - len(biti)))
	while len(biti) % 8:
		biti.append(0)
	cuvinte = [int("".join(str(b) for b in biti[i:i + 8]), 2) for i in range(0, len(biti), 8)]
	umplere = (0xEC, 0x11)
	i = 0
	while len(cuvinte) < _capacitate(versiune):
		cuvinte.append(umplere[i % 2])
		i += 1
	return cuvinte


def _intretese(cuvinte, versiune):
	grad, grupe = _BLOCURI_M[versiune]
	blocuri = []
	poz = 0
	for n, k in grupe:
		for _b in range(n):
			bloc = cuvinte[poz:poz + k]
			poz += k
			blocuri.append((bloc, corectie(bloc, grad)))
	rez = []
	for i in range(max(len(b[0]) for b in blocuri)):
		for b in blocuri:
			if i < len(b[0]):
				rez.append(b[0][i])
	for i in range(grad):
		for b in blocuri:
			rez.append(b[1][i])
	return rez


# ---------------------------------------------------------------- matricea

class _Matrice(object):
	def __init__(self, versiune):
		self.versiune = versiune
		self.n = 17 + 4 * versiune
		self.m = [[0] * self.n for _i in range(self.n)]
		self.functie = [[False] * self.n for _i in range(self.n)]

	def pune(self, x, y, inchis):
		self.m[y][x] = 1 if inchis else 0
		self.functie[y][x] = True

	def tipare(self):
		n = self.n
		for i in range(n):
			self.pune(6, i, i % 2 == 0)
			self.pune(i, 6, i % 2 == 0)
		for cx, cy in ((3, 3), (n - 4, 3), (3, n - 4)):
			for dy in range(-4, 5):
				for dx in range(-4, 5):
					x, y = cx + dx, cy + dy
					if 0 <= x < n and 0 <= y < n:
						d = max(abs(dx), abs(dy))
						self.pune(x, y, d != 2 and d != 4)
		poz = _ALINIERE[self.versiune]
		for i, cx in enumerate(poz):
			for j, cy in enumerate(poz):
				if (i == 0 and j == 0) or (i == 0 and j == len(poz) - 1) or (i == len(poz) - 1 and j == 0):
					continue
				for dy in range(-2, 3):
					for dx in range(-2, 3):
						self.pune(cx + dx, cy + dy, max(abs(dx), abs(dy)) != 1)
		self.format(0)  # locurile rezervate; valorile adevarate dupa alegerea mastii
		self.versiunea()

	def format(self, masca):
		n = self.n
		date = (_NIVEL_M << 3) | masca
		rest = date
		for _i in range(10):
			rest = (rest << 1) ^ ((rest >> 9) * 0x537)
		biti = ((date << 10) | rest) ^ 0x5412

		def b(i):
			return (biti >> i) & 1

		for i in range(6):
			self.pune(8, i, b(i))
		self.pune(8, 7, b(6))
		self.pune(8, 8, b(7))
		self.pune(7, 8, b(8))
		for i in range(9, 15):
			self.pune(14 - i, 8, b(i))
		for i in range(8):
			self.pune(n - 1 - i, 8, b(i))
		for i in range(8, 15):
			self.pune(8, n - 15 + i, b(i))
		self.pune(8, n - 8, True)  # modulul mereu inchis

	def versiunea(self):
		if self.versiune < 7:
			return
		rest = self.versiune
		for _i in range(12):
			rest = (rest << 1) ^ ((rest >> 11) * 0x1F25)
		biti = (self.versiune << 12) | rest
		for i in range(18):
			bit = (biti >> i) & 1
			a = self.n - 11 + i % 3
			b = i // 3
			self.pune(a, b, bit)
			self.pune(b, a, bit)

	def aseaza(self, cuvinte):
		n = self.n
		i = 0
		total = len(cuvinte) * 8
		dreapta = n - 1
		while dreapta >= 1:
			if dreapta == 6:
				dreapta = 5
			for vert in range(n):
				for j in range(2):
					x = dreapta - j
					sus = ((dreapta + 1) & 2) == 0
					y = n - 1 - vert if sus else vert
					if not self.functie[y][x] and i < total:
						self.m[y][x] = (cuvinte[i >> 3] >> (7 - (i & 7))) & 1
						i += 1
			dreapta -= 2

	def mascheaza(self, masca):
		for y in range(self.n):
			for x in range(self.n):
				if self.functie[y][x]:
					continue
				if masca == 0:
					inv = (x + y) % 2 == 0
				elif masca == 1:
					inv = y % 2 == 0
				elif masca == 2:
					inv = x % 3 == 0
				elif masca == 3:
					inv = (x + y) % 3 == 0
				elif masca == 4:
					inv = (x // 3 + y // 2) % 2 == 0
				elif masca == 5:
					inv = (x * y) % 2 + (x * y) % 3 == 0
				elif masca == 6:
					inv = ((x * y) % 2 + (x * y) % 3) % 2 == 0
				else:
					inv = ((x + y) % 2 + (x * y) % 3) % 2 == 0
				if inv:
					self.m[y][x] ^= 1

	def penalizare(self):
		n = self.n
		m = self.m
		p = 0
		linii = [m[y] for y in range(n)] + [[m[y][x] for y in range(n)] for x in range(n)]
		tipar1 = [1, 0, 1, 1, 1, 0, 1, 0, 0, 0, 0]
		tipar2 = tipar1[::-1]
		for linie in linii:
			lung = 1
			for i in range(1, n):
				if linie[i] == linie[i - 1]:
					lung += 1
				else:
					if lung >= 5:
						p += lung - 2
					lung = 1
			if lung >= 5:
				p += lung - 2
			for i in range(n - 10):
				bucata = linie[i:i + 11]
				if bucata == tipar1 or bucata == tipar2:
					p += 40
		for y in range(n - 1):
			for x in range(n - 1):
				c = m[y][x]
				if c == m[y][x + 1] == m[y + 1][x] == m[y + 1][x + 1]:
					p += 3
		inchise = sum(sum(r) for r in m)
		procent = inchise * 100.0 / (n * n)
		p += int(abs(procent - 50) // 5) * 10
		return p


def matrice(text):
	"""Matricea codului QR pentru `text` (str sau bytes); ValueError daca nu incape in versiunea 10."""
	date = text.encode("utf-8") if not isinstance(text, bytes) else text
	versiune = versiunea_pentru(len(date))
	if versiune is None:
		raise ValueError("textul are %d octeti, prea lung pentru codul QR" % len(date))
	cuvinte = _intretese(_cuvinte_date(date, versiune), versiune)
	cea_mai_buna = None
	for masca in range(8):
		q = _Matrice(versiune)
		q.tipare()
		q.aseaza(cuvinte)
		q.mascheaza(masca)
		q.format(masca)
		p = q.penalizare()
		if cea_mai_buna is None or p < cea_mai_buna[0]:
			cea_mai_buna = (p, q)
	return [list(r) for r in cea_mai_buna[1].m]


def deseneaza(canvas, text, latime, inaltime, inchis=0x00000000, deschis=0x00FFFFFF, margine=4):
	"""Deseneaza codul pe un CanvasSource de latime x inaltime: fundal deschis, patrate intregi, centrat, cu marginea
	alba ceruta de standard (`margine` module). Intoarce marimea unui modul in pixeli (0 daca nu incape)."""
	m = matrice(text)
	n = len(m)
	pas = min(latime, inaltime) // (n + 2 * margine)
	canvas.clear()
	canvas.fill(0, 0, latime, inaltime, deschis)
	if pas <= 0:
		return 0
	x0 = (latime - pas * n) // 2
	y0 = (inaltime - pas * n) // 2
	for y in range(n):
		x = 0
		while x < n:
			if m[y][x]:
				inceput = x
				while x < n and m[y][x]:
					x += 1
				canvas.fill(x0 + inceput * pas, y0 + y * pas, (x - inceput) * pas, pas, inchis)
			else:
				x += 1
	return pas
