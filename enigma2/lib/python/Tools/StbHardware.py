# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Tools.StbHardware: numele pe care le importa pluginurile externe pentru panoul frontal si identitatea aparatului.

Pluginurile (de pilda EPGImport, plugin.py:35) fac `from Tools.StbHardware import ...` la incarcare; fara modul nu se
incarca deloc. Scris de noi: panoul frontal trece prin Tools/DreamboxHardware.py, cel folosit deja de mytest.py, iar
identitatea vine din regulile imaginii, apoi din /proc/stb.
Nimic nu arunca si nimic nu se atinge la incarcarea modulului.

Ce nu exista pe aparat da o valoare sigura, aceeasi de fiecare data:
- getFPWasTimerWakeup -> False (pornire de catre om: pluginul nu duce aparatul inapoi in oprire completa);
- getFPWakeuptime -> 0, getFPVersion -> None, getBoxProc/getBoxProcType/getBoxRCType -> "unknown",
  getHWSerial -> "unavailable"; scrierile (setFPWakeuptime, setRTCtime, setRTCoffset) nu fac nimic.
"""

from os.path import exists
from time import localtime, time

NECUNOSCUT = "unknown"
FARA_SERIE = "unavailable"

_TREZIRE = "/proc/stb/fp/was_timer_wakeup"
_RTC_OFFSET = "/proc/stb/fp/rtc_offset"

# citirea initiala, din Navigation sau de la prima cerere: (trezire de la ceas, eroare de citire)
_trezire = None


def _citeste(*cai):
	"""Primul fisier din cai care se poate citi si nu e gol, fara spatii; altfel None."""
	for cale in cai:
		try:
			with open(cale, "r", encoding="utf-8", errors="replace") as f:
				text = f.read().strip()
		except OSError:
			continue
		if text:
			return text
	return None


def getFPVersion():
	try:
		from Tools.DreamboxHardware import getFPVersion as citeste
		return citeste()
	except Exception as e:
		print("[StbHardware] versiunea panoului: %r" % (e,))
		return None


def setFPWakeuptime(wutime):
	try:
		from Tools.DreamboxHardware import setFPWakeuptime as scrie
		scrie(wutime)
	except Exception as e:
		print("[StbHardware] ora de trezire: %r" % (e,))


def getFPWakeuptime():
	try:
		from Tools.DreamboxHardware import getFPWakeuptime as citeste
		return citeste()
	except Exception as e:
		print("[StbHardware] ora de trezire: %r" % (e,))
		return 0


def setRTCtime(wutime):
	try:
		from Tools.DreamboxHardware import setRTCtime as scrie
		scrie(wutime)
	except Exception as e:
		print("[StbHardware] ceasul panoului: %r" % (e,))


def setRTCoffset(forsleep=None):
	"""Abaterea ceasului panoului fata de UTC, in secunde (fusul orar de acum), numai unde exista nodul.
	forsleep: se accepta pentru apelanti, nodul primeste aceeasi valoare."""
	if not exists(_RTC_OFFSET):
		return
	try:
		with open(_RTC_OFFSET, "w", encoding="ascii") as f:
			f.write(str(localtime(time()).tm_gmtoff))
	except OSError as e:
		print("[StbHardware] abaterea ceasului: %r" % (e,))


def _citesteTrezirea():
	"""(trezire de la ceas, eroare). Nodul se citeste din procfs; pe aparatele fara el, prin dispozitivul vechi."""
	text = _citeste(_TREZIRE)
	if text is not None:
		try:
			return bool(int(text)), False
		except ValueError:
			return False, True
	try:
		from Tools.DreamboxHardware import getFPWasTimerWakeup as citeste
		return bool(citeste()), False
	except Exception as e:
		print("[StbHardware] trezirea de la ceas: %r" % (e,))
		return False, True


def rememberFPWasTimerWakeup(was_timer_wakeup):
	"""Pastreaza citirea initiala din Navigation, inainte ca acesta sa stearga semnul din driver."""
	global _trezire
	if _trezire is None:
		_trezire = bool(was_timer_wakeup), False


def getFPWasTimerWakeup(check=False):
	"""True cand aparatul a pornit singur, de la ceas. Se citeste o singura data: pluginurile intreaba si la multa vreme
	dupa pornire. Navigation pastreaza citirea inainte de stergere; fara el, prima cerere citeste si sterge semnul.
	O repornire a interfetei citeste semnul deja sters si nu mai conteaza ca trezire.
	check=True da perechea (valoare, eroare de citire)."""
	global _trezire
	if _trezire is None:
		_trezire = _citesteTrezirea()
		if _trezire[0]:
			clearFPWasTimerWakeup()
	return _trezire if check else _trezire[0]


def clearFPWasTimerWakeup():
	"""Sterge semnul din driver; raspunsul lui getFPWasTimerWakeup pentru pornirea de acum ramane."""
	try:
		from Tools.DreamboxHardware import clearFPWasTimerWakeup as sterge
		sterge()
	except Exception as e:
		print("[StbHardware] stergerea trezirii: %r" % (e,))


def getBoxProc():
	"""Modelul imaginii, apoi al placii, acelasi ca in rapoarte."""
	from Tools.HardwareInfo import getModelName
	return getModelName()


def getBoxProcType():
	return _citeste("/proc/stb/info/type") or NECUNOSCUT


def getHWSerial():
	return _citeste("/proc/stb/info/sn", "/proc/stb/info/serial", "/proc/stb/info/serial_number", "/sys/class/dmi/id/product_serial") or FARA_SERIE


def getBoxRCType():
	return _citeste("/proc/stb/ir/rc/type") or NECUNOSCUT
