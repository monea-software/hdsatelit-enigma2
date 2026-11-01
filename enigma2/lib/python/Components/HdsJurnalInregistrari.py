# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsJurnalInregistrari.py: jurnalul inregistrarilor si al temporizatoarelor (/home/root/logs/hds-inregistrari.log,
# Components/HdsJurnal.py), din RecordTimerEntry.log (RecordTimer.py: un singur rand acolo).
# Se scriu numai codurile cunoscute de mai jos; textul liber al temporizatorului (numele fisierului, titlul emisiunii,
# descrierea) NU intra niciodata. Pornirea si oprirea: INFO, fara canal, fara titlu, cu spatiul liber de pe disc.
# Esecurile (serviciul nu se poate inregistra, pregatirea cazuta, scrierea pe disc cazuta, fara disc, pornirea
# refuzata): AVERT/EROARE cu canalul (numele si referinta serviciului), ca sa se afle ce nu merge.

import os

from Components import HdsJurnal

# cod -> (nivel, text fix, cu canal)
CODURI = {
	1: (HdsJurnal.EROARE, "serviciul de inregistrat nu se gaseste in grup", True),
	2: (HdsJurnal.EROARE, "pregatirea inregistrarii cazuta", True),
	4: (HdsJurnal.AVERT, "informatiile inregistrarii nu se pot scrie", True),
	7: (HdsJurnal.EROARE, "pregatirea a cazut, se reincearca", True),
	10: (HdsJurnal.AVERT, "reincercare programata", True),
	11: (HdsJurnal.INFO, "pornire", False),
	12: (HdsJurnal.INFO, "oprire sau prelungire", False),
	13: (HdsJurnal.EROARE, "pornirea refuzata", True),
	14: (HdsJurnal.AVERT, "omul n-a vrut sa schimbe canalul, inregistrarea poate cadea", True),
	17: (HdsJurnal.EROARE, "fara disc adevarat pentru inregistrare", True),
}
# din mesajele acestor coduri se pastreaza numai cifrele (codul de eroare, minutele), nu textul
CIFRE = (2, 10, 12, 13)


def _spatiu(dosar):
	try:
		st = os.statvfs(dosar or "/media/hdd")
		return "liber %d MB" % (st.f_bavail * st.f_frsize // (1024 * 1024))
	except (OSError, AttributeError):
		return "liber ?"


def _cifre(msg):
	import re
	n = re.findall(r"-?\d+", "%s" % msg)
	return (" (%s)" % " ".join(n[:3])) if n else ""


def dinLog(timer, code, msg):
	try:
		if getattr(timer, "justplay", False):
			return  # temporizator de schimbare a canalului, nu inregistrare
		d = CODURI.get(code)
		if d is None:
			return
		nivel, text, cuCanal = d
		if code in CIFRE:
			text += _cifre(msg)
		if code in (11, 12, 17):
			text += " | " + _spatiu(getattr(timer, "dirname", None))
		canal = None
		if cuCanal:
			try:
				ref = timer.service_ref.ref
				canal = HdsJurnal.canalDinReferinta(ref, timer.service_ref.getServiceName())
			except Exception:
				canal = None
		HdsJurnal.scrie("inregistrari", nivel, "temporizator", text, canal=canal)
	except Exception:
		pass


def eroareScriere(timer):
	"""Evenimentul evRecordWriteError (disc plin, disc scos)."""
	try:
		ref = timer.service_ref.ref
		canal = HdsJurnal.canalDinReferinta(ref, timer.service_ref.getServiceName())
	except Exception:
		canal = None
	HdsJurnal.eroare("inregistrari", "disc", "scrierea inregistrarii cazuta | " + _spatiu(getattr(timer, "dirname", None)),
		canal=canal)
