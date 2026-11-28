# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsDvbIDate: ce a aflat DVB-I la ultima reincarcare, intr-un fisier mic, citit de lista de canale, de bara de
# informatii, de trecerea pe internet si de pagina web, fara sa se citeasca listele mari (pana la 4 MB) pe firul enigma2.
#
#   CALE_STARE      scris de pluginul DVB-I (Plugins/SystemPlugins/HdsDvbI/plugin.py) dupa fiecare reincarcare:
#                   {"ora", "liste": [{"adresa", "nume", "ok", "tv", "radio", "regiuni": [...], "lungi"}],
#                    "canale": [{"id", "nume", "url", "tip", "lcn", "nr", "lista", "sat"}],
#                    "legaturi": {cheie satelit: {"nume", "url", "id"}}}
#                   "sat" e cheia de legare (SID:TSID:ONID:NS, Components/HdsDvbILegare.cheie) cand canalul e si pe
#                   satelit; "nr" e locul din buchetul DVB-I (numarul vazut in lista, in ordinea LCN).
#                   EPG2 (0.7.7): canalele care n-au trecut incercarea din casa raman aici cu "ascuns" (starea) si
#                   "nr" None (nu sunt in buchet); "scoase": {"clip": n, "proba": n} = adresele din liste care nu sunt
#                   canale (clipuri, imagini de proba), care nu intra nici in buchet, nici aici.
#   CALE_INCERCARI  scris de incercarea fluxurilor din casa (Components/HdsDvbIIncercare): {url: [stare, cod, ora, fel]}
#                   (DRM1, 0.8.0: fel = FEL_INCERCARE; imaginile de dinainte scriau numai [stare, cod, ora]).
#                   Dupa adresa, nu dupa id: o reincarcare nu pierde ce s-a aflat.
#
# Citirile tin minte fisierul dupa data si marime (un os.stat pe apel); fara fisier, totul e gol. Fisierul nu importa
# nimic din enigma2 la incarcare: probele de pe PC il folosesc ca atare.
from __future__ import absolute_import, unicode_literals

import json
import os
import time

def N_(text):
	"""Marcaj pentru xgettext (--keyword=N_), fara efect: textul se traduce la folosire."""
	return text


# textul din bara de pe televizor in locul semnalului (Components/Converter/HdsInfo.py ViaInternetText; acel dosar nu e
# citit de xgettext, deci textul sta aici)
T_PRIN_INTERNET = N_("prin internet")

CALE_STARE = "/etc/enigma2/hdsdvbi-stare.json"
CALE_INCERCARI = "/etc/enigma2/hdsdvbi-incercari.json"
MAX_INCERCARI = 2000

_CACHE = {}


def _citesteJson(cale, gol):
	try:
		st = os.stat(cale)
		semn = (st.st_mtime_ns, st.st_size, st.st_ino)
	except OSError:
		_CACHE.pop(cale, None)
		return gol
	vechi = _CACHE.get(cale)
	if vechi is not None and vechi[0] == semn:
		return vechi[1]
	try:
		with open(cale, encoding="utf-8") as f:
			date = json.load(f)
		if not isinstance(date, type(gol)):
			raise ValueError("forma")
	except (IOError, OSError, ValueError):
		date = gol
	_CACHE[cale] = (semn, date)
	return date


def scrieJson(cale, date):
	"""prin .nou si redenumire. -> True daca s-a scris"""
	nou = cale + ".nou"
	try:
		with open(nou, "w", encoding="utf-8") as f:
			json.dump(date, f)
		os.replace(nou, cale)
		_CACHE.pop(cale, None)
		return True
	except (IOError, OSError, TypeError, ValueError) as eroare:
		print("[HdsDvbIDate] scrierea %s: %s" % (cale, eroare))
		try:
			os.unlink(nou)
		except OSError:
			pass
		return False


# ------------------------------------------------------------------ starea listelor
def stare(cale=None):
	return _citesteJson(cale or CALE_STARE, {})


def canale(cale=None):
	return list(stare(cale).get("canale") or [])


