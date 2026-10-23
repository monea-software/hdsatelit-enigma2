# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# subdl.py: sursa SubDL, prin API-ul lor oficial (https://api.subdl.com/api/v1/subtitles; fisierele de pe
# https://dl.subdl.com). Conditiile lor cer ca fiecare om sa-si aduca propria cheie (o cheie gratuita nu se imparte intre
# oameni) si interzic cererea parolei contului SubDL: in setari se scrie numai cheia API din panoul contului. Cautarea
# dupa titlu (si an, sezon, episod); la un film de pe un canal TV (tv.py) intai dupa imdb_id (cu "tt") sau tmdb_id
# (parametrii din cercetare; documentatia lor nu s-a putut citi de pe PC, deci neprobat cu raspunsul lor adevarat);
# fps-ul din campul fps (sau framerate, cand e numar). Descarcarea da o arhiva zip. Cheia merge in adresa cererii (asa
# cere API-ul), deci adresa nu se scrie niciodata in jurnal.

from .. import retea
from .. import limbi as LB
from . import EroareSursa, imdbBun, fpsDin

ID = "subdl"
NUME = "SubDL"
ADRESA = "https://subdl.com"
BAZA = "https://api.subdl.com/api/v1/subtitles"
DESCARCARE = "https://dl.subdl.com"
MAX_REZULTATE = 30


def _t(text):
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _cheie(conturi):
	return (conturi or {}).get("subdl_cheie", "")


def configurat(conturi):
	return bool(_cheie(conturi))


def _limbi(limbi):
	return ",".join(sorted(set(LB.DOUA[c].upper() for c in (limbi or ()) if c in LB.DOUA)))


def _cere(parametri, conturi):
	p = dict(parametri)
	p["api_key"] = _cheie(conturi)
	cod, antete, corp = retea.cerere("GET", BAZA, {"Accept": "application/json"}, p)
	d = retea.json_din(corp) or {}
	if cod in (401, 403) or d.get("error") == "not_authorized":
		raise EroareSursa(_t("SubDL nu primește cheia API. Verifică-o în setări."))
	if cod == 429:
		raise EroareSursa(_t("Prea multe cereri către SubDL. Încearcă mai târziu."))
	if cod != 200:
		raise EroareSursa(_t("SubDL nu răspunde cum trebuie (cod %d).") % cod)
	return d


def cauta(film, limbi, conturi, amprenta=None):
	if not configurat(conturi):
		raise EroareSursa(_t("Pentru SubDL scrie în setări cheia ta API (din panoul contului SubDL)."))
	imdb = imdbBun(film.get("imdb"))
	tmdb = (u"%s" % (film.get("tmdb") or u"")).strip()
	if imdb or tmdb.isdigit():
		# filmul de pe un canal TV: dupa ID (imdb_id cu "tt", tmdb_id numarul), apoi dupa titlu daca nu e nimic
		parametri = {"languages": _limbi(limbi), "subs_per_page": MAX_REZULTATE, "type": "movie"}
		if imdb:
			parametri["imdb_id"] = imdb
		else:
			parametri["tmdb_id"] = tmdb
		rez = _rezultate(_cere(parametri, conturi))
		if rez:
			return rez
	parametri = {"film_name": film.get("titlu") or film.get("release") or "", "languages": _limbi(limbi),
		"subs_per_page": MAX_REZULTATE, "year": film.get("an") or None}
	if film.get("sezon") is not None:
		parametri.update({"type": "tv", "season_number": film["sezon"], "episode_number": film.get("episod")})
	else:
		parametri["type"] = "movie"
	return _rezultate(_cere(parametri, conturi))


def _rezultate(d):
	if d.get("status") is False:
		return []
	rez = []
	for x in (d.get("subtitles") or [])[:MAX_REZULTATE]:
		if not x.get("url"):
			continue
		rez.append({"sursa": ID, "id": str(x["url"]), "limba": LB.canonic(x.get("language") or x.get("lang")) or "und",
			"nume": x.get("release_name") or x.get("name") or "", "descarcari": None, "potrivire": False,
			"surzi": bool(x.get("hi")), "detalii": (x.get("author") or "")[:80],
			"fps": fpsDin(x.get("fps")) or fpsDin(x.get("framerate"))})
	return rez


def descarca(rezultat, conturi):
	url = rezultat["id"]
	if not url.startswith("/"):
		raise EroareSursa(_t("SubDL a dat o adresă de fișier neașteptată."))
	cod, antete, corp = retea.cerere("GET", DESCARCARE + url, {"Accept": "*/*"})
	if cod != 200 or not corp:
		raise EroareSursa(_t("Fișierul nu s-a putut aduce de la SubDL (cod %d).") % cod)
	return corp, url.rsplit("/", 1)[-1] or "subdl.zip", ""


def verifica(conturi):
	_cere({"film_name": "test", "subs_per_page": 1}, conturi)
	return _t("Cheia SubDL merge.")
