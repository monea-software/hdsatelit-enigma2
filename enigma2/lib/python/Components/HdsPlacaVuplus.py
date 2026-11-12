# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
# HdsPlacaVuplus.py: ocolisurile de hardware ale placii Vu+ Duo 4K Lite (BCM7252S, aceeasi placa cu GigaBlue UHD Quad
# 4K Pro, driverele platform-util), luate ca idee din imaginea producatorului si scrise aici:
# - lista modurilor video din driver (videomode_choices) e gresita: folosim lista fixa a placii (MODURI_DUO4KLITE);
# - un mod video nou nu se aplica la prima scriere: dupa o secunda se scrie un mod diferit, iar dupa inca una modul
#   ales (Components/VideoOutput.py, VideoOutput.writeMode).
# Placa se recunoaste dupa /proc/stb/info/vumodel, scris la pornire de vuplus-ddbootup: „vuduo4klite” (stratul
# OE-Alliance) sau „duo4klite” (imaginea producatorului). Fara aparat de proba: de confirmat de un tester.
import os

NUME_DUO4KLITE = ("vuduo4klite", "duo4klite")
MODURI_DUO4KLITE = ("480p", "480i", "576p", "576i", "720p50", "720p", "1080i50", "1080i", "1080p50", "1080p",
	"2160p50", "2160p")
PAUZA_MS = 1000


def _citeste(cale):
	try:
		with open(cale, "r", encoding="ascii", errors="replace") as f:
			return f.read(64).strip().lower()
	except OSError:
		return ""


def caleInfo(radacinaVideo):
	"""dosarul /proc/stb/info langa /proc/stb/video (radacinaVideo se termina cu /proc/stb/video/; probele dau alt dosar)"""
	return os.path.join(os.path.dirname(os.path.normpath(radacinaVideo)), "info")


def esteDuo4kLite(dosarInfo="/proc/stb/info"):
	return _citeste(os.path.join(dosarInfo, "vumodel")) in NUME_DUO4KLITE


def modIntermediar(mod):
	"""un mod SD diferit de cel ales, scris inainte de el ca driverul sa vada o schimbare"""
	return "480p" if (mod or "").startswith("576") else "576p"
