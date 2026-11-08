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
# care nu se termina in TIMP_S marcheaza driverul "blocat" cat timp firul ei e tot acolo: nu se mai porneste niciun fir
# (altfel s-ar strange fire blocate) si se intoarce numai ce e citit deja. Cand citirea se termina, chiar tarziu, driverul
# nu mai e blocat: o citire lenta o data (la schimbari repezi de canal) nu are voie sa tina pana la repornirea interfetei,
# ca atunci lista imaginilor refuza tot („receptorul nu se poate verifica”). Un singur fir de citire odata.
# Pe alte fire decat cel principal (analiza fluxului, firele web care au deja firul lor) si pentru celelalte fisiere
# citirea ramane directa, ca inainte. Fisierul nu importa nimic din enigma2: probele de pe PC il incarca asa cum e.

import os
import threading
import time

ASTEPTARE_S = 0.2
TIMP_S = 1.0
# partile de cale ale fisierelor driverului (si sub o radacina de proba: <dosar>/proc/msp/...)
DRIVER = ("/proc/msp/", "/proc/hisi/")

# Fisierele din /proc/stb care nu se citesc, o singura lista pentru Python-ul imaginii (Components/HdsHdmiDate.py,
# Components/HdsAsistentaBroker.py); tools/hds-raport.sh.in e in shell si tine aceeasi lista, iar proba le compara.
# Pe HiSilicon functiile de citire din hi_dvb opresc nucleul pe unele placi SF8008 (proc_audio_*_read, proc_video_alpha_read,
# proc_video_zapmode_read: un Oops nou la fiecare fisier). Listele *_choices se citesc: Components/AVSwitch.py le citeste la
# fiecare pornire. Pe orice placa: *_apply (citirea poate declansa ceva) si *event* (citirea poate astepta).
VIDEO_OPRITE_HISILICON = ("alpha", "zapmode")

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


def eHiSilicon(radacina=""):
	"""True pe placile HiSilicon: au /proc/msp. radacina muta cautarea intr-un dosar de proba."""
	return os.path.isdir(os.path.join(radacina or "/", "proc", "msp"))


def nodOprit(cale, hisilicon):
	"""True pentru un fisier din /proc/stb care nu se citeste. cale: absoluta, sub o radacina de proba sau relativa la /proc/stb
	("audio/ac3"); o cale absoluta din alta parte nu e un nod."""
	c = str(cale).replace("\\", "/")
	i = c.find("proc/stb/")
	if i >= 0:
		c = c[i + len("proc/stb/"):]
	elif c.startswith("/"):
		return False
	c = c.strip("/")
	nume = c.rsplit("/", 1)[-1]
	if nume.endswith("_apply") or "event" in nume:
		return True
	if not hisilicon:
		return False
	if c.startswith("audio/"):
		return not nume.endswith("_choices")
	return c.startswith("video/") and nume in VIDEO_OPRITE_HISILICON


def blocat():
	"""True cat timp o citire a driverului nu raspunde de mai mult de TIMP_S."""
	_verificaFirul()
	return _STARE["blocat"]


def _verificaFirul():
	fir = _STARE["fir"]
	if fir is None or not fir.is_alive():
		if _STARE["blocat"]:
			_STARE["blocat"] = False
			_jurnal("citirea lui %s s-a terminat dupa %.1f s: citesc din nou driverul" % (_STARE["cale"], time.time() - _STARE["pornit_t"]))
		return
	if not _STARE["blocat"] and time.time() - _STARE["pornit_t"] > TIMP_S:
		_STARE["blocat"] = True
		_jurnal("citirea lui %s nu raspunde de %.1f s: nu mai citesc driverul cat timp nu se termina"
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
	if durata > TIMP_S:
		_jurnal("citirea lui %s a durat %.1f s" % (argumente[0] if argumente else "?", durata))


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