def canal(id_canal, cale=None):
	for c in canale(cale):
		if c.get("id") == id_canal:
			return c
	return None


def legaturi(cale=None):
	return stare(cale).get("legaturi") or {}


def _cheieRef(ref):
	"""cheia de legare dintr-o referinta de serviciu ('1:0:19:283D:3FB:1:C00000:0:0:0:'), fara partea de jos a
	spatiului de nume; None pentru alte referinte"""
	p = (ref or "").split(":")
	if len(p) < 7 or p[0] != "1":
		return None
	try:
		sid, tsid, onid, ns = (int(x, 16) for x in p[3:7])
	except ValueError:
		return None
	return "%X:%X:%X:%X" % (sid, tsid, onid, ns & 0xFFFF0000)


def legaturaRef(ref, cale=None):
	"""{"nume", "url", "id"} pentru canalul de satelit care are si varianta de internet, altfel None"""
	cale = cale or CALE_STARE
	leg = legaturi(cale)
	if not leg:
		return None
	cheie = _cheieRef(ref if isinstance(ref, str) else _text(ref))
	return leg.get(cheie) if cheie else None


def areInternet(ref, cale=None):
	return legaturaRef(ref, cale) is not None


def urlDinRef(ref):
	"""adresa fluxului dintr-o referinta 4097 ('4097:0:1:A9DA:0:0:0:0:0:0:https%3a//...:Nume'), decodata ca la
	scrierea buchetului (%3a, %20, %25); "" pentru alte referinte"""
	p = (ref if isinstance(ref, str) else _text(ref)).split(":")
	if len(p) < 11 or p[0] != "4097":
		return ""
	return p[10].replace("%3a", ":").replace("%3A", ":").replace("%20", " ").replace("%25", "%")


_INDEX = {"lista": None, "dupa_url": {}}


def canalUrl(url, cale=None):
	"""canalul DVB-I cu adresa data (din starea de acum), sau None; indexul dupa adresa se reface numai cand se schimba
	starea (lista de canale si pagina web intreaba pentru fiecare rand)"""
	if not url:
		return None
	lista = stare(cale).get("canale") or []
	if _INDEX["lista"] is not lista:
		_INDEX["dupa_url"] = dict((c.get("url"), c) for c in lista)
		_INDEX["lista"] = lista
	return _INDEX["dupa_url"].get(url)


# DVI2 (0.8.0, Eduard 26.11.2026 17:34): canalele oprite pentru tara omului raman in lista (se pot porni cu VPN-ul), cu
# eticheta "merge doar în <țara>" cand lista lor e a altei tari decat cea aleasa ("tara" la canal, scris de pluginul
# DVB-I); altfel eticheta veche, "oprit în țara ta"
T_DOAR_IN = N_("merge doar în %s")


def doarIn(url, cale=None, stare=None):
	"""DVI2: numele tarii (tradus) pentru eticheta "merge doar în <țara>" a unui canal oprit pentru tara omului, sau ""
	(alta stare, tara listei necunoscuta sau chiar tara aleasa). stare: starea incercarii, cand cel care cheama o are deja
	(lista de canale: o citire de fisier mai putin pe rand)"""
	if (stare if stare is not None else stareUrl(url)[0]) != "oprit_tara":
		return ""
	c = canalUrl(url, cale)
	tara = (c or {}).get("tara") or ""
	if not tara:
		return ""
	try:
		from Components.HdsDvbISetari import numeTara
		return numeTara(tara)
	except Exception:
		return tara


def esteDvbI(ref, cale=None):
	"""True cand referinta e un canal DVB-I redat prin internet (din buchetul DVB-I sau din trecerea pe internet)"""
	return canalUrl(urlDinRef(ref), cale) is not None


def areDvbI(ref, cale=None):
	"""True pentru canalul de satelit care are si varianta de internet si pentru canalul DVB-I insusi (eticheta DVB-I
	din bara si din lista)"""
	return legaturaRef(ref, cale) is not None or esteDvbI(ref, cale)


def refuriCuInternet(cale=None):
	"""cheile tuturor canalelor de satelit legate (pentru semnul din lista de canale)"""
	return set(legaturi(cale))


