# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Mutarea setarilor salvate sub o cheie veche la cheia noua, fara sa se piarda valoarea. Doar in imaginea HDSatelit.

Setarile releului de flux al modulului de acces (Components/UsageConfig.py, config.usage si config.misc) au acum
numele acces_streamrelay_url, acces_streamrelay_port si acces_streamrelay_delay. O valoare salvata in
/etc/enigma2/settings sub numele de dinainte (alt prefix din litere, acelasi sfarsit: _streamrelay_url / _port /
_delay) trece la prima pornire la cheia noua, daca aceea nu are deja o valoare salvata; cheia veche se scoate, deci la
urmatoarea salvare a setarilor nu mai apare in fisier. Cheile vechi se recunosc dupa forma (TIPAR_RELEU), fara sa le
scriem numele.

Cum pastreaza enigma2 cheile necunoscute (Components/config.py): settings se citeste la incarcarea lui config.py, iar o
cheie care nu are (inca) element ramane in content.stored_values al subsectiunii ei si se scrie inapoi la fiecare
salvare. Mutarea lucreaza acolo: pune valoarea in stored_values la cheia noua (asa o ia si un element definit din nou
mai tarziu, cum face InitUsageConfig) si in elementul deja definit, apoi scoate cheia veche. Se poate chema de oricate
ori: a doua oara nu mai gaseste nimic de mutat. Modulul nu importa nimic din enigma2 (se incearca pe PC)."""
import re

# o cheie a releului: un prefix din litere mici, apoi _streamrelay_ si felul valorii
TIPAR_RELEU = re.compile(r"^([a-z]+)_streamrelay_(url|port|delay)$")
PREFIX_NOU = "acces"


def cheie_noua(cheie):
	"""Cheia noua pentru o cheie veche a releului, sau None (cheia nu e a releului sau e deja cea noua)."""
	m = TIPAR_RELEU.match(cheie or "")
	if not m or m.group(1) == PREFIX_NOU:
		return None
	return "%s_streamrelay_%s" % (PREFIX_NOU, m.group(2))


def muta_releul(subsectiune):
	"""Pentru o subsectiune (config.usage, config.misc): muta valorile salvate sub cheile vechi ale releului la cheile
	noi. Intoarce [(cheia veche, cheia noua, "mutat" | "ramane cea noua")]."""
	continut = subsectiune.content
	salvate = continut.stored_values
	rez = []
	for veche in sorted(k for k in list(salvate) if cheie_noua(k)):
		noua = cheie_noua(veche)
		valoare = salvate.pop(veche)
		element = continut.items.get(noua)
		are_noua = salvate.get(noua) is not None or (element is not None and element.saved_value is not None)
		if are_noua or isinstance(valoare, dict) or valoare is None:
			rez.append((veche, noua, "ramane cea noua"))
			continue
		salvate[noua] = valoare
		if element is not None:
			element.saved_value = valoare
			element.load()
		rez.append((veche, noua, "mutat"))
	return rez


def muta_releul_peste_tot(config, jurnal=None):
	"""muta_releul pe config.usage si config.misc (cele care exista); fiecare mutare se scrie in jurnal (numai
	numele cheilor, nu si valorile)."""
	rez = []
	for nume in ("usage", "misc"):
		if nume not in config.content.items:
			continue
		for veche, noua, ce in muta_releul(getattr(config, nume)):
			rez.append(("config.%s.%s" % (nume, veche), "config.%s.%s" % (nume, noua), ce))
	if jurnal is not None:
		for veche, noua, ce in rez:
			jurnal("%s -> %s: %s" % (veche, noua, ce))
	return rez
