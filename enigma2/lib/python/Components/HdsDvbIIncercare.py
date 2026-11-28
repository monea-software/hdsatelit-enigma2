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
#
# DRM1 (0.8.0, asistenta 327835, AS229, SF8008 Italia): 29 din 33 de canale ale listei grecesti AnixeTV
# (spark3.smart-tv-data.com) sunt DASH criptate (ContentProtection cenc + Widevine + PlayReady in manifest); serverul
# raspunde 206, dar GStreamer n-are decriptor (stream-error domain=1761 code=1), deci ele intrau in buchet ca bune.
# Acum inceputul manifestului se citeste: un MPD cu ContentProtection (orice schema: urn:mpeg:dash:mp4protection:2011
# "cenc" singur inseamna tot continut criptat, cheia vine numai printr-un sistem DRM) sau o lista HLS cu
# EXT-X-KEY / EXT-X-SESSION-KEY METHOD=SAMPLE-AES(-CTR) si KEYFORMAT de DRM (Widevine, PlayReady, FairPlay, urn:uuid:)
# da starea DRM, ascunsa din buchet ca celelalte stari care nu merg (canalul ramane in starea DVB-I si in pagina web,
# cu motivul). AES-128 (HLS cu cheie simpla) merge cu GStreamer: ramane MERGE. Ce nu se poate citi ramane MERGE.
# O lista HLS principala (numai EXT-X-STREAM-INF) nu are de obicei cheia: lista media nu se mai cere (TODO).
from __future__ import absolute_import, unicode_literals

import re

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
DRM = "drm"    # DRM1: fluxul raspunde, dar e criptat cu DRM (receptorul n-are decriptor)

# 403 si 451 = refuzat pentru adresa de unde vine cererea (blocarea pe tara); 401 cere cont, deci tot "nu de aici"
CODURI_TARA = (401, 403, 451)
CODURI_MOARTA = (404, 410)
# starile care tin canalul afara din buchet (EPG2). DVI2 (0.8.0, Eduard 26.11.2026 17:34-17:36, "nu ascunzi nimic"):
# "oprit pentru tara" NU mai ascunde canalul, fiindca omul il poate porni cu VPN-ul; ramane in buchet cu eticheta lui
# ("oprit în țara ta" sau "merge doar în <țara listei>": Components/ServiceList, pagina web). La fel DRM: canalul ramane,
# cu eticheta "protejat (DRM)" si mesajul de la pornire (DRM1, HdsFilmRedare "Canal protejat (DRM)"); licenta lor e
# PlayReady (DRM2), deci se vor putea reda mai tarziu.
STARI_ASCUNSE = (ADRESA_MOARTA, NU_RASPUNDE)
# adresele care nu sunt canale (EPG2)
CLIP = "clip"
PROBA = "proba"
# inceputul unui manifest (DRM1: 16 KB, ca ContentProtection sa fie prins si dupa un antet lung); fluxul nu se descarca
CITITI = 16384

# DRM1: un element ContentProtection (cu sau fara prefix de spatiu de nume) intr-un MPD
_MPD = re.compile(r"<(?:[A-Za-z_][\w.-]*:)?MPD[\s>]")
_PROTECTIE_DASH = re.compile(r"<(?:[A-Za-z_][\w.-]*:)?ContentProtection[\s/>]")
# HLS: cheile cu SAMPLE-AES (FairPlay, Widevine, PlayReady); AES-128 e cheie simpla, pe care GStreamer o descifreaza
_CHEIE_HLS = re.compile(r"^#EXT-X-(?:SESSION-)?KEY:(.*)$", re.M)
_METODA = re.compile(r"(?:^|,)\s*METHOD\s*=\s*\"?([A-Za-z0-9-]+)", re.I)
_FORMAT_CHEIE = re.compile(r"(?:^|,)\s*KEYFORMAT\s*=\s*\"([^\"]*)\"", re.I)
FORMATE_DRM_HLS = ("com.widevine", "com.microsoft.playready", "com.apple.streamingkeydelivery", "urn:uuid:")


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


def _text(octeti):
	if isinstance(octeti, bytes):
		return octeti.decode("utf-8", "replace")
	return octeti or ""


def protejat(octeti):
	"""DRM1: True cand inceputul fluxului spune DRM: un MPD cu ContentProtection sau o lista HLS cu o cheie SAMPLE-AES /
	SAMPLE-AES-CTR si KEYFORMAT de DRM (FORMATE_DRM_HLS). Orice altceva (alt fel de raspuns, AES-128, cheia simpla
	"identity", textul necitit): False, adica fluxul ramane cum spune codul HTTP."""
	try:
		text = _text(octeti)
	except Exception:
		return False
	inceput = text.lstrip(u"﻿ \t\r\n")
	if _MPD.search(text):
		return _PROTECTIE_DASH.search(text) is not None
	if inceput.startswith("#EXTM3U"):
		for m in _CHEIE_HLS.finditer(text):
			atribute = m.group(1)
			metoda = _METODA.search(atribute)
			if metoda is None or not metoda.group(1).upper().startswith("SAMPLE-AES"):
				continue
			fmt = _FORMAT_CHEIE.search(atribute)
			fmt = (fmt.group(1) if fmt else "").strip().lower()
			if fmt.startswith(FORMATE_DRM_HLS):
				return True
	return False


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
			inceput = r.read(CITITI)
		finally:
			r.close()
		stare = stareDinCod(cod)
		if stare == MERGE and protejat(inceput):
			return DRM, cod
		return stare, cod
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
