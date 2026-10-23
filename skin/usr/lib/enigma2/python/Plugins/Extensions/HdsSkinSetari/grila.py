# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
# HDS-MARCA: skin HDSatelit, Monea Software pentru HD Satelit, 2026
#
# Alegerea vizuala a unei culori (ecranul HdsAlegeCuloare din ecrane_culoare.py si pagina web /culori-skin): grila de
# nuante (nuanta pe orizontala, lumina pe verticala, prima coloana griurile de la alb la negru), treptele de
# transparenta si banda cu culoarea de acum, culorile puse de mana la alte roluri si culorile paletei.
# Numai calcule, fara enigma2; merge pe Python 2.7 si 3.x.
from . import paleta as P

NUANTE = 16                     # coloanele 1..16: nuantele 0, 22.5, ... 337.5 grade
COLOANE = NUANTE + 1            # coloana 0: griurile
RANDURI = 8
SATURATIE = 0.75
LUMINI = (0.90, 0.80, 0.68, 0.56, 0.45, 0.34, 0.23, 0.12)
GRIURI = (1.0, 0.85, 0.70, 0.55, 0.40, 0.26, 0.13, 0.0)
ALFE = (0, 10, 20, 30, 40, 50, 60, 70, 80, 90)   # transparenta in procente; 0 = opac
BANDA_MAXIM = 15
# rolurile paletei care intra in banda, dupa culorile puse de mana
ROLURI_BANDA = ("hdsBrand", "hdsBrandLight", "hdsAmber", "hdsGood", "hdsWarn", "hdsBad", "hdsText", "hdsText2", "hdsLabel",
	"hdsPanelSolid", "hdsTrack", "hdsCell", "key_red", "key_green", "key_yellow", "key_blue")


def culoare(col, rand):
	"""Culoarea opaca a celulei (col, rand) din grila."""
	col = max(0, min(COLOANE - 1, col))
	rand = max(0, min(RANDURI - 1, rand))
	if col == 0:
		return P.hsl(0, 0.0, GRIURI[rand])
	return P.hsl((col - 1) * 360.0 / NUANTE, SATURATIE, LUMINI[rand])


def rgb(c):
	return int(c) & 0x00FFFFFF


def cea_mai_apropiata(c):
	"""(col, rand) al celulei cu culoarea cea mai apropiata de c (distanta in RGB)."""
	_a, r, g, b = P.parti(rgb(c))
	cel, d_min = (0, 0), None
	for col in range(COLOANE):
		for rand in range(RANDURI):
			_x, r2, g2, b2 = P.parti(culoare(col, rand))
			d = (r - r2) ** 2 + (g - g2) ** 2 + (b - b2) ** 2
			if d_min is None or d < d_min:
				cel, d_min = (col, rand), d
	return cel


def alfa_din_procent(procent):
	return P._rot(max(0, min(100, int(procent))) * 255 / 100.0)


def procent_din_alfa(a):
	return P._rot((int(a) & 255) * 100 / 255.0)


def treapta_alfa(a):
	"""Indexul treptei de transparenta celei mai apropiate de alfa a."""
	p = procent_din_alfa(a)
	return min(range(len(ALFE)), key=lambda i: abs(ALFE[i] - p))


def are_alfa(rol):
	return P.FEL.get(rol) in ("panou", "strat")


def banda(rol, conf, pal, acum):
	"""Culorile benzii (fara alfa, fara dubluri, cel mult BANDA_MAXIM): culoarea de acum a rolului, culorile puse de
	mana la celelalte roluri, apoi culorile principale ale paletei."""
	rez = []

	def pune(c):
		c = rgb(c)
		if c not in rez and len(rez) < BANDA_MAXIM:
			rez.append(c)
	pune(acum)
	for r in P.EDITABILE:
		if r != rol and r in conf.get("roluri", {}):
			pune(conf["roluri"][r])
	for r in ROLURI_BANDA:
		if r in pal:
			pune(pal[r])
	return rez


def compune(c_rgb, a):
	"""Culoarea finala: RGB-ul ales cu alfa a."""
	return P.cu_alfa(rgb(c_rgb), a)


def text_procent(a):
	return "%d%%" % procent_din_alfa(a)


def hex6(c):
	return "#%06X" % rgb(c)
