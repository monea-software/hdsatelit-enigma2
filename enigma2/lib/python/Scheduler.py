# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
# Pluginul inregistreaza functii dupa cheie si construieste datele unei programari.

__all__ = ("SchedulerEntry", "TIMERTYPE", "AFTEREVENT", "addFunctionTimer", "functionTimers")


class TIMERTYPE:
	# Dovada cere numai identificatorul OTHER, fara o valoare numerica anume.
	OTHER = "other"


class AFTEREVENT:
	# Pluginul cere numai pastrarea optiunii fara actiune dupa programare.
	NONE = "none"


class SchedulerEntry:
	def __init__(self, begin, end, timerType=TIMERTYPE.OTHER, afterEvent=AFTEREVENT.NONE):
		# Pastram datele cerute; acest modul nu executa programari.
		self.begin = int(begin)
		self.end = int(end)
		self.timerType = timerType
		self.afterEvent = afterEvent
		self.function = None
		self.repeated = 0


class _Registru(dict):
	def getItem(self, key, default=None):
		return self.get(key, default)

	def remove(self, key):
		self.pop(key, None)


functionTimers = _Registru()


def addFunctionTimer(key, name, function, cancel, useOwnThread=False):
	# Retinem functiile, fara sa pornim lucrul sau un fir la inregistrare.
	functionTimers[key] = (name, function, cancel, bool(useOwnThread))
