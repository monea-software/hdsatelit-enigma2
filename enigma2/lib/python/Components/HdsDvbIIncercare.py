# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsDvbIIncercare: incearca din casa omului fluxul de internet al unui canal DVB-I si spune ce s-a intamplat, ca
# lista sa poata arata "merge de aici", "oprit pentru tara ta" (atunci VPN-ul ajuta) sau "adresa nu mai exista".
# Se cere numai inceputul fluxului (manifestul DASH sau lista HLS), urmand redirectarile, cu un termen scurt.
# Masurat pe listele germane reale: fara VPN raspund 403 dupa o redirectare 307, cu o adresa de Germania 200;
# o adresa moarta din lista raspunde 404. Fara texte pentru om aici: ecranele aleg mesajul dupa stare.
#
# EPG2 (0.7.7, asistenta 058499): in buchet intra numai canalele care pot merge (pluginul DVB-I). felScos spune dupa
# adresa ce nu e canal deloc: lista "Freeview Australia" din registre da clipuri Vimeo de 30 s - 2 min
# (player.vimeo.com/external/<nr>.mpd, MPD static cu lungime: pornesc, se termina, imaginea sta pe loc), iar mai multe
# liste dau imaginea de proba DASH-IF (livesim.dashif.org). ascunsa spune ce stare a incercarii tine canalul afara din
# buchet pana la urmatoarea incercare reusita; un canal neincercat intra.
from __future__ import absolute_import, unicode_literals

try:
	from urllib.request import Request, urlopen
	from urllib.error import HTTPError, URLError
	from urllib.parse import urlsplit
except ImportError:  # Python 2
	from urllib2 import Request, urlopen, HTTPError, URLError
	from urlparse import urlsplit

MERGE = "merge"
OPRIT_TARA = "oprit_tara"
ADRESA_MOARTA = "adresa_moarta"
NU_RASPUNDE = "nu_raspunde"

# 403 si 451 = refuzat pentru adresa de unde vine cererea (blocarea pe tara); 401 cere cont, deci tot "nu de aici"
CODURI_TARA = (401, 403, 451)
CODURI_MOARTA = (404, 410)
# starile care tin canalul afara din buchet (EPG2)
STARI_ASCUNSE = (OPRIT_TARA, ADRESA_MOARTA, NU_RASPUNDE)
# adresele care nu sunt canale (EPG2)
CLIP = "clip"
PROBA = "proba"
CITITI = 4096  # ajunge pentru inceputul unui manifest; fluxul insusi nu se descarca


def stareDinCod(cod):
	"""starea pentru un cod HTTP final (dupa redirectari)"""
	if 200 <= cod < 300:
		return MERGE
	if cod in CODURI_TARA:
		return OPRIT_TARA
	if cod in CODURI_MOARTA:
		return ADRESA_MOARTA
	return NU_RASPUNDE


def felScos(url):
	"""CLIP (clip cu lungime, nu canal), PROBA (imaginea de proba DASH-IF) sau "" (canal), numai dupa adresa"""
	try:
		parti = urlsplit(url or "")
		gazda = (parti.hostname or "").lower()
	except (ValueError, AttributeError):
		return ""
	cale = parti.path or ""
	if gazda == "player.vimeo.com" and cale.startswith("/external/"):
		return CLIP
	if (gazda == "dashif.org" or gazda.endswith(".dashif.org")) and "livesim" in (gazda + cale).lower():
		return PROBA
	return ""


def ascunsa(stare):
	"""True cand canalul cu starea aceasta a incercarii nu intra in buchet (n-a trecut incercarea din casa)"""
	return stare in STARI_ASCUNSE


def incearca(url, termen=8, deschide=None):
	"""(stare, cod) pentru adresa fluxului; cod 0 cand nu s-a primit niciun raspuns HTTP. 'deschide' inlocuieste
	urlopen in teste. Nu arunca."""
	if not url or not (url.startswith("http://") or url.startswith("https://")):
		return NU_RASPUNDE, 0
	deschide = deschide or urlopen
	try:
		cerere = Request(url, headers={"User-Agent": "HDSatelit", "Range": "bytes=0-%d" % (CITITI - 1)})
		r = deschide(cerere, timeout=termen)
		try:
			cod = int(getattr(r, "status", None) or r.getcode())
			r.read(CITITI)
		finally:
			r.close()
		return stareDinCod(cod), cod
	except HTTPError as e:
		return stareDinCod(int(e.code)), int(e.code)
	except (URLError, IOError, ValueError, OSError):
		return NU_RASPUNDE, 0
	except Exception:
		return NU_RASPUNDE, 0


def incearcaToate(servicii, termen=8, deschide=None, opreste=None):
	"""servicii = [(id, nume, url, fel)] ca din parserul DVB-I; intoarce {id: (stare, cod)}. 'opreste' (functie fara
	argumente) intrerupe sirul intre doua canale, de pilda la iesirea din ecran."""
	rez = {}
	for s in servicii:
		if opreste is not None and opreste():
			break
		rez[s[0]] = incearca(s[2], termen=termen, deschide=deschide)
	return rez


def numara(rezultate):
	"""{stare: cate} pentru un rezumat pe ecran"""
	n = {MERGE: 0, OPRIT_TARA: 0, ADRESA_MOARTA: 0, NU_RASPUNDE: 0}
	for stare, _cod in rezultate.values():
		n[stare] = n.get(stare, 0) + 1
	return n
