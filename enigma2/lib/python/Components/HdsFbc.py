# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only

"""Topologia FBC si rutarea intrarilor fizice cerute deja prin configurarea tunerelor."""

import re


OBISNUIT, RADACINA, LEGAT, ROL_NECUNOSCUT = range(4)


def _citeste(frontend, cheie):
	try:
		with open("/proc/stb/frontend/%d/%s" % (frontend, cheie), "r") as fisier:
			return fisier.read(256).strip()
	except (IOError, OSError, UnicodeError):
		return None


def _numar(text):
	try:
		valoare = int(text)
		return valoare if valoare >= 0 else None
	except (TypeError, ValueError):
		return None


def _radacini(text):
	"""Intrarile fizice din fbc_connect_choices. Doua forme: „0 1” si, la driverele Vu+ 4K (Duo4K cu 45308X FBC),
	„0=A, 1=B”; fara forma a doua niciun demodulator nu era radacina, rutarea se oprea si toate ramaneau pe intrarea A
	(sety, Vu+ Duo4K, 10.11.2026: cablul in A mergea numai cu tunerul B configurat)."""
	if not text:
		return None
	text = text.strip()
	if re.match(r"^[0-9]+(?:\s+[0-9]+)*$", text):
		valori = frozenset(int(x) for x in text.split())
	elif re.match(r"^[0-9]+\s*=\s*[A-Za-z]+(?:\s*,?\s*[0-9]+\s*=\s*[A-Za-z]+)*$", text):
		valori = frozenset(int(x) for x in re.findall(r"([0-9]+)\s*=", text))
	else:
		return None
	return valori if valori and max(valori) < 8 else None


def descopera(tunere):
	"""Intoarce {frontend: (rol, set_id)}. Numele singur nu dovedeste o legatura intre tunere."""
	rezultat, grupe, fara_proc = {}, {}, {}
	for tuner in tunere:
		frontend = tuner.frontend_id
		if frontend is None or frontend < 0 or tuner.type not in ("DVB-S", "DVB-S2"):
			continue
		text_set = _citeste(frontend, "fbc_set_id")
		set_id = _numar(text_set)
		nume = (tuner.description or "").strip().lower()
		fbc_in_nume = re.search(r"\bfbc\b", nume) is not None
		rezultat[frontend] = (ROL_NECUNOSCUT if set_id is not None or fbc_in_nume else OBISNUIT, set_id)
		if set_id is not None:
			grupe.setdefault(set_id, []).append(frontend)
		elif text_set is None and fbc_in_nume:
			fara_proc.setdefault(nume, []).append(frontend)

	for set_id, frontends in grupe.items():
		frontends.sort()
		# Pentru acest API setul are opt demodulatoare. Cu o grupa incompleta nu ghicim indexul local.
		if len(frontends) != 8 or frontends[-1] - frontends[0] != 7:
			continue
		alegeri = []
		for frontend in frontends:
			text = _citeste(frontend, "fbc_connect_choices")
			if text is not None:
				alegeri.append(_radacini(text))
		if not alegeri or None in alegeri or any(x != alegeri[0] for x in alegeri):
			continue
		for index, frontend in enumerate(frontends):
			rezultat[frontend] = (RADACINA if index in alegeri[0] else LEGAT, set_id)

	for frontends in fara_proc.values():
		frontends.sort()
		# Rezerva pentru driverele Vu+ vechi: numai opt intrari consecutive, cu acelasi nume explicit FBC.
		# set_id ramane necunoscut; aceasta recunoastere nu autorizeaza optimizari ale comenzilor SEC.
		if len(frontends) == 8 and frontends[-1] - frontends[0] == 7:
			for index, frontend in enumerate(frontends):
				rezultat[frontend] = (RADACINA if index < 2 else LEGAT, None)
	return rezultat


def _scrie(frontend, cheie, valoare):
	text = str(valoare)
	with open("/proc/stb/frontend/%d/%s" % (frontend, cheie), "w") as fisier:
		if fisier.write(text) != len(text):
			raise IOError("scriere proc incompleta")


def ruteaza(tunere, sursa_slot, radacina_slot, legat=True):
	"""Leaga numai intrari fizice FBC confirmate; demodulatoarele interne raman neatinse."""
	pe_slot = dict((t.slot, t) for t in tunere)
	sursa, radacina = pe_slot.get(sursa_slot), pe_slot.get(radacina_slot)
	if sursa is None or radacina is None:
		return False
	set_id = sursa.fbc_set_id
	if set_id is None or set_id < 0 or radacina.fbc_set_id != set_id:
		return False
	if sursa.fbc_role != RADACINA or radacina.fbc_role != RADACINA:
		return False
	if (sursa_slot == radacina_slot) == bool(legat):
		return False
	grupa = sorted((t for t in tunere if t.fbc_set_id == set_id), key=lambda t: t.frontend_id)
	if len(grupa) != 8 or any(
			t.fbc_role not in (RADACINA, LEGAT) or t.type not in ("DVB-S", "DVB-S2") for t in grupa):
		return False
	frontends = [t.frontend_id for t in grupa]
	if frontends != list(range(frontends[0], frontends[0] + 8)):
		return False
	index = frontends.index(radacina.frontend_id)
	frontend = sursa.frontend_id
	chei = ("fbc_connect", "fbc_link")
	vechi = tuple(_numar(_citeste(frontend, cheie)) for cheie in chei)
	if vechi[0] is None or vechi[0] >= 8 or vechi[1] not in (0, 1):
		print("[HdsFbc] rutare refuzata pentru frontend %d: proc lipsa sau nevalid" % frontend)
		return False
	dorit = (index, int(bool(legat)))
	incercate = []
	try:
		for cheie, anterior, valoare in zip(chei, vechi, dorit):
			if anterior != valoare:
				# Si scrierea care arunca exceptia poate sa fi ajuns partial la driver.
				incercate.append((cheie, anterior))
				_scrie(frontend, cheie, valoare)
		if tuple(_numar(_citeste(frontend, cheie)) for cheie in chei) != dorit:
			raise IOError("driverul nu a pastrat rutarea ceruta")
	except (IOError, OSError, ValueError) as eroare:
		print("[HdsFbc] rutarea frontend %d a esuat: %s" % (frontend, eroare))
		for cheie, anterior in reversed(incercate):
			try:
				_scrie(frontend, cheie, anterior)
				if _numar(_citeste(frontend, cheie)) != anterior:
					raise IOError("driverul nu a pastrat valoarea veche")
			except (IOError, OSError, ValueError) as revenire:
				print("[HdsFbc] revenire esuata frontend %d, %s: %s" % (frontend, cheie, revenire))
		return False
	return True


def ruteazaIndependente(tunere):
	"""O intrare fizica redevenita independenta nu trebuie sa ramana pe cablul vecinului."""
	for tuner in tunere:
		if tuner.fbc_role != RADACINA or tuner.fbc_set_id is None:
			continue
		mod = tuner.config.configMode.value
		if mod not in ("simple", "advanced", "equal", "satposdepends"):
			continue
		if mod == "advanced":
			avansat = getattr(tuner.config, "advanced", None)
			conectat = getattr(avansat, "unicableconnected", None)
			if conectat is not None and conectat.value:
				continue  # linkNIMs aplica mai jos legatura explicita, fara o resetare intermediara.
		ruteaza(tunere, tuner.slot, tuner.slot, legat=False)
