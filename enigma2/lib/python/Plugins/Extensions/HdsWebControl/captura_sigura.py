# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# captura_sigura.py: cand intra si imaginea canalului (decodorul video) intr-o captura de ecran ceruta prin
# /api/screenshot si /grab (ScreenshotResource din plugin.py; pluginurile care cer capturi prin interfata noastra trec
# tot pe aici). Citirea cadrului din decodor (grab fara optiune sau cu -v) loveste driverul video; cat decodorul nu e
# gata (interfata abia pornita, canalul abia schimbat, standby, niciun canal TV) captura se face numai cu afisajul OSD
# (grab -o), iar una cu imaginea canalului se face cel mult o data la INTERVAL_VIDEO_S: cererile dese (o pagina care
# reimprospateaza dupa fiecare tasta) primesc ultima poza, daca e mai noua de PASTRARE_S.
# - hotarare(): functie fara efecte, cu toate intrarile date (testata pe PC);
# - decide(): aceeasi, cu starea de acum a receptorului (pornirea interfetei, ultimul canal pornit, standby);
# - tine() si dinPastrare(): ultima captura cu imaginea canalului.
# Nimic nu apare pe televizor.

import os
import time

PAUZA_PORNIRE_S = 120    # dupa pornirea interfetei: decodorul si driverul video isi fac memoria
PAUZA_ZAP_S = 5          # dupa pornirea unui canal: decodorul porneste
INTERVAL_VIDEO_S = 1.5   # cel mult o captura cu imaginea canalului atat de des
PASTRARE_S = 2.0         # cat se mai da ultima poza unei cereri dese
TIPURI_RADIO = ("2", "a", "A")   # tipul serviciului din referinta (al treilea camp, hex): radio



def pornireaProcesului(stat="/proc/self/stat", uptime="/proc/uptime", acum=None, tic=None):
	"""Ceasul monoton de la pornirea procesului enigma2 (interfata), nu de la importul acestui fisier: plugin.py il
	importa la prima captura ceruta, care poate veni si la o ora dupa pornire. Campul 22 din /proc/self/stat
	(starttime, in tacte de la pornirea receptorului) fata de /proc/uptime; fara ele, ora de acum (pauza intreaga)."""
	acum = time.monotonic() if acum is None else acum
	try:
		with open(stat, "rb") as f:
			text = f.read().decode("ascii", "replace")
		campuri = text[text.rindex(")") + 2:].split()   # numele programului poate avea spatii si paranteze
		tic = tic or os.sysconf("SC_CLK_TCK")
		pornit = int(campuri[19]) / float(tic)
		with open(uptime, "rb") as f:
			sus = float(f.read().split()[0])
		varsta = sus - pornit
		if varsta < 0:
			return acum
		return acum - varsta
	except Exception:
		return acum


_STARE = {"pornire": pornireaProcesului(), "zap": None, "ultima_video": 0.0, "pastrata": None, "ascult": False}


def _laEveniment(eveniment):
	try:
		from enigma import iPlayableService
		if eveniment == iPlayableService.evStart:
			_STARE["zap"] = time.monotonic()
	except Exception:
		pass


def asculta():
	"""o singura data: ora fiecarui canal pornit (evenimentul evStart al navigatiei)"""
	if _STARE["ascult"]:
		return
	try:
		import NavigationInstance
		nav = NavigationInstance.instance
		if nav is not None:
			nav.event.append(_laEveniment)
			_STARE["ascult"] = True
	except Exception:
		pass


def stareReceptor():
	"""(standby, canal TV pornit) acum"""
	standby = False
	tv = False
	try:
		import Screens.Standby
		standby = Screens.Standby.inStandby is not None
	except Exception:
		pass
	try:
		import NavigationInstance
		ref = NavigationInstance.instance.getCurrentlyPlayingServiceReference()
		if ref is not None:
			campuri = ref.toString().split(":")
			tv = not (len(campuri) > 2 and campuri[2] in TIPURI_RADIO)
	except Exception:
		pass
	return standby, tv


def hotarare(mod, acum, pornire, zap, standby, tv, ultima_video):
	"""-> (ce, motiv). ce: "da" (grab cum s-a cerut), "osd" (numai afisajul: grab -o), "refuz" (mode=video cand
	imaginea canalului nu se poate lua acum) sau "des" (o captura cu imaginea canalului a fost facuta acum
	INTERVAL_VIDEO_S: se da ultima, daca e, altfel se refuza). motiv: un cuvant ASCII pentru antetul raspunsului."""
	if mod == "osd":
		return "da", ""
	motiv = ""
	if acum - pornire < PAUZA_PORNIRE_S:
		motiv = "pornire"
	elif standby:
		motiv = "standby"
	elif not tv:
		motiv = "fara-tv"
	elif zap is not None and 0 <= acum - zap < PAUZA_ZAP_S:
		motiv = "zap"
	if motiv:
		return ("refuz" if mod == "video" else "osd"), motiv
	if 0 <= acum - ultima_video < INTERVAL_VIDEO_S:
		return "des", "des"
	return "da", ""


def decide(mod, acum=None):
	asculta()
	acum = time.monotonic() if acum is None else acum
	standby, tv = stareReceptor()
	return hotarare(mod, acum, _STARE["pornire"], _STARE["zap"], standby, tv, _STARE["ultima_video"])


def incepeVideo(acum=None):
	"""o captura cu imaginea canalului porneste acum (intervalul se socoteste de aici)"""
	_STARE["ultima_video"] = time.monotonic() if acum is None else acum


def tine(cheie, date, tip, acum=None):
	_STARE["pastrata"] = (cheie, date, tip, time.monotonic() if acum is None else acum)


def dinPastrare(cheie, acum=None):
	"""(date, tip) ale ultimei capturi cu imaginea canalului cu aceiasi parametri, mai noua de PASTRARE_S, sau None"""
	p = _STARE["pastrata"]
	acum = time.monotonic() if acum is None else acum
	if p is None or p[0] != cheie or not (0 <= acum - p[3] <= PASTRARE_S):
		return None
	return p[1], p[2]
