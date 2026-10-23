# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Sursele de subtitrari ale descarcarii, fiecare un modul separat, cu acelasi API, ca o sursa sa se poata scoate
# repede (se sterge modulul si numele lui din SURSE): numai servicii cu API oficial si cu permisiune pentru aplicatii.
#   ID, NUME, ADRESA              numele pentru ecrane si adresa sitului
#   configurat(conturi) -> bool   are ce ii trebuie ca sa caute
#   cauta(film, limbi, conturi, amprenta) -> [rezultat]
#   descarca(rezultat, conturi) -> (octeti, numele fisierului, mesaj pentru om sau "")
#   verifica(conturi) -> mesaj    starea contului sau a cheii (pentru „Verifică”)
# Un rezultat: {"sursa", "id", "limba" (cod canonic: ron, eng, ...), "nume", "descarcari", "potrivire" (dupa amprenta
# filmului), "surzi", "detalii", "fps" (cadrele pe secunda ale copiei pe care s-a facut subtitrarea, sau None)}, plus ce
# ii trebuie sursei la descarcare.
# Filmul de pe un canal TV (tv.py) vine cu "imdb" (tt0133093) si "tmdb" din Wikidata: sursele cauta intai dupa ID (titlul
# din EPG e tradus, ID-ul nu), apoi, daca nu gasesc nimic, dupa titlu si an.
# O problema pentru om (cheie lipsa, cont gresit, cota terminata) ridica EroareSursa cu textul ei.

import re

SURSE = ("opensubtitles", "subsro", "subdl")


class EroareSursa(Exception):
	"""O problema a unei surse, cu textul pentru om."""


def imdbBun(valoare):
	"""ID-ul IMDb ca "tt0133093", sau "" daca nu are forma buna."""
	v = (u"%s" % (valoare or u"")).strip()
	return v if re.match(r"^tt\d{5,10}$", v) else u""


def fpsDin(valoare):
	"""Cadrele pe secunda date de o sursa ("23.976", 23.976, "25") -> numar intre 10 si 120, sau None."""
	try:
		f = float(u"%s" % valoare)
	except (TypeError, ValueError):
		return None
	return f if 10.0 <= f <= 120.0 else None


def module():
	"""Modulele surselor care exista, in ordinea din SURSE."""
	import importlib
	rez = []
	for nume in SURSE:
		try:
			rez.append(importlib.import_module(__name__ + "." + nume))
		except ImportError as e:
			print("[HdsSubtitrariInternet] sursa %s lipseste: %s" % (nume, e))
	return rez
