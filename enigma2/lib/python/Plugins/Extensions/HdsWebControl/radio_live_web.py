# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Radio online in playerul listei de canale: identificarea referintei este pura;
# numai rezolva(), chemata pe un fir separat, poate cere datele pluginului RadioOnline.
# Fluxul merge direct de la post la browser. Navigatia si tunerul nu sunt atinse.

import re
import threading
from urllib.parse import unquote, urlsplit

_HEX = re.compile(r"^[0-9a-fA-F]{1,8}\Z")
_NUMERIC = re.compile(r"^[0-9]{1,5}\Z")
_SCHEMA = re.compile(r"^https?(?::|%3a)//", re.I)
_UUID = re.compile(r"^/radio/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\Z")
_TIPURI = (1, 4097, 5001, 5002, 5003, 8193, 8739)


def _t(text):
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _text(value, maxim=160):
	if not isinstance(value, str):
		return ""
	value = re.sub(r"<[^>]*>", " ", value)
	return " ".join("".join(c if 32 <= ord(c) < 127 or ord(c) >= 160 else " " for c in value).split())[:maxim]


def _url(value):
	"""Numai HTTP(S), fara autentificare, spatii ori caractere de control."""
	if not isinstance(value, str) or not 0 < len(value) <= 4096:
		return None
	if any(c.isspace() or ord(c) < 32 or ord(c) == 127 or 0xD800 <= ord(c) <= 0xDFFF for c in value) or "\\" in value:
		return None
	try:
		p = urlsplit(value)
		if p.scheme.lower() not in ("http", "https") or not p.hostname or "%" in p.hostname:
			return None
		if p.username is not None or p.password is not None or (p.port is not None and not 0 < p.port < 65536):
			return None
	except ValueError:
		return None
	return p


def _referinta(ref):
	if not isinstance(ref, str) or not 0 < len(ref) <= 8192 or any(ord(c) < 32 or ord(c) == 127 for c in ref):
		return None
	f = ref.split(":", 10)
	if len(f) != 11 or not _NUMERIC.match(f[0]) or int(f[0]) not in _TIPURI or any(not _HEX.match(v) for v in f[1:10]):
		return None
	if int(f[1], 16) != 0 or int(f[2], 16) not in (2, 10):
		return None
	cale = f[10]
	m = _SCHEMA.match(cale)
	if m is None:
		return None
	# Numele este campul de dupa URL. Colonul schemei si portul pot fi si
	# necodificate in referinte introduse manual; restul separatorilor sunt %3a.
	inceput_cale = cale.find("/", m.end())
	if inceput_cale < 0:
		inceput_cale = len(cale)
	separator = cale.find(":", inceput_cale)
	nume = ""
	if separator >= 0:
		nume = _text(unquote(cale[separator + 1:]))
		cale = cale[:separator]
	adresa = unquote(cale)
	p = _url(adresa)
	if p is None:
		return None
	uuid = None
	if p.hostname.lower() in ("127.0.0.1", "localhost", "::1"):
		# Adresa receptorului nu poate fi redata in browserul altui calculator.
		# Singura exceptie recunoscuta se rezolva prin provider, fara GET local.
		m = _UUID.match(p.path)
		if p.hostname.lower() not in ("127.0.0.1", "localhost") or p.port != 8895 or m is None or p.query or p.fragment:
			return None
		uuid = m.group(1)
	return {"ref": ref, "url": adresa, "nume": nume, "id": uuid}


def online_ref(ref):
	"""Referinta audio HTTP(S), fara acces la fisiere, provider, retea sau enigma2."""
	return _referinta(ref) is not None


def _eroare(text):
	return {"result": False, "radio": True, "online": True, "message": text}


def rezolva(ref, furnizor=None):
	"""Datele postului pentru /api/tv-radio. NUMAI pe worker; providerul poate iesi pe retea.

	Argumentul optional furnizor este post_dupa_id in probele de pe PC.
	Erorile nu contin referinta, adresa sau exceptia providerului.
	"""
	if threading.current_thread() is threading.main_thread():
		return _eroare(_t("Datele postului nu se pot citi acum."))
	r = _referinta(ref)
	if r is None:
		return _eroare(_t("Alege un post de radio online din lista de canale."))
	post = {}
	if r["id"] is not None:
		try:
			if furnizor is None:
				from Plugins.Extensions.RadioOnline.adrese import post_dupa_id
				furnizor = post_dupa_id
			post = furnizor(r["id"])
		except Exception:
			return _eroare(_t("Adresa postului de radio nu se poate afla acum."))
		if not isinstance(post, dict):
			return _eroare(_t("Adresa postului de radio nu se poate afla acum."))
	adresa = post.get("url") if r["id"] is not None else r["url"]
	p = _url(adresa)
	if p is None or p.hostname.lower() in ("127.0.0.1", "localhost", "::1"):
		return _eroare(_t("Adresa postului de radio nu poate fi redată în browser."))
	nume = _text(post.get("nume")) or r["nume"] or _t("Radio online")
	codec = _text(post.get("codec"), 24)
	try:
		kbps = max(0, min(int(post.get("kbps") or 0), 9999))
	except (TypeError, ValueError):
		kbps = 0
	tara = _text(post.get("tara"), 60)
	etichete = post.get("etichete")
	etichete = [_text(e, 40) for e in etichete[:4]] if isinstance(etichete, (tuple, list)) else []
	detalii = ", ".join(v for v in [tara] + etichete if v)
	sunet = ", ".join(v for v in (codec, ("%d kbit/s" % kbps) if kbps else "") if v)
	try:
		from .radio_web import _numeSigla
		sigla = _numeSigla(ref)
	except Exception:
		sigla = None
	date = {"ref": ref, "radio": True, "online": True, "nume": nume, "furnizor": tara,
		"numar": 0, "epg": None, "rds": {}, "receptie": {}, "semnal": {},
		"sunet": {"codec": codec, "debit": kbps}, "analiza": {}, "acces": None}
	texte = {"nume": nume, "detalii": detalii, "sunet": sunet, "transponder": "",
		"satelit": _t("Online"), "semnal": "", "semnal_slab": False, "ramas": "",
		"acum_ora": "", "urmatoare": [], "epg_lipsa": _t("Postul nu transmite programul emisiunilor."),
		"bare": "", "bare_detaliu": ""}
	return {"result": True, "radio": True, "online": True, "ref": ref, "nume": nume,
		"radio_url": adresa, "radio_date": {"date": date, "texte": texte, "sigla": sigla}}
