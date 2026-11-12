# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com & hdsatelit.com
# SPDX-License-Identifier: GPL-2.0-only

"""Data cu numele zilelor si lunilor in limba meniului.

Imaginea nu are datele de limba ale glibc (reteta: IMAGE_LINGUAS = "") si nu cheama setlocale nicaieri, deci
time.strftime da %A, %a, %B, %b si %c in engleza in ORICE limba (testerul JAKITAKI, meniul in polona, 0.7.3: „Tuesday,
November” intr-o tema din afara). Aici numele vin din cataloagele noastre (_), care le au deja in toate cele 30 de limbi:
zilele („Monday”, „Mon”) si lunile intregi (msgid-urile romanesti „ianuarie” ... „decembrie”, din HdsAfisajDate). Restul
formatului trece neschimbat prin time.strftime. Fara catalog sau fara traducere, textul ramane ca inainte (engleza).
"""

import re
import time


def N_(text):
	"""Marcaj pentru xgettext (--keyword=N_), fara efect: numele se traduc la folosire."""
	return text


# tm_wday: 0 = luni
ZILE = (N_("Monday"), N_("Tuesday"), N_("Wednesday"), N_("Thursday"), N_("Friday"), N_("Saturday"), N_("Sunday"))
ZILE_SCURT = (N_("Mon"), N_("Tue"), N_("Wed"), N_("Thu"), N_("Fri"), N_("Sat"), N_("Sun"))
# tm_mon: 1 = ianuarie (aceleasi texte ca in Components/HdsAfisajDate.py, traduse in toate limbile)
LUNI = (N_("ianuarie"), N_("februarie"), N_("martie"), N_("aprilie"), N_("mai"), N_("iunie"), N_("iulie"),
	N_("august"), N_("septembrie"), N_("octombrie"), N_("noiembrie"), N_("decembrie"))
# TRANSLATORS: short month name in a date, as in "11 Nov" (strftime %b): the usual short form of your language
# (Polish "lis", German "Nov"). "May" here is the short form of the month May.
LUNI_SCURT = (N_("Jan"), N_("Feb"), N_("Mar"), N_("Apr"), N_("May"), N_("Jun"), N_("Jul"), N_("Aug"), N_("Sep"),
	N_("Oct"), N_("Nov"), N_("Dec"))
# numele englezesti ale lunilor intregi (ce da en.po pentru LUNI): cand numele scurt nu e tradus inca, se foloseste
# numele intreg tradus, daca limba nu e engleza (un nume intreg in limba meniului e mai bun decat unul scurt in engleza)
_LUNI_ENGLEZA = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
	"November", "December")
# %c al glibc in limba C („Tue Nov 11 14:30:00 2026”), cu ziua inaintea lunii, ca in restul imaginii
FORMAT_C = "%a %d %b %Y %H:%M:%S"
_COD = re.compile(r"%([-_0^#]*)([0-9]*)([EO]?)(.)")


def _traducere(text):
	try:
		import builtins
		f = getattr(builtins, "_", None)
		return f(text) if f is not None else text
	except Exception:
		return text


def numeZi(t, scurt=False):
	"""Numele zilei din time.struct_time, in limba meniului."""
	return _traducere((ZILE_SCURT if scurt else ZILE)[t.tm_wday])


def numeLuna(t, scurt=False):
	"""Numele lunii din time.struct_time, in limba meniului."""
	i = t.tm_mon - 1
	lung = _traducere(LUNI[i])
	if lung == LUNI[i] and _traducere(ZILE[0]) == ZILE[0]:
		# niciun catalog activ (nici zilele nu sunt traduse): engleza, ca inainte, nu msgid-ul romanesc
		lung = _LUNI_ENGLEZA[i]
	if not scurt:
		return lung
	s = _traducere(LUNI_SCURT[i])
	if s == LUNI_SCURT[i] and lung != _LUNI_ENGLEZA[i]:
		return lung
	return s


def dataText(format, t=None):
	"""time.strftime(format, t) cu numele zilelor si lunilor traduse (%A %a %B %b %h %c). t: struct_time, secunde sau
	None (acum). Semnul ^ (litere mari, „%^A”) se pastreaza; celelalte coduri trec neschimbate prin time.strftime."""
	if t is None:
		t = time.localtime()
	elif isinstance(t, (int, float)):
		t = time.localtime(t)
	# Cod cu cod: numele traduse si textul dintre coduri nu trec prin strftime (literele din afara ASCII ar depinde de
	# LC_CTYPE si de felul cum e construit Python); fiecare alt cod („%d”, „%H”...) trece singur prin time.strftime.
	parti = []
	poz = 0
	for m in _COD.finditer(format):
		parti.append(format[poz:m.start()])
		poz = m.end()
		semne, cod = m.group(1), m.group(4)
		if cod == "%":
			parti.append("%")
			continue
		if cod == "c":
			nume = dataText(FORMAT_C, t)
		elif cod == "A":
			nume = numeZi(t)
		elif cod == "a":
			nume = numeZi(t, True)
		elif cod == "B":
			nume = numeLuna(t)
		elif cod in ("b", "h"):
			nume = numeLuna(t, True)
		else:
			parti.append(time.strftime(m.group(0), t))
			continue
		parti.append(nume.upper() if "^" in semne else nume)
	parti.append(format[poz:])
	return "".join(parti)
