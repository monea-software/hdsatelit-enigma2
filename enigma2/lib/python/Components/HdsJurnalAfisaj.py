# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsJurnalAfisaj.py: jurnalul iesirii HDMI si al rezolutiei (/home/root/logs/hds-hdmi.log, Components/HdsJurnal.py).
# - modAplicat(valori, ok, atins): chemat din Components/VideoOutput.py (apply): modul video, rata dupa canal si
#   celelalte setari scrise in driver, cu rezultatul (primit / refuzat de driver); numai cand difera de randul de dinainte.
# - paza conectarii: la primul mod aplicat porneste un ceas de PAUZA_S secunde care citeste starea HotPlug a iesirii HDMI
#   (/proc/msp/hdmi0 pe HiSilicon, /proc/stb/hdmi/hotplug pe celelalte) si scrie conectarea si deconectarea
#   televizorului. O citire de fisier /proc la cateva secunde; nimic altceva.
# Numai date tehnice (modul, rata, culorile, starea cablului).

import os
import re

from Components import HdsJurnal

PAUZA_S = 5
HDMI0 = "/proc/msp/hdmi0"
HOTPLUG = "/proc/stb/hdmi/hotplug"
_HOTPLUG_RE = re.compile(r"HotPlug\s*:\s*(\w+)", re.IGNORECASE)

_ultimMod = [None]
_paza = [None]
_stare = [None]


def textMod(valori, ok, atins):
	parti = []
	for k in sorted(valori):
		v = valori[k]
		if v in (None, ""):
			continue
		parti.append("%s=%s" % (k, "da" if v is True else ("nu" if v is False else v)))
	rez = "primit" if ok else ("modul refuzat de driver" if atins is False else "o setare refuzata de driver")
	return "aplicat %s | %s" % (" ".join(parti) if parti else "-", rez)


def modAplicat(valori, ok, atins):
	try:
		text = textMod(valori or {}, ok, atins)
		if text != _ultimMod[0]:
			_ultimMod[0] = text
			(HdsJurnal.info if ok else HdsJurnal.avert)("hdmi", "mod", text)
		pornestePaza()
	except Exception:
		pass


def citesteConectarea(hdmi0=HDMI0, hotplug=HOTPLUG):
	"""True / False / None (necunoscut): televizorul legat pe HDMI."""
	try:
		if os.path.exists(hdmi0):
			with open(hdmi0) as f:
				m = _HOTPLUG_RE.search(f.read())
			if m:
				v = m.group(1).lower()
				return v in ("yes", "y", "true", "1", "on", "enable", "enabled", "da")
		if os.path.exists(hotplug):
			with open(hotplug) as f:
				return f.read().strip() not in ("0", "")
	except (IOError, OSError):
		pass
	return None


def _verifica():
	acum = citesteConectarea()
	if acum is None or acum == _stare[0]:
		return
	inainte, _stare[0] = _stare[0], acum
	if inainte is None:
		HdsJurnal.info("hdmi", "conectare", "televizor %s la pornirea pazei" % ("legat" if acum else "nelegat"))
	elif acum:
		HdsJurnal.info("hdmi", "conectare", "televizor conectat (HotPlug)")
	else:
		HdsJurnal.avert("hdmi", "conectare", "televizor deconectat (HotPlug)")


def pornestePaza():
	if _paza[0] is not None:
		return
	try:
		from enigma import eTimer
	except ImportError:
		_paza[0] = False
		return
	t = eTimer()
	t.callback.append(_verifica)
	t.start(PAUZA_S * 1000, False)
	_paza[0] = t
	_verifica()
