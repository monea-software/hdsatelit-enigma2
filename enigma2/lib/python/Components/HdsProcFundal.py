# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsProcFundal.py: citirile din fisierele driverului HiSilicon (/proc/msp/..., /proc/hisi/...) facute pe firul
# principal al interfetei trec printr-un fir de fundal, ca la Components/HdsSunet.py (avplay). Pe Octagon SF8008 o
# citire din /proc/msp a ramas blocata in nucleu si a tinut interfata pe loc pana a oprit-o paznicul.
#
# citeste(functie, cale, *argumente): functia de citire a modulului (aceeasi forma a rezultatului ca pana acum) se
# ruleaza intr-un fir daemon, asteptat cel mult ASTEPTARE_S (o citire buna din /proc ia sub o milisecunda); altfel se
# intoarce ce s-a citit ultima data pentru aceeasi cale si aceleasi argumente (None la inceput = nu se stie). O citire
# care nu se termina in TIMP_S marcheaza driverul "blocat" pana la repornirea interfetei: nu se mai porneste niciun fir
# (altfel s-ar strange fire blocate) si se intoarce numai ce e citit deja. Un singur fir de citire odata.
# Pe alte fire decat cel principal (analiza fluxului, firele web care au deja firul lor) si pentru celelalte fisiere
# citirea ramane directa, ca inainte. Fisierul nu importa nimic din enigma2: probele de pe PC il incarca asa cum e.

import threading
import time

ASTEPTARE_S = 0.2
TIMP_S = 1.0
# partile de cale ale fisierelor driverului (si sub o radacina de proba: <dosar>/proc/msp/...)
DRIVER = ("/proc/msp/", "/proc/hisi/")

_STARE = {"fir": None, "pornit_t": 0.0, "blocat": False, "cale": ""}
_CITITE = {}
_LACAT = threading.Lock()


def _jurnal(text):
	print("[HdsProcFundal] %s" % text)


def eDriver(cale):
	"""True pentru un fisier al driverului (/proc/msp, /proc/hisi), si sub o radacina de proba."""
	try:
		c = str(cale).replace("\\", "/")
	except Exception:
		return False
	return any(d in c for d in DRIVER)


def blocat():
	"""True dupa o citire a driverului care n-a raspuns in TIMP_S (pana la repornirea interfetei)."""
	_verificaFirul()
	return _STARE["blocat"]


def _verificaFirul():
	fir = _STARE["fir"]
	if not _STARE["blocat"] and fir is not None and fir.is_alive() and time.time() - _STARE["pornit_t"] > TIMP_S:
		_STARE["blocat"] = True
		_jurnal("citirea lui %s nu raspunde de %.1f s: nu mai citesc driverul pana la repornirea interfetei"
			% (_STARE["cale"], time.time() - _STARE["pornit_t"]))


def _peFirulPrincipal():
	try:
		return threading.current_thread() is threading.main_thread()
	except AttributeError:
		return isinstance(threading.current_thread(), threading._MainThread)


def _citesteInFir(cheie, functie, argumente):
	t0 = time.time()
	try:
		date = functie(*argumente)
	except Exception:
		date = None
	durata = time.time() - t0
	with _LACAT:
		_CITITE[cheie] = date
	if durata > TIMP_S and not _STARE["blocat"]:
		_STARE["blocat"] = True
		_jurnal("citirea lui %s a durat %.1f s: nu mai citesc driverul pana la repornirea interfetei"
			% (argumente[0] if argumente else "?", durata))


def citeste(functie, cale, *argumente):
	"""Rezultatul lui functie(cale, *argumente): pe firul principal, pentru fisierele driverului, prin firul de
	fundal (asteptat cel mult ASTEPTARE_S, altfel ultimul rezultat stiut); altfel direct."""
	if not eDriver(cale) or not _peFirulPrincipal():
		return functie(cale, *argumente)
	toate = (cale,) + tuple(argumente)
	try:
		cheie = (getattr(functie, "__module__", ""), getattr(functie, "__name__", ""), toate)
		hash(cheie)
	except TypeError:
		cheie = (getattr(functie, "__name__", ""), str(cale))
	_verificaFirul()
	if not _STARE["blocat"]:
		fir = _STARE["fir"]
		if fir is None or not fir.is_alive():
			fir = threading.Thread(target=_citesteInFir, args=(cheie, functie, toate), name="HdsProcFundal")
			fir.daemon = True
			_STARE["fir"], _STARE["pornit_t"], _STARE["cale"] = fir, time.time(), str(cale)
			fir.start()
			fir.join(ASTEPTARE_S)
			_verificaFirul()
	with _LACAT:
		return _CITITE.get(cheie)
