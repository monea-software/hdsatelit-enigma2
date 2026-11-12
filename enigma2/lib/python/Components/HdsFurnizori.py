# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Numele furnizorilor aratate omului: lista "Furnizor" a listei de canale, informatiile canalului, editorul de canale
si interfata web. Numai cum se arata: lamedb si buchetele nu se ating.

Un serviciu de satelit gasit la scanare numai in PAT (fara SDT) primeste de la nucleu furnizorul facut din transponder
(lib/dvb/hdsgrad.h, furnizorScanare): "DVB-S2 8PSK 11250H 51.5°E". Listele mai vechi au pozitiile vestice scrise ca
est, cu valoarea bruta: "DVB-S2 8PSK 11222H 330.0°E" (= 30,0 vest). Pentru om grupa se numeste dupa operatorul
transponderului, cand il stie imaginea (data/operatori-satelit.json, Components/HdsOperatoriSatelit.py), altfel
"Satelit 51,5°E, 11250 H", cu pozitia scrisa ca in restul imaginii (Components/HdsGrade.py: in romana "30,0°V", in
engleza "30.0°W").

Serviciile fara niciun furnizor stau la nucleu in grupa "Unknown" (lib/dvb/db.cpp, eDVBDBProvidersQuery): "Fără
furnizor". Un furnizor scris numai din semne ("-", ".") e "Furnizor fără nume".

