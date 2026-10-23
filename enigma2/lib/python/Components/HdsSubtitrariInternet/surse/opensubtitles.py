# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# opensubtitles.py: sursa OpenSubtitles.com, prin API-ul lor oficial REST v1 (https://api.opensubtitles.com/api/v1).
#
# Regulile lor, respectate aici:
# - o singura cheie de aplicatie („Api-Key”), a HD Satelit; utilizatorul NU pune o cheie a lui. Cheia nu e in cod: vine
#   din setarile descarcarii (conturi, criptat) sau din fisierul FISIER_CHEIE pus de imagine; fara ea sursa nu cauta;
# - fiecare om cu contul lui (nume de utilizator, nu adresa de e-mail, si parola); descarcarea cere contul (20 pe zi cu
#   un cont gratuit, 1000 cu VIP; contorul se reface la miezul noptii UTC);
# - User-Agent „HDSatelit vX.Y”; cel mult 5 cereri pe secunda (retea.py); parametrii in ordine alfabetica;
# - login rar: jetonul se tine DURATA_JETON_S (20 de ore, ei il dau pentru 24) in FISIER_JETON (/tmp, 0600, se sterge la
#   repornire); dupa un 401 la login nu se mai incearca cu aceleasi date (limitele lor de login);
# - legatura de descarcare expira in 3 ore: nu se tine, se foloseste pe loc;
# - pe planul gratuit ei pot pune o reclama la inceputul sau sfarsitul subtitrarii (se spune in setari).
# Cautarea: la un film din fisier dupa titlu, an si amprenta; la un film de pe un canal TV (tv.py) dupa imdb_id (numarul
# fara "tt") sau tmdb_id, apoi dupa titlu si an daca nu e nimic. In rezultate: fps-ul copiei (pentru viteza pe TV) si
# semnul subtitrarilor traduse automat (ai_translated, machine_translated), puse la coada listei.
# Nimic din jetoane, parole sau chei nu ajunge in jurnal.

import hashlib
import json
import os
import time

from .. import retea
from .. import limbi as LB
from . import EroareSursa, imdbBun, fpsDin

ID = "opensubtitles"
NUME = "OpenSubtitles.com"
ADRESA = "https://www.opensubtitles.com"
BAZA = "https://api.opensubtitles.com/api/v1"
FISIER_CHEIE = "/usr/share/hdsatelit/opensubtitles-aplicatie.key"
FISIER_JETON = "/tmp/hds-opensubtitles-jeton.json"
DURATA_JETON_S = 20 * 3600
MAX_REZULTATE = 60

_NEREUSITE = set()     # amprentele (sha256) datelor de login respinse cu 401: nu se mai incearca


def _t(text):
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def cheieAplicatie(conturi):
	cheie = (conturi or {}).get("os_cheie_aplicatie", "")
	if cheie:
		return cheie
	try:
		with open(FISIER_CHEIE, "r") as f:
			return f.read(256).strip()
	except (OSError, IOError):
		return ""


def configurat(conturi):
	return bool(cheieAplicatie(conturi))


def _antete(conturi, jeton=None):
	a = {"Api-Key": cheieAplicatie(conturi), "Accept": "application/json"}
	if jeton:
		a["Authorization"] = "Bearer %s" % jeton
	return a


def _amprentaCont(conturi):
	text = "%s\n%s" % ((conturi or {}).get("os_utilizator", ""), (conturi or {}).get("os_parola", ""))
	return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _citesteJeton(conturi, ceas=time.time):
	try:
		with open(FISIER_JETON, "r") as f:
			d = json.load(f)
		if d.get("cont") == _amprentaCont(conturi) and ceas() - float(d.get("t", 0)) < DURATA_JETON_S and d.get("jeton"):
			return d["jeton"], d.get("baza") or BAZA
	except (OSError, IOError, ValueError, TypeError, AttributeError):
		pass
	return None, None


