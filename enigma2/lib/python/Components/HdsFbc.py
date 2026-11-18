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


CHEI = ("fbc_connect", "fbc_link")


def _grupa(tunere, set_id):
	"""Cele opt demodulatoare ale setului `set_id`, in ordinea frontendurilor, sau None cand setul nu e confirmat."""
	grupa = sorted((t for t in tunere if t.fbc_set_id == set_id), key=lambda t: t.frontend_id)
	if len(grupa) != 8 or any(
			t.fbc_role not in (RADACINA, LEGAT) or t.type not in ("DVB-S", "DVB-S2") for t in grupa):
		return None
	frontends = [t.frontend_id for t in grupa]
	if frontends != list(range(frontends[0], frontends[0] + 8)):
		return None
	return grupa


def _scriePereche(frontend, dorit):
	"""Scrie fbc_connect si fbc_link, in ordinea asta, MEREU, si cand /proc arata deja valoarea dorita: asa face
	OE-Alliance enigma2 (fbc.cpp SetProcFBCID, GPL-2.0; cod nou). Pana la 0.7.5 se scria numai ce era altfel decat
	valoarea citita, iar driverul GigaBlue (Quad 4K Pro, 45308X FBC) pare sa nu aplice o valoare care nu i-a fost
	scrisa: /proc arata tunerul A pe 0 si B pe 1, dar B pierdea semnalul in aceeasi secunda in care A schimba tensiunea
	sau trimitea comanda de motor, iar mufa motorului ramanea fara curent (asistenta 457322,
	15.11.2026). Intoarce (reusit, valorile vechi); la o greseala pune la loc valorile vechi."""
	vechi = tuple(_numar(_citeste(frontend, cheie)) for cheie in CHEI)
	if vechi[0] is None or vechi[0] >= 8 or vechi[1] not in (0, 1):
		print("[HdsFbc] rutare refuzata pentru frontend %d: proc lipsa sau nevalid" % frontend)
		return False, vechi
	incercate = []
	try:
		for cheie, anterior, valoare in zip(CHEI, vechi, dorit):
			# Si scrierea care arunca exceptia poate sa fi ajuns partial la driver.
			incercate.append((cheie, anterior))
			_scrie(frontend, cheie, valoare)
		if tuple(_numar(_citeste(frontend, cheie)) for cheie in CHEI) != tuple(dorit):
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
		return False, vechi
	return True, vechi


def ruteaza(tunere, sursa_slot, radacina_slot, legat=True):
	"""Leaga numai intrari fizice FBC confirmate; demodulatoarele interne raman neatinse. Scrierea pleaca si cand
	valoarea citita e deja cea dorita (_scriePereche), ca setTunerLinked -> UpdateFBCID in OE-Alliance."""
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
	grupa = _grupa(tunere, set_id)
	if grupa is None:
		return False
	index = [t.frontend_id for t in grupa].index(radacina.frontend_id)
	dorit = (index, int(bool(legat)))
	reusit, vechi = _scriePereche(sursa.frontend_id, dorit)
	if reusit:
		print("[HdsFbc] frontend %d: fbc_connect %d, fbc_link %d scrise (erau %s/%s)" % (
			sursa.frontend_id, dorit[0], dorit[1], vechi[0], vechi[1]))
	return reusit


def _mod(tuner):
	try:
		return tuner.config.configMode.value
	except AttributeError:
		return None


def _unicableLegat(tuner):
	avansat = getattr(tuner.config, "advanced", None)
	conectat = getattr(avansat, "unicableconnected", None)
	return conectat is not None and bool(conectat.value)


def ruteazaIndependente(tunere):
	"""La fiecare SecConfigure.update (si deci la pornire, din SecConfigure.__init__), inaintea legaturilor: fiecare
	demodulator FBC care nu primeste mai jos o legatura primeste valorile implicite, scrise MEREU, ca OE-Alliance enigma2
	(GPL-2.0, cod nou: la pornire eFBCTunerManager, apoi la fiecare reconfigurare sec.cpp clear() -> fbc.cpp
	SetDefaultFBCID): o radacina pe mufa ei (fbc_connect = locul ei in set, fbc_link 0), iar un demodulator legat
	nefolosit (nimic conectat) pe 0 si 0. Asa o intrare redevenita independenta nu ramane pe cablul vecinului, iar
	driverul primeste valoarea si cand /proc o arata deja (_scriePereche, asistenta 457322).
	Fara resetarea intermediara din clear(): o radacina care se leaga mai jos (loopthrough, Unicable legat) si un
	demodulator legat folosit raman pentru linkNIMs -> ruteaza, deci fiecare primeste o singura pereche de scrieri, cu
	valoarea finala. Intoarce cate demodulatoare au primit scrierea."""
	seturi = sorted(set(t.fbc_set_id for t in tunere if t.fbc_set_id is not None and t.fbc_set_id >= 0))
	scrise = 0
	for set_id in seturi:
		grupa = _grupa(tunere, set_id)
		if grupa is None:
			continue
		randuri = []
		for index, tuner in enumerate(grupa):
			mod = _mod(tuner)
			if mod is None:
				continue
			if tuner.fbc_role == RADACINA:
				if mod == "loopthrough" or (mod == "advanced" and _unicableLegat(tuner)):
					continue  # linkNIMs aplica mai jos legatura explicita, fara o resetare intermediara.
				dorit = (index, 0)
			elif mod == "nothing":
				dorit = (0, 0)
			else:
				continue  # demodulator legat folosit: neatins, ca pana acum
			reusit, vechi = _scriePereche(tuner.frontend_id, dorit)
			if reusit:
				scrise += 1
			randuri.append("%d=%d/%d(era %s/%s)%s" % (tuner.frontend_id, dorit[0], dorit[1], vechi[0], vechi[1],
				"" if reusit else " ESUAT"))
		if randuri:
			print("[HdsFbc] setul %d, fbc_connect/fbc_link scrise ca la pornire: %s" % (set_id, " ".join(randuri)))
	return scrise
