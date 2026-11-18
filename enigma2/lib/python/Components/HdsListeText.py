# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Numele din liste vechi: UTF8 valid ramane, octetii vechi devin CP1252/Latin1."""
import re

_VECHI = re.compile(r"[\udc80-\udcff]+")
_LATIN1 = {0xdc00 + n: n for n in range(128, 256)}


def _vechi(m):
	date = m.group().encode("utf-8", "surrogateescape")
	return date.decode("cp1252", "surrogateescape").translate(_LATIN1)


def text_lista(text):
	"""Text de afisat, fara pierderea literelor sau surrogate in JSON si widget-uri.

	Se decodifica numai octetii UTF8 invalizi, inclusiv intr-un nume mixt.
	Octetii nedefiniti de CP1252 raman caracterele Latin1 corespunzatoare.
	Pentru rescriere fara schimbari, apelantul pastreaza separat datele brute.
	"""
	# 0.7.7 (UIF): calea scurta, cu acelasi rezultat: octetii UTF-8 valizi (decodarea stricta merge) si textul fara
	# surogate (ASCII, sau codarea stricta merge) n-au ce schimba, deci expresia nu mai trece peste tot textul (pe un
	# lamedb de 2,2 MB 0,3-0,5 s pe ARM, cu lacatul Python tinut). Numai listele vechi (octeti CP1252) trec pe calea lunga.
	if isinstance(text, bytes):
		try:
			return text.decode("utf-8")
		except UnicodeDecodeError:
			text = text.decode("utf-8", "surrogateescape")
	elif text.__class__ is str:   # o subclasa de str ia calea veche, care intoarce un str simplu
		if text.isascii():
			return text
		try:
			text.encode("utf-8")
			return text
		except UnicodeEncodeError:
			pass
	return _VECHI.sub(_vechi, text)
