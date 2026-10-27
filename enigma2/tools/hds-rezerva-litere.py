#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# hds-rezerva-litere.py (pe PC, cu Pillow): face tabelul de litere al imaginii de rezerva (tools/hds-rezerva-ecran.py)
# din data/fonts/DejaVuSansMono-Bold.ttf, care e deja in imagine (licenta: data/fonts/DejaVuSansMono-Bold.license).
# Pe receptor python3 nu are FreeType si nici Pillow, deci literele vin desenate: o celula de LATIME x INALTIME pixeli
# pe litera, 2 biti pe pixel (4 trepte de acoperire, pentru margini netede), 4 pixeli pe octet, rand dupa rand.
# Setul: ASCII, Latin-1, Latin Extended-A, S si T cu virgula (romana), chirilica de baza (rusa) si semnele tipografice
# folosite in texte (ghilimelele de jos si de sus, linia de pauza scurta, apostroful, punctele de suspensie). Asa se
# pot scrie toate cele 13 limbi ale interfetei.
# Iesirea: blocul dintre semnele "# LITERE-INCEPUT" si "# LITERE-SFARSIT" din tools/hds-rezerva-ecran.py e inlocuit
# (zlib + base64, randuri de 116 semne). Rulare: py -3 tools/hds-rezerva-litere.py [--verifica]
# --verifica: nu scrie nimic, iese cu 1 daca blocul din fisier nu e cel facut acum.

import base64
import os
import sys
import zlib

from PIL import Image, ImageDraw, ImageFont

AICI = os.path.dirname(os.path.abspath(__file__))
FONT = os.path.join(AICI, "..", "data", "fonts", "DejaVuSansMono-Bold.ttf")
TINTA = os.path.join(AICI, "hds-rezerva-ecran.py")

MARIME = 30
LATIME = 18
INALTIME = 36

INTERVALE = [
	(0x0020, 0x007E),
	(0x00A0, 0x00FF),
	(0x0100, 0x017F),
	(0x0218, 0x021B),
	(0x0400, 0x045F),
	(0x2013, 0x2014),
	(0x2018, 0x201E),
	(0x2026, 0x2026),
]

INCEPUT = "# LITERE-INCEPUT"
SFARSIT = "# LITERE-SFARSIT"


def puncte():
	for a, b in INTERVALE:
		for p in range(a, b + 1):
			yield p


def deseneaza():
	font = ImageFont.truetype(FONT, MARIME)
	urcare, coborare = font.getmetrics()
	sus = (INALTIME - (urcare + coborare)) // 2
	date = bytearray()
	lista = []
	for p in puncte():
		c = chr(p)
		img = Image.new("L", (LATIME, INALTIME), 0)
		d = ImageDraw.Draw(img)
		lat = font.getlength(c)
		x = (LATIME - lat) / 2.0
		d.text((x, sus), c, font=font, fill=255)
		px = img.load()
		for y in range(INALTIME):
			octet = 0
			for xx in range(LATIME):
				v = px[xx, y]
				t = 0 if v < 40 else (1 if v < 110 else (2 if v < 190 else 3))
				octet |= t << (2 * (xx % 4))
				if xx % 4 == 3:
					date.append(octet)
					octet = 0
			if LATIME % 4:
				date.append(octet)
		lista.append(p)
	return lista, bytes(date)


def bloc():
	lista, date = deseneaza()
	b64 = base64.b64encode(zlib.compress(date, 9)).decode("ascii")
	randuri = [b64[i:i + 116] for i in range(0, len(b64), 116)]
	intervale = ", ".join("(0x%04X, 0x%04X)" % ab for ab in INTERVALE)
	text = [INCEPUT + " (facut de tools/hds-rezerva-litere.py din DejaVuSansMono-Bold.ttf; nu se scrie de mana)",
		"LITERE_LATIME = %d" % LATIME,
		"LITERE_INALTIME = %d" % INALTIME,
		"LITERE_INTERVALE = [%s]" % intervale,
		"LITERE_DATE = (",
	]
	text += ['\t"%s"' % r for r in randuri]
	text += [")", SFARSIT]
	return "\n".join(text) + "\n", len(lista), len(date)


def main():
	verifica = "--verifica" in sys.argv[1:]
	nou, n, marime = bloc()
	s = open(TINTA, encoding="utf-8", newline="").read()
	i = s.index(INCEPUT)
	j = s.index(SFARSIT, i) + len(SFARSIT) + 1
	vechi = s[i:j]
	if verifica:
		if vechi != nou:
			print("tabelul de litere din %s nu e cel facut acum" % TINTA)
			return 1
		print("tabelul de litere e la zi (%d litere, %d octeti)" % (n, marime))
		return 0
	s = s[:i] + nou + s[j:]
	open(TINTA + ".nou", "w", encoding="utf-8", newline="\n").write(s)
	os.replace(TINTA + ".nou", TINTA)
	print("scris: %d litere, %d octeti necomprimati" % (n, marime))
	return 0


if __name__ == "__main__":
	sys.exit(main())
