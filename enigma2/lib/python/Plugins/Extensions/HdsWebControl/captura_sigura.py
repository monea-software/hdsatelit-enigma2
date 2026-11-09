# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# captura_sigura.py: bariera tuturor ecranelor cu secrete si paza decodorului pentru capturile straine.
# Citirea cadrului din decodor (grab fara optiune sau cu -v) loveste driverul video; cat decodorul nu e gata
# (interfata abia pornita, canalul abia schimbat, standby,
# niciun canal TV) captura se face numai cu afisajul OSD (grab -o), iar una cu imaginea canalului se face cel mult o
# data la INTERVAL_VIDEO_S: cererile dese (telecomanda straina cere o captura dupa fiecare tasta) primesc ultima poza,
# daca e mai noua de PASTRARE_S.
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
MESAJ_ASOCIERE = "Captura nu este disponibilă acum. Închide fereastra codului de asociere de pe televizor și reîncearcă."


def epocaCapturii():
	try:
		from Screens.HdsCodAsociere import stareCaptura
		from Components.HdsAsistentaControl import stareCapturaWeb
		epoca, deschis = stareCaptura()
		epoca_web, secret = stareCapturaWeb()
		if (type(epoca) is int and epoca >= 0 and deschis is False
				and type(epoca_web) is int and epoca_web >= 0 and secret is False):
			return epoca + epoca_web
	except Exception:
		pass
	return None


def capturaValida(epoca):
	return type(epoca) is int and epoca >= 0 and epoca == epocaCapturii()


def mesajRefuz():
	try:
		from Components.HdsAsistentaControl import mesajEcranSecret
		return mesajEcranSecret()
	except ImportError:
		try:
			return _("Captura nu este disponibilă acum. Starea ecranului se verifică.")
		except NameError:
			return "Captura nu este disponibilă acum. Starea ecranului se verifică."


def cartusSecret(request):
	"""Mesaj in panou; descarcarea refuzata primeste eroarea, fara un fisier SVG."""
	if request.args.get(b"download", [b""])[0] == b"1":
		import json
		request.setResponseCode(409)
		request.setHeader(b"content-type", b"application/json; charset=utf-8")
		request.setHeader(b"cache-control", b"no-store, private")
		return json.dumps({"result": False, "message": mesajRefuz()}).encode("utf-8")
	from html import escape
	request.setResponseCode(200)
	request.setHeader(b"content-type", b"image/svg+xml; charset=utf-8")
	request.setHeader(b"cache-control", b"no-store, private")
	request.setHeader(b"x-content-type-options", b"nosniff")
	request.setHeader(b"x-hds-captura", b"ecran-privat")
	return ('<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720">'
		'<rect width="1280" height="720" fill="#101828"/>'
		'<text x="640" y="360" text-anchor="middle" fill="white" font-family="sans-serif" font-size="24">%s</text>'
		'</svg>' % escape(mesajRefuz())).encode("utf-8")



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
	"""o singura data, la prima captura straina: ora fiecarui canal pornit (evenimentul evStart al navigatiei). Ora
	canalului pornit inainte nu se stie: se socoteste acum (prima captura cu imaginea canalului dupa PAUZA_ZAP_S)."""
	if _STARE["ascult"]:
		return
	try:
		import NavigationInstance
		nav = NavigationInstance.instance
		if nav is not None:
			nav.event.append(_laEveniment)
			_STARE["ascult"] = True
			if _STARE["zap"] is None:
				_STARE["zap"] = time.monotonic()
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
	if not capturaValida(cheie[0]):
		_STARE["pastrata"] = None
		return
	_STARE["pastrata"] = (cheie, date, tip, time.monotonic() if acum is None else acum)


def dinPastrare(cheie, acum=None):
	"""(date, tip) ale ultimei capturi cu imaginea canalului cu aceiasi parametri, mai noua de PASTRARE_S, sau None"""
	p = _STARE["pastrata"]
	if not capturaValida(cheie[0]):
		_STARE["pastrata"] = None
		return None
	acum = time.monotonic() if acum is None else acum
	if p is None or p[0] != cheie or not (0 <= acum - p[3] <= PASTRARE_S):
		return None
	return p[1], p[2]