Modulul nu importa nimic din enigma la incarcare: se probeaza pe PC (teste/test_lista_buchete_exit.py).
"""
from __future__ import absolute_import, unicode_literals

import re

try:
	_text = unicode  # noqa: F821  (Python 2)
except NameError:
	_text = str

GRAD = u"°"
# furnizorul de scanare: sistemul, modulatia, frecventa in MHz lipita de polarizare, pozitia cu o zecimala, E sau W
_SCANARE = re.compile(u"^DVB-S2? (?:QPSK|8PSK) (\\d{3,6})([HVLR]) (\\d{1,4})\\.(\\d)\\s*" + GRAD + u"?\\s*([EW])$")
# un furnizor fara nicio litera sau cifra
_FARA_NUME = re.compile(u"^[\\W_]+$", re.UNICODE)
# grupa nucleului pentru serviciile fara furnizor (lib/dvb/db.cpp)
NECUNOSCUT = "Unknown"
# cat poate fi frecventa din lamedb departe de cea din lista operatorilor (MHz)
TOLERANTA_MHZ = 3

T_FARA_FURNIZOR = "Fără furnizor"
T_FARA_NUME = "Furnizor fără nume"
T_SATELIT = "Satelit %s, %s"

# grupele listei, in ordine: furnizorii adevarati (si operatorii stiuti), transponderele fara operator (de la vest la
# est, apoi dupa frecventa), furnizorul fara nume, serviciile fara furnizor
GRUPA_NUME, GRUPA_TRANSPONDER, GRUPA_FARA_NUME, GRUPA_FARA_FURNIZOR = range(4)


def N_(text):
	return text


def _t(text):
	try:
		return _(text)  # noqa: F821  (functia de traducere a enigma2, pusa in builtins)
	except NameError:
		return text


def _u(text):
	if text is None:
		return u""
	if isinstance(text, bytes):
		return text.decode("utf-8", "replace")
	return _text(text)


def din_scanare(nume):
	"""Furnizorul facut de scanare -> (pozitia bruta 0..3599, frecventa in MHz, polarizarea), altfel None.
	"330.0°E" si "30.0°W" dau amandoua 3300 (vestul ca 3600 - x, ca in nucleu)."""
	m = _SCANARE.match(_u(nume).strip())
	if m is None:
		return None
	zecimi = int(m.group(3)) * 10 + int(m.group(4))
	if zecimi > 3600:
		return None
	if m.group(5) == "W":
		zecimi = (3600 - zecimi) % 3600
	return zecimi % 3600, int(m.group(1)), m.group(2)


def _transpondere(op):
	t = op.get("transpondere")
	if isinstance(t, list):
		return [x for x in t if isinstance(x, dict)]
	t = op.get("transponder")
	return [t] if isinstance(t, dict) else []


def _operatori():
	try:
		try:
			from Components import HdsOperatoriSatelit as O
		except ImportError:
			import HdsOperatoriSatelit as O
		return O.incarca().get("operatori") or []
	except Exception as e:
		print("[HdsFurnizori] operatorii: %s" % e)
		return []


def operator_pentru(poz, frecventa_mhz, pol, operatori=None):
	"""Numele operatorului care are transponderul (pozitia bruta, frecventa in MHz, H/V), sau None."""
	for op in (_operatori() if operatori is None else operatori):
		try:
			if int(op.get("pozitie")) % 3600 != poz:
				continue
			for t in _transpondere(op):
				f = t.get("frecventa")
				if f is None or (t.get("pol") or "") != pol:
					continue
				if abs(int(f) // 1000 - int(frecventa_mhz)) <= TOLERANTA_MHZ:
					nume = _u(op.get("nume")).strip()
					if nume:
						return nume
		except Exception:
			continue
	return None


def _pozitie(poz):
	try:
		from Components.HdsGrade import pozitieOrbitala
	except ImportError:
		from HdsGrade import pozitieOrbitala
	return pozitieOrbitala(poz) or _text(poz)


def grupa(nume):
	"""In ce grupa a listei "Furnizor" intra furnizorul (GRUPA_*)."""
	n = _u(nume).strip()
	if not n or n == NECUNOSCUT:
		return GRUPA_FARA_FURNIZOR
	if _FARA_NUME.match(n):
		return GRUPA_FARA_NUME
	s = din_scanare(n)
	if s is not None and operator_pentru(*s) is None:
		return GRUPA_TRANSPONDER
	return GRUPA_NUME


def nume_aratat(nume, operatori=None):
	"""Numele grupei din lista "Furnizor" (si al furnizorului oriunde se arata unul): furnizorul de scanare dupa
	operatorul transponderului sau "Satelit 51,5°E, 11250 H"; grupa nucleului fara furnizor "Fără furnizor"; un nume
	numai din semne "Furnizor fără nume"; orice alt nume ramane cum e."""
	n = _u(nume).strip()
	if not n or n == NECUNOSCUT:
		return _t(T_FARA_FURNIZOR)
	if _FARA_NUME.match(n):
		return _t(T_FARA_NUME)
	s = din_scanare(n)
	if s is None:
		return _u(nume)
	poz, frecventa, pol = s
	tp = u"%d %s" % (frecventa, pol)
	op = operator_pentru(poz, frecventa, pol, operatori)
	if op:
		# numele operatorilor din 0.7.x poarta deja transponderul ("Abertis 11222 H (Spania)"): fara el a doua oara
		return op if tp in op else u"%s · %s" % (op, tp)
	return _t(T_SATELIT) % (_pozitie(poz), tp)


def aratat_in_informatii(nume):
	"""Furnizorul unui canal in informatii (bara, INFO, panoul listei): numai furnizorul de scanare se schimba; un
	furnizor gol ramane gol (ecranul isi pune semnul lui)."""
	n = _u(nume)
	if din_scanare(n) is None:
		return n
	return nume_aratat(n)


def cheie_ordine(nume, aratat=None):
	"""Cheia de sortare a listei "Furnizor": furnizorii dupa nume, apoi transponderele fara operator de la vest la est
	si dupa frecventa, apoi furnizorul fara nume, la urma serviciile fara furnizor."""
	g = grupa(nume)
	if aratat is None:
		aratat = nume_aratat(nume)
	if g == GRUPA_TRANSPONDER:
		poz, frecventa, pol = din_scanare(nume)
		return (g, poz - 3600 if poz > 1800 else poz, frecventa, pol, u"")
	return (g, 0, 0, u"", _u(aratat).lower())
