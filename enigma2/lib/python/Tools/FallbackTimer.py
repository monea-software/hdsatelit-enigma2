# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# FallbackTimer.py: temporizatoarele unui receptor de rezerva din retea, cum le cer pluginurile de EPG ale altor imagini (cautarea in EPG, EPG-ul
# grafic): `from Tools.FallbackTimer import FallbackTimerList`. Imaginea noastra nu are receptor de rezerva, deci aici lista lui e mereu goala si
# pluginul lucreaza numai cu temporizatoarele receptorului: FallbackTimerList cheama functia data dupa asezarea ecranului (onLayoutFinish), ca
# atunci cand rezerva e oprita. Ce s-ar face pe receptorul de rezerva (adaugare, schimbare, stergere) nu are unde: merge mai departe cu functia
# pentru eroare a pluginului, fara text nou pe ecran.
from timer import TimerEntry


class FallbackTimerList(object):
	def __init__(self, parent, fallbackFunction, fallbackFunctionNOK=None):
		self.fallbackFunction = fallbackFunction
		self.fallbackFunctionNOK = fallbackFunctionNOK or fallbackFunction
		self.parent = parent
		self.headers = {}
		self.url = None
		self.list = []
		parent.onLayoutFinish.append(self.fallbackFunction)

	def cleanServiceRef(self, service_ref):
		"""referinta fara numele canalului de la coada"""
		text = str(service_ref)
		if not text.endswith(":"):
			text = text.rsplit("::", 1)[0] + ":"
		return text

	def getFallbackTimerList(self):
		self.list = []
		self.fallback()

	def _faraRezerva(self, fallbackFunction, fallbackFunctionNOK):
		# nu exista rezerva: merge direct pe drumul de eroare al pluginului, fara text nou pe ecran
		self.fallbackFunction = fallbackFunction
		self.fallbackFunctionNOK = fallbackFunctionNOK or fallbackFunction
		print("[FallbackTimer] fara receptor de rezerva: %s" % getattr(fallbackFunction, "__name__", fallbackFunction))
		self.fallbackNOK()

	def removeTimer(self, timer, fallbackFunction, fallbackFunctionNOK=None):
		self._faraRezerva(fallbackFunction, fallbackFunctionNOK)

	def toggleTimer(self, timer, fallbackFunction, fallbackFunctionNOK=None):
		self._faraRezerva(fallbackFunction, fallbackFunctionNOK)

	def addTimer(self, timer, fallbackFunction, fallbackFunctionNOK=None):
		self._faraRezerva(fallbackFunction, fallbackFunctionNOK)

	def editTimer(self, timer, fallbackFunction, fallbackFunctionNOK=None):
		self._faraRezerva(fallbackFunction, fallbackFunctionNOK)

	def cleanupTimers(self, fallbackFunction, fallbackFunctionNOK=None):
		# curatenia pe rezerva: nimic de facut, ca atunci cand rezerva e oprita
		self.fallbackFunction = fallbackFunction
		self.fallbackFunctionNOK = fallbackFunctionNOK or fallbackFunction
		self.fallback()

	def fallback(self, message=None):
		if message:
			from Screens.MessageBox import MessageBox
			self.parent.session.openWithCallback(self.fallbackNOK, MessageBox, message, MessageBox.TYPE_ERROR)
		else:
			self.fallbackFunction()

	def fallbackNOK(self, answer=None):
		self.fallbackFunctionNOK()


class FallbackTimerDirs(FallbackTimerList):
	"""locurile de inregistrare de pe rezerva; fara rezerva, functia se cheama fara ele"""
	def getFallbackTimerList(self):
		self.fallbackFunction()


class FallbackTimerClass(TimerEntry):
	"""un temporizator de pe rezerva; aici nu se face niciunul (lista e goala), clasa e pentru isinstance din pluginuri"""
	def __init__(self, service_ref="", name="", disabled=0, timebegin=0, timeend=0, duration=0, startprepare=0, state=0, repeated=0, justplay=0, eit=0,
			afterevent=0, dirname="", description=""):
		from ServiceReference import ServiceReference
		self.service_ref = ServiceReference(service_ref and ":".join(service_ref.split(":")[:11]) or None)
		self.name = name
		self.disabled = disabled
		self.begin = timebegin
		self.end = timeend
		self.duration = duration
		self.startprepare = startprepare
		self.state = state
		self.repeated = repeated
		self.justplay = justplay
		self.eit = eit
		self.afterEvent = afterevent
		self.dirname = dirname
		self.description = description
		self.external = True
		self.tags = []
		self.repeatedbegindate = timebegin
