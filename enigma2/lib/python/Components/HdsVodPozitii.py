# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Filme si seriale: unde ai ramas (pe film si pe episod), ce ai vazut, favoritele si pistele vazute la ultima redare.

Totul sta in memorie; pe flash (/etc/enigma2/hds_vod.json) se scrie numai cand se schimba ceva si cel mult o data la
SCRIE_LA_S in timpul redarii, plus la oprirea filmului. Un fisier mic, cu plafon (MAX_POZITII, MAX_FAVORITE).
Cheia unui titlu: „<sursa>/<cheie>” (cheie = v<id>.<ext> la film, e<id>.<ext> la episod, s<id> la serial).
"""
import json
import os
import threading
import time

CALE = "/etc/enigma2/hds_vod.json"
SCRIE_LA_S = 300
MAX_POZITII = 300
MAX_FAVORITE = 500
MIN_POZITIE_S = 60              # sub un minut nu e „continua”
VAZUT_PROCENT = 0.94            # dupa atat (sau cu mai putin de VAZUT_REST_S ramase) filmul e vazut
VAZUT_REST_S = 240
_lacat = threading.Lock()
_date = None
_schimbat = False
_scris = time.monotonic()        # prima scriere fara „forteaza” vine abia dupa SCRIE_LA_S (nu la pornirea fiecarui film)


def _gol():
	return {"v": 1, "poz": {}, "fav": {}}


def _curat(d):
	if not isinstance(d, dict):
		return _gol()
	rez = _gol()
	for camp in ("poz", "fav"):
		v = d.get(camp)
		if isinstance(v, dict):
			rez[camp] = dict((str(k)[:120], x) for k, x in v.items() if isinstance(x, dict))
	return rez


def _incarca():
	global _date
	if _date is None:
		try:
			with open(CALE, encoding="utf-8") as f:
				_date = _curat(json.load(f))
		except (IOError, OSError, ValueError):
			_date = _gol()
	return _date


def cheie(sursa_id, cheie_titlu):
	return "%s/%s" % (sursa_id, cheie_titlu)


def _meta(meta):
	"""Ce se tine despre titlu ca sa apara in „Continuă să vizionezi” fara retea."""
	meta = meta or {}
	rez = {}
	for k, maxim in (("nume", 200), ("poza", 1024), ("fundal", 1024), ("tip", 10), ("serial", 20), ("serial_nume", 200), ("sezon", 6), ("numar", 6)):
		v = meta.get(k)
		if isinstance(v, (str, int)) and str(v):
			rez[k] = str(v)[:maxim]
	return rez


def noteaza(k, pozitie_s, durata_s, meta=None, subtitrari=None, audio=None, forteaza=False):
	"""Pozitia de acum (secunde). Scrie pe flash numai la forteaza (oprire) sau dupa SCRIE_LA_S de la ultima scriere."""
	global _schimbat
	from Components.HdsVod import activ
	if not activ("continua"):
		return
	try:
		pozitie_s, durata_s = max(0, int(pozitie_s)), max(0, int(durata_s or 0))
	except (TypeError, ValueError):
		return
	with _lacat:
		d = _incarca()
		vechi = d["poz"].get(k) or {}
		rand = dict(vechi, p=pozitie_s, d=durata_s or vechi.get("d", 0), t=int(time.time()))
		rand.update(_meta(meta))
		if durata_s and (pozitie_s >= durata_s * VAZUT_PROCENT or durata_s - pozitie_s <= VAZUT_REST_S):
			rand["vazut"] = 1
		if subtitrari is not None:
			rand["sub"] = [str(x)[:40] for x in subtitrari][:12]
		if audio is not None:
			rand["aud"] = [str(x)[:40] for x in audio][:12]
		if rand != vechi:
			d["poz"][k] = rand
			_schimbat = True
		if len(d["poz"]) > MAX_POZITII:
			for x in sorted(d["poz"], key=lambda x: d["poz"][x].get("t", 0))[:len(d["poz"]) - MAX_POZITII]:
				del d["poz"][x]
	if forteaza or time.monotonic() - _scris >= SCRIE_LA_S:
		scrie()


def pozitie(k):
	"""Secunda de unde se continua, sau 0 (nou sau vazut pana la capat)."""
	with _lacat:
		r = _incarca()["poz"].get(k) or {}
	p = r.get("p", 0)
	from Components.HdsVod import activ
	if not activ("continua"):
		return 0
	return p if p >= MIN_POZITIE_S and not r.get("vazut") else 0


def stare(k):
	"""{p, d, vazut, sub, aud} sau {}."""
	with _lacat:
		return dict(_incarca()["poz"].get(k) or {})


def progres(k):
	"""0..1 pentru bara de pe poster: 1 = vazut, 0 = neinceput."""
	r = stare(k)
	if r.get("vazut"):
		return 1.0
	if r.get("d") and r.get("p", 0) >= MIN_POZITIE_S:
		return min(1.0, float(r["p"]) / r["d"])
	return 0.0


def continua(sursa_id=None, maxim=30):
	"""Ce ai inceput si n-ai terminat, cel mai recent intai: [(cheie, rand)]. La seriale ramane numai ultimul episod."""
	from Components.HdsVod import activ
	if not activ("continua"):
		return []
	with _lacat:
		poz = dict(_incarca()["poz"])
	rez, seriale = [], set()
	for k, r in sorted(poz.items(), key=lambda x: -x[1].get("t", 0)):
		if sursa_id and not k.startswith(sursa_id + "/"):
			continue
		if r.get("vazut") or r.get("p", 0) < MIN_POZITIE_S:
			continue
		if r.get("serial"):
			if r["serial"] in seriale:
				continue
			seriale.add(r["serial"])
		rez.append((k, r))
		if len(rez) >= maxim:
			break
	return rez


def uita(k):
	global _schimbat
	with _lacat:
		if _incarca()["poz"].pop(k, None) is not None:
			_schimbat = True
	scrie()


def favorit(k):
	with _lacat:
		return k in _incarca()["fav"]


def comutaFavorit(k, meta=None):
	"""Adauga sau scoate; -> True daca acum e favorit. Se scrie imediat (omul a apasat o tasta)."""
	global _schimbat
	with _lacat:
		fav = _incarca()["fav"]
		if k in fav:
			del fav[k]
			acum = False
		else:
			fav[k] = dict(_meta(meta), t=int(time.time()))
			while len(fav) > MAX_FAVORITE:
				del fav[min(fav, key=lambda x: fav[x].get("t", 0))]
			acum = True
		_schimbat = True
	scrie()
	return acum


def favorite(sursa_id=None):
	with _lacat:
		fav = dict(_incarca()["fav"])
	return [(k, r) for k, r in sorted(fav.items(), key=lambda x: -x[1].get("t", 0)) if not sursa_id or k.startswith(sursa_id + "/")]


def scrie():
	global _schimbat, _scris
	with _lacat:
		if not _schimbat or _date is None:
			return
		text = json.dumps(_date, ensure_ascii=False, separators=(",", ":"))
		_schimbat = False
		_scris = time.monotonic()
	try:
		tmp = CALE + ".tmp"
		with open(tmp, "w", encoding="utf-8") as f:
			f.write(text)
		os.replace(tmp, CALE)
	except (IOError, OSError) as e:
		print("[HdsVodPozitii] nu pot scrie:", e)


def _pentruProbe():
	"""Probele de pe PC: memoria de la zero."""
	global _date, _schimbat, _scris
	_date, _schimbat, _scris = None, False, time.monotonic()