def _scrieJeton(conturi, jeton, baza, ceas=time.time):
	try:
		fd = os.open(FISIER_JETON + ".nou", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
		with os.fdopen(fd, "w") as f:
			json.dump({"cont": _amprentaCont(conturi), "jeton": jeton, "baza": baza, "t": ceas()}, f)
		os.replace(FISIER_JETON + ".nou", FISIER_JETON)
	except (OSError, IOError):
		pass


def uitaJetonul():
	"""La schimbarea sau stergerea contului: jetonul vechi nu mai e bun."""
	try:
		os.unlink(FISIER_JETON)
	except OSError:
		pass
	_NEREUSITE.clear()


def autentifica(conturi):
	"""-> (jeton, adresa de baza) sau ridica EroareSursa. Refoloseste jetonul tinut minte."""
	if not configurat(conturi):
		raise EroareSursa(_t("Cheia aplicației OpenSubtitles lipsește; o pune HD Satelit."))
	utilizator = (conturi or {}).get("os_utilizator", "")
	parola = (conturi or {}).get("os_parola", "")
	if not utilizator or not parola:
		raise EroareSursa(_t("Pentru descărcări de pe OpenSubtitles scrie în setări contul tău (gratuit)."))
	jeton, baza = _citesteJeton(conturi)
	if jeton:
		return jeton, baza
	amprenta = _amprentaCont(conturi)
	if amprenta in _NEREUSITE:
		raise EroareSursa(_t("OpenSubtitles nu a primit numele sau parola. Verifică-le în setări (numele de utilizator, nu adresa de e-mail)."))
	cod, antete, corp = retea.cerere("POST", BAZA + "/login", _antete(conturi), corp_json={"username": utilizator,
		"password": parola})
	d = retea.json_din(corp) or {}
	if cod in (400, 401):
		_NEREUSITE.add(amprenta)
		raise EroareSursa(_t("OpenSubtitles nu a primit numele sau parola. Verifică-le în setări (numele de utilizator, nu adresa de e-mail)."))
	if cod == 429:
		raise EroareSursa(_t("OpenSubtitles cere o pauză între autentificări. Încearcă peste un minut."))
	if cod != 200 or not d.get("token"):
		raise EroareSursa(_t("OpenSubtitles nu răspunde cum trebuie (cod %d).") % cod)
	baza = d.get("base_url") or ""
	baza = ("https://%s/api/v1" % baza) if baza and "/" not in baza else BAZA
	_scrieJeton(conturi, d["token"], baza)
	return d["token"], baza


def _limbiOs(limbi):
	coduri = []
	for c in limbi or ():
		d = LB.DOUA.get(c)
		if d == "pt":
			d = "pt-pt"
		if d and d not in coduri:
			coduri.append(d)
	return sorted(coduri)


def cauta(film, limbi, conturi, amprenta=None):
	if not configurat(conturi):
		raise EroareSursa(_t("Cheia aplicației OpenSubtitles lipsește; o pune HD Satelit."))
	imdb = imdbBun(film.get("imdb"))
	tmdb = (u"%s" % (film.get("tmdb") or u"")).strip()
	if imdb or tmdb.isdigit():
		# filmul de pe un canal TV: dupa ID (imdb_id e numarul fara "tt"), apoi dupa titlu daca nu e nimic
		parametri = {"languages": ",".join(_limbiOs(limbi))}
		if imdb:
			parametri["imdb_id"] = int(imdb[2:])
		else:
			parametri["tmdb_id"] = int(tmdb)
		rez = _cauta(parametri, conturi)
		if rez:
			return rez
	parametri = {"languages": ",".join(_limbiOs(limbi)), "query": (film.get("titlu") or "").lower(),
		"year": film.get("an") or None, "moviehash": amprenta or None}
	if film.get("sezon") is not None:
		parametri["season_number"] = film["sezon"]
		parametri["episode_number"] = film.get("episod")
	return _cauta(parametri, conturi)


def _cauta(parametri, conturi):
	cod, antete, corp = retea.cerere("GET", BAZA + "/subtitles", _antete(conturi), parametri)
	if cod == 401 or cod == 403:
		raise EroareSursa(_t("OpenSubtitles nu primește cheia aplicației (cod %d).") % cod)
	if cod == 429:
		raise EroareSursa(_t("Prea multe cereri către OpenSubtitles. Încearcă peste câteva secunde."))
	if cod != 200:
		raise EroareSursa(_t("OpenSubtitles nu răspunde cum trebuie (cod %d).") % cod)
	d = retea.json_din(corp) or {}
	rez = []
	for x in (d.get("data") or [])[:MAX_REZULTATE]:
		a = x.get("attributes") or {}
		fisiere = a.get("files") or []
		if not fisiere or not fisiere[0].get("file_id"):
			continue
		detalii = a.get("feature_details") or {}
		rez.append({"sursa": ID, "id": str(fisiere[0]["file_id"]), "limba": LB.canonic(a.get("language")) or "und",
			"nume": a.get("release") or fisiere[0].get("file_name") or detalii.get("title") or "",
			"descarcari": a.get("download_count"), "potrivire": bool(a.get("moviehash_match")),
			"surzi": bool(a.get("hearing_impaired")),
			"detalii": " ".join(str(v) for v in (detalii.get("title"), detalii.get("year")) if v),
			"fisier": fisiere[0].get("file_name") or "", "fps": fpsDin(a.get("fps")),
			"automata": bool(a.get("ai_translated") or a.get("machine_translated"))})
	return rez


def descarca(rezultat, conturi):
	jeton, baza = autentifica(conturi)
	cod, antete, corp = retea.cerere("POST", baza + "/download", _antete(conturi, jeton),
		corp_json={"file_id": int(rezultat["id"])})
	d = retea.json_din(corp) or {}
	if cod == 401:
		uitaJetonul()
		raise EroareSursa(_t("Autentificarea la OpenSubtitles a expirat. Încearcă din nou."))
	if cod == 406 or (cod == 200 and not d.get("link") and d.get("remaining") == 0):
		raise EroareSursa(_t("Ai ajuns la numărul de descărcări pe azi la OpenSubtitles (se reface la %s).") %
			(d.get("reset_time_utc") or d.get("reset_time") or _t("miezul nopții UTC")))
	if cod == 429:
		raise EroareSursa(_t("Prea multe cereri către OpenSubtitles. Încearcă peste câteva secunde."))
	if cod != 200 or not d.get("link"):
		raise EroareSursa(_t("OpenSubtitles nu a dat fișierul (cod %d).") % cod)
	cod2, antete2, octeti = retea.cerere("GET", d["link"], {"Accept": "*/*"})
	if cod2 != 200 or not octeti:
		raise EroareSursa(_t("Fișierul nu s-a putut aduce de la OpenSubtitles (cod %d).") % cod2)
	mesaj = ""
	if d.get("remaining") is not None:
		mesaj = _t("Descărcări rămase azi la OpenSubtitles: %s.") % d["remaining"]
	return octeti, d.get("file_name") or rezultat.get("fisier") or "subtitrare.srt", mesaj


def verifica(conturi):
	"""Autentificarea si contorul de descarcari (pentru „Verifică”)."""
	jeton, baza = autentifica(conturi)
	cod, antete, corp = retea.cerere("GET", baza + "/infos/user", _antete(conturi, jeton))
	d = (retea.json_din(corp) or {}).get("data") or {}
	if cod != 200:
		return _t("Contul OpenSubtitles merge.")
	nivel = _t("VIP") if d.get("vip") else _t("gratuit")
	return _t("Contul OpenSubtitles merge (%s). Descărcări rămase azi: %s din %s.") % (nivel,
		d.get("remaining_downloads", "?"), d.get("allowed_downloads", "?"))


def iesire(conturi):
	"""/logout la schimbarea contului (jetonul vechi nu mai trebuie)."""
	jeton, baza = _citesteJeton(conturi)
	if jeton:
		try:
			retea.cerere("DELETE", baza + "/logout", _antete(conturi, jeton))
		except retea.EroareRetea:
			pass
	uitaJetonul()
