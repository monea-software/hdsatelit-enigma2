# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# subsro.py: sursa subs.ro, prin API-ul lor oficial v1.0 (https://api.subs.ro/v1.0, antetul X-Subs-Api-Key).
# Fiecare om isi face cheia in profilul lui de pe subs.ro (au o cota zilnica pe cheie) si o scrie in setari; o singura
# cheie, a omului (nu se trece la alta cheie cand se termina cota). Cautarea: intai dupa numele fisierului („release”),
# apoi dupa titlu; la un film de pe un canal TV (tv.py) intai dupa ID-ul IMDb (/search/imdbid/tt..., cu "tt", ca in
# exemplul din https://subs.ro/api) sau TMDb. Raspunsul nu are fps. Descarcarea da o arhiva (zip), din care se ia
# subtitrarea (salvare.py). Nimic din cheie nu ajunge in jurnal.

from .. import retea
from .. import limbi as LB
from . import EroareSursa, imdbBun

ID = "subsro"
NUME = "subs.ro"
ADRESA = "https://subs.ro"
BAZA = "https://api.subs.ro/v1.0"
MAX_REZULTATE = 40
# limbile din API-ul lor (parametrul language)
LIMBI = {"ron": "ro", "eng": "en", "ita": "ita", "fra": "fra", "deu": "ger", "hun": "ung", "ell": "gre", "por": "por",
	"spa": "spa"}
DIN_LIMBI = dict((v, k) for k, v in LIMBI.items())


def _t(text):
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _cheie(conturi):
	return (conturi or {}).get("subsro_cheie", "")


def configurat(conturi):
	return bool(_cheie(conturi))


def _antete(conturi):
	return {"X-Subs-Api-Key": _cheie(conturi), "Accept": "application/json"}


def _eroare(cod, corp=None):
	mesaj = ((retea.json_din(corp) or {}).get("message") or "").lower() if corp else ""
	if cod == 401 or "api key" in mesaj:
		return EroareSursa(_t("subs.ro nu primește cheia API. Verifică-o în setări."))
	if cod == 403:
		return EroareSursa(_t("subs.ro: cota zilnică a cheii s-a terminat sau accesul e oprit."))
	if cod == 429:
		return EroareSursa(_t("Prea multe cereri către subs.ro. Încearcă mai târziu."))
	return EroareSursa(_t("subs.ro nu răspunde cum trebuie (cod %d).") % cod)


def _cautaDupa(camp, valoare, limba, conturi):
	try:
		from urllib.parse import quote
	except ImportError:
		quote = None
	adresa = "%s/search/%s/%s" % (BAZA, camp, quote(valoare, safe=""))
	cod, antete, corp = retea.cerere("GET", adresa, _antete(conturi), {"language": limba})
	if cod == 404:
		return []
	if cod != 200:
		raise _eroare(cod, corp)
	d = retea.json_din(corp) or {}
	return d.get("items") or []


def cauta(film, limbi, conturi, amprenta=None):
	if not configurat(conturi):
		raise EroareSursa(_t("Pentru subs.ro scrie în setări cheia ta API (din profilul de pe subs.ro)."))
	rez = []
	vazute = set()
	for limba in limbi or ("ron",):
		cod = LIMBI.get(limba)
		if not cod:
			continue
		elemente = []
		imdb = imdbBun(film.get("imdb"))
		tmdb = (u"%s" % (film.get("tmdb") or u"")).strip()
		if imdb:
			# filmul de pe un canal TV: dupa ID-ul IMDb, cu "tt" (/search/imdbid/tt0133093)
			elemente = _cautaDupa("imdbid", imdb, cod, conturi)
		elif tmdb.isdigit():
			elemente = _cautaDupa("tmdbid", tmdb, cod, conturi)
		if not elemente and film.get("release"):
			elemente = _cautaDupa("release", film["release"], cod, conturi)
		if not elemente and film.get("titlu"):
			elemente = _cautaDupa("title", film["titlu"], cod, conturi)
		for x in elemente[:MAX_REZULTATE]:
			if x.get("id") is None or x["id"] in vazute:
				continue
			vazute.add(x["id"])
			rez.append({"sursa": ID, "id": str(x["id"]), "limba": DIN_LIMBI.get(x.get("language"), LB.canonic(x.get("language")) or limba),
				"nume": x.get("title") or "", "descarcari": None, "potrivire": False, "surzi": False,
				"detalii": " ".join(str(v) for v in (x.get("year"), x.get("translator"), x.get("description")) if v)[:200],
				"fps": None})
	return rez


def descarca(rezultat, conturi):
	if not configurat(conturi):
		raise EroareSursa(_t("Pentru subs.ro scrie în setări cheia ta API (din profilul de pe subs.ro)."))
	cod, antete, corp = retea.cerere("GET", "%s/subtitle/%s/download" % (BAZA, int(rezultat["id"])), _antete(conturi))
	if cod != 200 or not corp:
		raise _eroare(cod, corp)
	return corp, "subsro-%s.zip" % rezultat["id"], ""


def verifica(conturi):
	cod, antete, corp = retea.cerere("GET", BAZA + "/quota", _antete(conturi))
	if cod != 200:
		raise _eroare(cod, corp)
	q = (retea.json_din(corp) or {}).get("quota") or {}
	return _t("Cheia subs.ro merge. Cererile rămase azi: %s din %s.") % (q.get("remaining_quota", "?"), q.get("total_quota", "?"))
