# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# film.py: ce se stie despre filmul care merge, pentru cautarea subtitrarilor: titlul si anul din numele fisierului
# (fara calitate, codec, grupul care l-a scos), sezonul si episodul (S01E02, 1x02), numele „release” (numele fisierului
# fara extensie, dupa care cauta subs.ro) si amprenta OpenSubtitles („moviehash”: marimea plus suma pe 64 de biti a
# primilor si ultimilor 64 KB, citita numai din acele doua bucati, deci merge si pe un film din retea).

import os
import re
import struct

BUCATA = 64 * 1024

# cuvintele de dupa titlu in numele fisierelor: de aici incolo nu mai e titlul
_OPRIRE = re.compile(r"(?i)^(?:\d{3,4}p|2160p|4k|uhd|hdr|hdr10|dv|bluray|blu-ray|bdrip|brrip|dvdrip|dvd|webrip|web-dl|web|"
	r"webdl|hdtv|hdrip|remux|x264|x265|h264|h265|hevc|avc|xvid|divx|aac|ac3|dts|ddp?5\.?1|atmos|proper|repack|"
	r"extended|unrated|limited|internal|multi|dubbed|subbed|ro|rosub|romanian|imax|10bit)$")
_AN = re.compile(r"^(19[2-9]\d|20[0-4]\d)$")
_EPISOD = re.compile(r"(?i)\bS(\d{1,2})[ ._-]?E(\d{1,3})\b|\b(\d{1,2})x(\d{2,3})\b")


def informatii(cale):
	"""-> {"cale", "nume" (fisierul), "release" (numele fara extensie), "titlu", "an" (text sau ""), "sezon", "episod"
	(numere sau None)}."""
	nume = os.path.basename(cale or "")
	release = os.path.splitext(nume)[0]
	text = release
	sezon = episod = None
	m = _EPISOD.search(text)
	if m:
		sezon = int(m.group(1) or m.group(3))
		episod = int(m.group(2) or m.group(4))
		text_titlu = text[:m.start()]
	else:
		text_titlu = text
	cuvinte = [c for c in re.split(r"[\s._\[\]()]+", text_titlu) if c]
	titlu = []
	an = ""
	for c in cuvinte:
		if _AN.match(c) and titlu:
			an = c
			break
		if _OPRIRE.match(c) and titlu:
			break
		titlu.append(c)
	if not an:
		for c in cuvinte[len(titlu):]:
			if _AN.match(c):
				an = c
				break
	titlu_text = u" ".join(titlu).strip(" -") or release
	return {"cale": cale, "nume": nume, "release": release, "titlu": titlu_text, "an": an, "sezon": sezon,
		"episod": episod}


def amprenta(cale):
	"""Amprenta OpenSubtitles a fisierului (16 cifre hexazecimale) si marimea lui; (None, marime) daca fisierul e mai mic
	de 128 KB sau nu se poate citi."""
	try:
		marime = os.path.getsize(cale)
		if marime < 2 * BUCATA:
			return None, marime
		suma = marime
		with open(cale, "rb") as f:
			for pozitie in (0, marime - BUCATA):
				f.seek(pozitie)
				bucata = f.read(BUCATA)
				if len(bucata) < BUCATA:
					return None, marime
				suma += sum(struct.unpack("<%dQ" % (BUCATA // 8), bucata))
		return "%016x" % (suma & 0xFFFFFFFFFFFFFFFF), marime
	except (OSError, IOError, struct.error):
		return None, 0
