# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com & hdsatelit.com
# SPDX-License-Identifier: GPL-2.0-only
"""Pregatirea montarii pe fir separat si raspunsul pe firul interfetei."""
import threading
import time

_context = threading.local()


def inTermen():
	return time.monotonic() < getattr(_context, "pana", float("inf"))


def executa(manager, cheie, functie, callback=None, termen=3):
	from Components.HdsStocareDisc import cere, stare, uita
	from enigma import eTimer
	if not hasattr(manager, "_disc_tasks"):
		manager._disc_tasks = {}
	if cheie in manager._disc_tasks:
		return False
	cache = ("montare", id(manager), cheie)
	uita(cache)
	pana = time.monotonic() + termen
	initial = [None]
	timer = eTimer()
	manager._disc_tasks[cheie] = timer
	if not hasattr(manager, "_disc_culegeri"):
		manager._disc_culegeri = {}
	def culege():
		rez = stare(cache) or initial[0]
		if (not rez or rez["stare"] == "asteapta") and time.monotonic() >= pana:
			rez = {"stare": "termen", "valoare": None, "eroare": ""}
		if not rez or rez["stare"] == "asteapta":
			return
		timer.stop()
		manager._disc_tasks.pop(cheie, None)
		manager._disc_culegeri.pop(cheie, None)
		if callback is not None:
			callback(rez)
	manager._disc_culegeri[cheie] = culege
	timer.callback.append(culege)
	def citeste():
		_context.pana = pana
		try:
			return functie()
		finally:
			_context.pana = float("inf")
	initial[0] = cere(cache, citeste, termen=termen, varsta=5)
	timer.start(100, False)
	return True


def culegeAcum(manager, gata, termen):
	"""Inainte de bucla principala (la pornire eTimer-ul lui executa nu bate inca): culege pe firul interfetei raspunsurile
	lucrarilor pornite de executa, pana cand gata() e adevarat sau trec `termen` secunde. Lucrul pe disc ramane pe fire,
	aici numai se asteapta; ce nu termina in termen se culege mai tarziu, ca pana acum, de eTimer. Intoarce gata()."""
	pana = time.monotonic() + max(0.0, termen)
	while not gata():
		for culege in list(getattr(manager, "_disc_culegeri", {}).values()):
			culege()
		if gata() or time.monotonic() >= pana:
			break
		time.sleep(0.02)
	return gata()