def _text(ref):
	try:
		return ref.toString()
	except Exception:
		return str(ref or "")


# ------------------------------------------------------------------ incercarile din casa
def incercari(cale=None):
	return _citesteJson(cale or CALE_INCERCARI, {})


def stareUrl(url, cale=None):
	"""(stare, cod, ora) pentru adresa fluxului; ("", 0, 0) cand n-a fost incercata"""
	v = incercari(cale).get(url)
	if isinstance(v, list) and len(v) >= 3:
		return v[0], v[1], v[2]
	return "", 0, 0


# DRM1: al patrulea camp al unei incercari = felul ei; FEL_INCERCARE: incercarea care se uita si in manifest dupa DRM.
# O incercare cu trei campuri e scrisa de o imagine de dinainte (0.7.9 si mai vechi): "merge" al ei nu stie de DRM.
FEL_INCERCARE = 2


def incercareVeche(url, cale=None):
	"""True cand adresa are o incercare scrisa inainte ca incercarea sa se uite dupa DRM (trei campuri)"""
	v = incercari(cale).get(url)
	return isinstance(v, list) and len(v) == 3


STARE_DRM = "drm"   # Components/HdsDvbIIncercare.DRM (aici fara import: lista de canale si playerul intreaba des)


def protejatDrm(url, cale=None):
	"""DRM1: True cand incercarea din casa a gasit fluxul canalului DVB-I criptat cu DRM (playerul spune atunci
	"Canal protejat (DRM)" si nu-l mai porneste din nou). url poate veni din calea unei referinte (cu %3a)."""
	if not url:
		return False
	try:
		inc = incercari(cale)
		for u in _formeUrl(url):
			v = inc.get(u)
			if isinstance(v, list) and len(v) >= 3:
				return v[0] == STARE_DRM
		return False
	except Exception:
		return False


def _formeUrl(url):
	"""adresa asa cum e data, apoi decodata ca la scrierea buchetului (%3a, %20, %25: urlDinRef), apoi decodata intreaga
	(calea unei referinte poate veni decodata de nucleu); fara repetari"""
	forme = [url, url.replace("%3a", ":").replace("%3A", ":").replace("%20", " ").replace("%25", "%")]
	try:
		from urllib.parse import unquote
	except ImportError:  # Python 2
		from urllib import unquote
	forme.append(unquote(url))
	rez = []
	for f in forme:
		if f not in rez:
			rez.append(f)
	return rez


def noteazaIncercari(rezultate, cale=None, acum=None):
	"""rezultate = {url: (stare, cod)}; le scrie peste cele vechi (celelalte adrese raman). -> True daca s-a scris"""
	cale = cale or CALE_INCERCARI
	acum = int(time.time() if acum is None else acum)
	d = dict(incercari(cale))
	for url, (st, cod) in rezultate.items():
		d[url] = [st, int(cod), acum, FEL_INCERCARE]
	if len(d) > MAX_INCERCARI:
		# cele mai vechi pleaca
		for url in sorted(d, key=lambda u: d[u][2])[:len(d) - MAX_INCERCARI]:
			d.pop(url, None)
	return scrieJson(cale, d)


def ascunse(cale=None):
	"""EPG2: {stare: cate} pentru canalele ascunse din buchet la ultima scriere (n-au trecut incercarea din casa)"""
	n = {}
	for c in canale(cale):
		st = c.get("ascuns") or ""
		if st:
			n[st] = n.get(st, 0) + 1
	return n


def scoase(cale=None):
	"""EPG2: {fel: cate} pentru adresele scoase din liste la ultima descarcare (clipuri, imagini de proba)"""
	v = stare(cale).get("scoase")
	return dict((k, int(x)) for k, x in v.items()) if isinstance(v, dict) else {}


def rezumat(cale_stare=None, cale_incercari=None):
	"""{stare: cate} pentru canalele de acum ale listei ("" = neincercat)"""
	n = {}
	for c in canale(cale_stare):
		st = stareUrl(c.get("url", ""), cale_incercari)[0]
		n[st] = n.get(st, 0) + 1
	return n
