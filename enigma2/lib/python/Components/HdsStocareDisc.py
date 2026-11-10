# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Citiri de disc la cerere, cu termen, fara asteptare pe firul interfetei.

Un apel porneste cel mult o citire pentru aceeasi cheie. Culegerea rezultatului
nu reporneste citirea blocata. Firele nu ating obiecte enigma2 si nu aplica
setari. Un apel de sistem blocat nu poate fi oprit din Python; numarul firelor
ramane limitat, iar raspunsul venit dupa termen nu este folosit.
"""

import os
import threading
import time

TERMEN = 2.0
VARSTA = 5.0
MAX_FIRE = 8
MAX_REZULTATE = 128
_zavor = threading.Lock()
_citiri = {}


def _rezultat(citire, acum):
	stare = citire["stare"]
	if stare == "asteapta" and acum >= citire["pana"]:
		stare = citire["stare"] = "termen"
	return {"stare": stare, "valoare": citire.get("valoare"),
		"eroare": citire.get("eroare", "")}


def _citeste(cheie, citire, functie):
	valoare, eroare = None, ""
	try:
		valoare = functie()
	except Exception as exc:
		eroare = str(exc)[:240]
	acum = time.monotonic()
	with _zavor:
		citire["activ"] = False
		citire["sfarsit"] = acum
		if _citiri.get(cheie) is not citire:
			return
		if acum >= citire["pana"] or citire["stare"] == "termen":
			citire["stare"] = "termen"
			return
		citire["valoare"] = valoare
		citire["eroare"] = eroare
		citire["stare"] = "eroare" if eroare else "gata"


def cere(cheie, functie, termen=TERMEN, varsta=VARSTA):
	"""Returneaza imediat {stare, valoare, eroare}; numai functie atinge discul.

	Rezultatele terminate se tin varsta secunde. Nu exista temporizator sau
	prospatare proprie. Un ecran poate culege raspunsul prin acelasi apel.
	"""
	acum = time.monotonic()
	with _zavor:
		citire = _citiri.get(cheie)
		if citire is not None:
			if citire["activ"] or acum - citire["sfarsit"] < max(0.0, varsta):
				return _rezultat(citire, acum)
		if len(_citiri) >= MAX_REZULTATE:
			vechi = sorted(((c["sfarsit"], k) for k, c in _citiri.items() if not c["activ"]), key=lambda x: x[0])
			for _timp, k in vechi[:max(1, len(_citiri) - MAX_REZULTATE + 1)]:
				_citiri.pop(k, None)
		if sum(1 for c in _citiri.values() if c["activ"]) >= MAX_FIRE:
			# Si refuzul are rezultat de cules; ecranul nu asteapta un fir nepornit.
			citire = {"stare": "termen", "activ": False, "pana": acum,
				"sfarsit": acum, "valoare": None, "eroare": ""}
			_citiri[cheie] = citire
			return _rezultat(citire, acum)
		citire = {"stare": "asteapta", "activ": True, "pana": acum + max(0.001, termen),
			"sfarsit": acum, "valoare": None, "eroare": ""}
		_citiri[cheie] = citire
	try:
		fir = threading.Thread(target=_citeste, args=(cheie, citire, functie), daemon=True)
		fir.start()
	except Exception as exc:
		with _zavor:
			citire.update(activ=False, stare="eroare", eroare=str(exc)[:240], sfarsit=time.monotonic())
	with _zavor:
		return _rezultat(citire, time.monotonic())


def stare(cheie):
	"""Culege numai memoria, fara a porni o alta citire."""
	with _zavor:
		citire = _citiri.get(cheie)
		return _rezultat(citire, time.monotonic()) if citire else None


def activ(cheie):
	"""Lucrarea mai ruleaza, chiar daca raspunsul ei a depasit termenul."""
	with _zavor:
		return bool((_citiri.get(cheie) or {}).get("activ"))


def uita(cheie=None):
	"""Uita rezultatele terminate, de exemplu dupa hotplug; nu dubleaza firele blocate."""
	with _zavor:
		for k in list(_citiri):
			if (cheie is None or k == cheie) and not _citiri[k]["activ"]:
				_citiri.pop(k, None)


def statvfs(cale):
	rez = cere(("statvfs", cale), lambda: os.statvfs(cale))
	return rez["valoare"] if rez["stare"] == "gata" else None


def listdir(cale):
	rez = cere(("listdir", cale), lambda: os.listdir(cale))
	return rez["valoare"] if rez["stare"] == "gata" else None
